"""Planning one master-to-project and project-to-master synchronisation."""

from __future__ import annotations

from . import bib, duplicates, library, project
from .model import CKMASTERKEY, FieldConflict, ProjectPlan, SyncConflict

# Fields whose differing values are corrections, not harmless presentation
# variants. Author and title formatting is handled by identity matching; URLs
# and notes often legitimately differ between a project and the master.
AUTHORITATIVE_FIELDS = frozenset(
    {
        "year",
        "journal",
        "volume",
        "number",
        "pages",
        "publisher",
        "doi",
        "eprint",
        "isbn",
        "issn",
    }
)


def _canonical_fields(record):
    """Canonical-name to (source spelling, value) for a master record."""
    return {key: (name, value) for name, key, value in bib.donatable(record.body)}


def _local_fields(record):
    fields = {}
    for name, _raw in bib.parse_fields(record.body, tolerant=True) or []:
        fields[bib.canonical(name)] = name.lower()
    return fields


def _comparable(value):
    return " ".join(bib.latex_clean(value).lower().split())


def field_disagreements(local, canonical):
    """Canonical field names whose local and master values contradict."""
    local_values = {
        meaning: value for _name, meaning, value in bib.donatable(local.body)
    }
    master_values = {
        meaning: value for _name, meaning, value in bib.donatable(canonical.body)
    }
    return tuple(
        sorted(
            meaning
            for meaning in AUTHORITATIVE_FIELDS
            if local_values.get(meaning)
            and master_values.get(meaning)
            and _comparable(local_values[meaning])
            != _comparable(master_values[meaning])
        )
    )


def field_conflicts(local, canonical):
    """Structured values for every authoritative disagreement."""
    local_values = {
        meaning: value for _name, meaning, value in bib.donatable(local.body)
    }
    master_values = {
        meaning: value for _name, meaning, value in bib.donatable(canonical.body)
    }
    return tuple(
        FieldConflict(name, master_values[name], local_values[name])
        for name in field_disagreements(local, canonical)
    )


FIELD_RESOLUTION_VERBS = frozenset({"master", "local"})


def parse_field_resolutions(text):
    """Parse ``master|local LOCAL_KEY FIELD`` decisions.

    ``master`` keeps the canonical value and rematerialises it locally;
    ``local`` deliberately promotes the local value into the master.  The
    second return value lists malformed non-comment lines.
    """
    resolutions, unread = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 3 or parts[0] not in FIELD_RESOLUTION_VERBS:
            unread.append((number, line.rstrip()))
            continue
        verb, local_key, field = parts
        resolutions[(local_key, bib.canonical(field))] = verb
    return resolutions, unread


def _correct_master(text, corrections):
    """Apply deliberate ``(master key, field) -> (name, value)`` changes."""

    def transform(_type, key, raw, body):
        changes = [
            (field, value)
            for (master_key, field), value in corrections.items()
            if master_key == key
        ]
        if not changes:
            return raw
        local_names = {
            bib.canonical(name): name.lower()
            for name, _value in (bib.parse_fields(body, tolerant=True) or [])
        }
        additions = []
        for meaning, (source_name, value) in changes:
            if meaning in local_names:
                raw = bib.replace_field_value(raw, local_names[meaning], value)
            else:
                additions.append((source_name, value))
        return bib.append_fields(raw, additions) if additions else raw

    return bib.transform_entries(text, transform)


def materialize_record(local, canonical):
    """Render CANONICAL's data through LOCAL's key and local metadata."""
    raw = local.raw
    local_fields = _local_fields(local)
    missing = []
    for meaning, (source_name, value) in _canonical_fields(canonical).items():
        local_name = local_fields.get(meaning)
        if local_name:
            current = bib.get_field(next(bib.iter_entries(raw))[3], local_name)
            if current.strip() != value.strip():
                raw = bib.replace_field_value(raw, local_name, value)
        else:
            missing.append((source_name, value))
    if missing:
        raw = bib.append_fields(raw, missing)

    # The master decides the bibliographic type, while the project's citation
    # key is an interface shared with collaborators and remains untouched.
    raw = bib.ENTRY_HEAD.sub(f"@{canonical.type}{{{local.key},", raw, count=1)
    if local.key != canonical.key:
        raw = bib.set_field(raw, CKMASTERKEY, canonical.key)
    else:
        raw = bib.drop_fields(raw, {CKMASTERKEY})
    return raw


def _conflicts(proposal_plan):
    return tuple(
        SyncConflict(
            conflict.incoming.key,
            conflict.reason,
            tuple(record.key for record in conflict.existing),
            (),
            conflict.incoming,
            conflict.existing,
            ("same", "distinct", "skip"),
        )
        for conflict in proposal_plan.conflicts
    )


def plan(
    master_text,
    local_text,
    cited=None,
    field_resolutions=None,
    identity_resolutions=None,
    master_origin="master.bib",
    local_origin="project.bib",
):
    """Return the complete future state of a master and one project `.bib`.

    CITED maps citation keys to the source files using them.  It may be omitted
    when synchronising a bibliography independently of a document tree.
    """
    cited = cited or {}
    field_resolutions = field_resolutions or {}
    identity_resolutions = identity_resolutions or {}
    master_records = duplicates.records(master_text, master_origin)
    local_records = duplicates.records(local_text, local_origin)
    proposal_plan = library.plan_proposals(
        master_records, local_records, identity_resolutions
    )
    if proposal_plan.blocked:
        return ProjectPlan(
            master_text,
            local_text,
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            _conflicts(proposal_plan),
        )

    future_master = library.apply_proposals(master_text, proposal_plan)
    future_records = duplicates.records(future_master, master_origin)
    future_index = library.index(future_records)
    original_master_keys = {record.key for record in master_records}
    accepted_links = dict(proposal_plan.links)
    skipped = set(proposal_plan.skipped)

    matches = []
    conflicts = []
    corrections = {}
    for local in local_records:
        if local.key in skipped:
            continue
        canonical_key = accepted_links.get(local.key)
        canonical = future_index.by_key.get(canonical_key)
        if canonical is None:
            conflicts.append(
                SyncConflict(
                    local.key,
                    "accepted record has no canonical target",
                    (canonical_key,) if canonical_key else (),
                )
            )
            continue
        disagreements = (
            field_conflicts(local, canonical)
            if canonical.key in original_master_keys
            else ()
        )
        unresolved = tuple(
            disagreement
            for disagreement in disagreements
            if (local.key, disagreement.name) not in field_resolutions
        )
        if unresolved:
            conflicts.append(
                SyncConflict(
                    local.key,
                    "field values disagree: "
                    + ", ".join(field.name for field in unresolved),
                    (canonical.key,),
                    unresolved,
                )
            )
            continue
        for disagreement in disagreements:
            decision = field_resolutions[(local.key, disagreement.name)]
            if decision not in FIELD_RESOLUTION_VERBS:
                conflicts.append(
                    SyncConflict(
                        local.key,
                        f"invalid field decision: {decision}",
                        (canonical.key,),
                        (disagreement,),
                    )
                )
                continue
            if decision == "local":
                key = (canonical.key, disagreement.name)
                proposed = (disagreement.name, disagreement.local)
                if key in corrections and corrections[key] != proposed:
                    conflicts.append(
                        SyncConflict(
                            local.key,
                            f"several local values proposed for {disagreement.name}",
                            (canonical.key,),
                            (disagreement,),
                        )
                    )
                    continue
                corrections[key] = proposed
        matches.append((local, canonical.key))

    if conflicts:
        return ProjectPlan(
            master_text, local_text, (), (), (), (), (), (), (), tuple(conflicts)
        )

    master_corrections = tuple(
        sorted((master_key, field) for master_key, field in corrections)
    )
    if corrections:
        future_master = _correct_master(future_master, corrections)
        future_records = duplicates.records(future_master, master_origin)
        future_index = library.index(future_records)

    replacements = {}
    aliases, local_updates = [], []
    held = {record.key for record in local_records}
    for local, canonical_key in matches:
        canonical = future_index.by_key[canonical_key]
        raw = materialize_record(local, canonical)
        replacements[local.raw] = raw
        if local.key != canonical.key and local.master_key != canonical.key:
            aliases.append((local.key, canonical.key))
        if raw != local.raw:
            local_updates.append(local.key)

    refreshed = bib.transform_entries(
        local_text, lambda _type, _key, raw, _body: replacements.get(raw, raw)
    )

    available = {record.key: record for record in future_records}
    missing = tuple(
        available[key] for key in sorted(cited) if key not in held and key in available
    )
    unknown = tuple(
        (key, tuple(sorted(str(path) for path in cited[key])))
        for key in sorted(cited)
        if key not in held and key not in available
    )
    final_local = project.apply_materialization(refreshed, missing)
    unused = tuple(sorted(held - set(cited))) if cited else ()

    return ProjectPlan(
        future_master,
        final_local,
        tuple(change.key for change in proposal_plan.additions),
        tuple(change.key for change in proposal_plan.enrichments),
        tuple(record.key for record in missing),
        tuple(local_updates),
        tuple(aliases),
        unknown,
        unused,
        (),
        master_corrections,
        tuple(sorted(skipped)),
    )


def summary(plan_):
    return {
        "master_added": len(plan_.master_additions),
        "master_enriched": len(plan_.master_enrichments),
        "master_corrected": len(plan_.master_corrections),
        "local_added": len(plan_.local_additions),
        "local_updated": len(plan_.local_updates),
        "aliases_added": len(plan_.aliases_added),
        "local_skipped": len(plan_.local_skipped),
        "unknown": len(plan_.unknown),
        "unused": len(plan_.unused),
        "conflicts": len(plan_.conflicts),
    }


def as_dict(plan_):
    return {
        "summary": summary(plan_),
        "blocked": plan_.blocked,
        "changed": plan_.changed,
        "master": {
            "added": list(plan_.master_additions),
            "enriched": list(plan_.master_enrichments),
            "corrected": [
                {"key": key, "field": field} for key, field in plan_.master_corrections
            ],
        },
        "local": {
            "added": list(plan_.local_additions),
            "updated": list(plan_.local_updates),
            "aliases": [
                {"local": local, "master": master}
                for local, master in plan_.aliases_added
            ],
            "skipped": list(plan_.local_skipped),
        },
        "unknown": [{"key": key, "files": list(files)} for key, files in plan_.unknown],
        "unused": list(plan_.unused),
        "conflicts": [
            {
                "local_key": conflict.local_key,
                "reason": conflict.reason,
                "master_keys": list(conflict.master_keys),
                "fields": [
                    {"name": field.name, "master": field.master, "local": field.local}
                    for field in conflict.fields
                ],
                "answers": list(conflict.answers),
                "incoming": (
                    {
                        "key": conflict.incoming.key,
                        "title": conflict.incoming.title,
                        "year": conflict.incoming.year,
                        "doi": conflict.incoming.doi,
                    }
                    if conflict.incoming
                    else None
                ),
                "existing": [
                    {
                        "key": record.key,
                        "title": record.title,
                        "year": record.year,
                        "doi": record.doi,
                    }
                    for record in conflict.existing
                ],
            }
            for conflict in plan_.conflicts
        ],
    }
