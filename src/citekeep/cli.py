"""Command line interface for synchronisation, search and maintenance.

``sync`` is the sole project/master workflow.  Editor-only mutations live
under the explicit ``editor`` protocol instead of masquerading as a second
generation of user commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tomllib
from pathlib import Path

from . import bib, catalog, decisions, duplicates, library, project, sources, storage
from . import sync as synchronization
from . import verify as verification

CONFIG = Path.home() / ".config" / "citekeep" / "config.toml"
SCHEMA_VERSION = 1


class Failure(Exception):
    """Something the user needs to fix, reported without a traceback."""


# --- locating the library ------------------------------------------------


def library_path(explicit=None):
    """Where the library lives: the flag, the environment, then the config.

    Three sources rather than one because the three callers differ — a
    one-off command names the file, a shell session exports it once, and an
    editor has neither and reads the config.
    """
    for candidate in (explicit, os.environ.get("CITEKEEP_LIBRARY")):
        if candidate:
            return Path(candidate).expanduser()
    if CONFIG.is_file():
        with open(CONFIG, "rb") as handle:
            configured = tomllib.load(handle).get("library")
        if configured:
            return Path(configured).expanduser()
    raise Failure(
        "no library configured — pass --library, set $CITEKEEP_LIBRARY, "
        f'or write library = "…/master.bib" in {CONFIG}'
    )


def read_records(path, origin=None):
    path = Path(path).expanduser()
    if not path.is_file():
        raise Failure(f"{path}: no such file")
    return duplicates.records(bib.read_text(path), origin or path.name)


def write_atomically(path, text, expected_digest=None):
    """Replace PATH's contents, or leave them untouched.

    The library is the one file that is not regenerable; a write interrupted
    half way through must not be able to truncate it. Existing permissions and
    symlinks are preserved. EXPECTED_DIGEST, when given, rejects a concurrent
    edit made since the caller planned its changes.
    """
    try:
        storage.write_atomically(path, text, expected_digest)
    except storage.ConcurrentModification as error:
        raise Failure(str(error)) from error


# --- where ---------------------------------------------------------------


def cmd_where(args):
    """Print the resolved library path.

    An editor integration needs to open the library and to show which file it
    is working on. Asking here keeps the resolution order in one place instead
    of reimplemented in every front end.
    """
    path = library_path(args.library)
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "library": str(path),
                    "exists": path.is_file(),
                }
            )
        )
    else:
        print(path)
    return 0 if path.is_file() else 1


# --- locating a project bibliography ------------------------------------


def target_bib(args, declared):
    """The project .bib to complete: the flag, else what the document says."""
    if args.bib:
        return Path(args.bib).expanduser()
    if len(declared) == 1:
        return declared[0]
    if not declared:
        raise Failure("no .bib declared by the sources — name one with --bib")
    raise Failure(
        "several .bib files declared ("
        + ", ".join(p.name for p in declared)
        + ") — pick one with --bib"
    )


# --- editor protocol -----------------------------------------------------


def cmd_editor_add_record(args):
    """Place a record read from standard input into a project .bib.

    The counterpart of `search` for a front end: search once, let the user
    choose, then send the chosen record here — rather than asking the service
    a second time for something already in hand. Also the way to file an entry
    copied from a publisher's page.
    """
    entry = sys.stdin.read()
    try:
        (record,) = duplicates.records(entry, "stdin")
    except ValueError:
        raise Failure("standard input holds no single BibTeX entry")

    path = library_path(args.library)
    target = Path(args.into).expanduser()
    existing = bib.read_text(target) if target.is_file() else ""
    master_records = duplicates.records(bib.read_text(path), path.name)
    local_records = duplicates.records(existing, target.name)
    match = catalog.classify_fetched(master_records, local_records, record)

    written = None
    if match.kind != "conflict":
        text, action = project.write_record(existing, entry, match.key)
        if action != "unchanged":
            write_atomically(target, text)
        written = {"file": str(target), "key": match.key, "action": action}

    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "written": written,
                    "match": {
                        "kind": match.kind,
                        "key": match.key,
                        "reason": match.reason,
                        "existing": [
                            {
                                "key": r.key,
                                "title": r.title,
                                "year": r.year,
                                "doi": r.doi,
                            }
                            for r in match.existing
                        ],
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif written:
        print(f"{written['action']} {written['key']} in {target.name}")
    else:
        print(f"{record.key}: {match.reason} — nothing written")
        for other in match.existing:
            print(
                f"      library   {other.year or '????'}  "
                f"{other.title[:66]}  ({other.key})"
            )
    return 1 if match.kind == "conflict" else 0


# --- local/master search -------------------------------------------------


def byline(record):
    """A short author line, for picking a result out of a list."""
    names = record.names
    if not names:
        return ""
    first = bib.surname(names[0])
    return first if len(names) == 1 else f"{first} et al."


def _search_hit(hit):
    record = hit.record
    return {
        "origin": hit.origin,
        "citation_key": hit.citation_key,
        "master_key": hit.master_key,
        "title": record.title,
        "year": record.year,
        "authors": byline(record),
        "authors_full": " and ".join(record.names),
        "journal": record.journal,
        "doi": record.doi,
        "arxiv": record.arxiv,
        "score": hit.score,
    }


def cmd_search(args):
    path = library_path(args.library)
    master = read_records(path)
    local = read_records(args.local) if args.local else []
    query = " ".join(args.query)
    result = catalog.search(master, local, query)
    data = {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "local": [_search_hit(hit) for hit in result.local],
        "master": [_search_hit(hit) for hit in result.master],
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for label, hits in (("Project", result.local), ("Library", result.master)):
            if not hits:
                continue
            print(label + ":")
            for hit in hits:
                print(
                    f"  {byline(hit.record):24.24}  "
                    f"{hit.record.year or '????':4}  "
                    f"{hit.record.title[:58]}  [{hit.citation_key}]"
                )
    return 0


# --- online search -------------------------------------------------------

ADVICE = {
    "unchanged": "already in the library — cite {key}",
    "enrich": "in the library, incomplete — cite {key}",
    "new": "not in the library — it would enter as {key}",
    "conflict": "needs a decision: {reason}",
}


def cmd_fetch(args):
    path = library_path(args.library)
    master_records = duplicates.records(bib.read_text(path), path.name)
    target = Path(args.into).expanduser() if args.into else None
    existing = bib.read_text(target) if target and target.is_file() else ""
    local_records = duplicates.records(existing, target.name) if target else []

    query = " ".join(args.query)
    try:
        source, entries = sources.lookup(query, count=args.count)
    except sources.NoResult:
        raise Failure(f"no record found for {query!r}")
    except sources.SourceError as error:
        raise Failure(str(error))

    candidates = []
    for text in entries:
        (record,) = duplicates.records(text, source)
        match = catalog.classify_fetched(master_records, local_records, record)
        candidates.append(
            {
                "key": record.key,
                "title": record.title,
                "year": record.year,
                "authors": byline(record),
                "doi": record.doi,
                "entry": text,
                "match": {
                    "kind": match.kind,
                    "key": match.key,
                    "reason": match.reason,
                    "existing": [
                        {"key": r.key, "title": r.title, "year": r.year, "doi": r.doi}
                        for r in match.existing
                    ],
                },
            }
        )

    written = None
    if args.take:
        chosen = next((c for c in candidates if c["key"] == args.take), None)
        if chosen is None:
            raise Failure(f"{args.take}: not among the results")
        if not target:
            raise Failure("--take needs --into to say where to write")
        if chosen["match"]["kind"] == "conflict":
            raise Failure(
                f"{args.take}: {chosen['match']['reason']} — decide before taking it"
            )
        text, action = project.write_record(
            existing, chosen["entry"], chosen["match"]["key"]
        )
        if action != "unchanged":
            write_atomically(target, text)
        written = {"file": str(target), "key": chosen["match"]["key"], "action": action}

    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "source": source,
                    "query": query,
                    "results": candidates,
                    "written": written,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"{source}: {len(candidates)} result(s) for {query!r}")
    for candidate in candidates:
        print(
            f"  {candidate['authors'] or '—':28.28}  "
            f"{candidate['year'] or '????':4}  {candidate['title'][:56]}"
        )
        print(
            f"      {candidate['key']}  —  "
            + ADVICE[candidate["match"]["kind"]].format(
                key=candidate["match"]["key"], reason=candidate["match"]["reason"]
            )
        )
    if written:
        print(f"\n{written['action']} {written['key']} in {Path(written['file']).name}")
    return 0


# --- unified project planning and synchronisation -----------------------


def _project_plan(args):
    master_path = library_path(args.library)
    cited, declared = project.scan(args.project)
    bib_path = target_bib(args, declared)
    if master_path.resolve() == bib_path.resolve():
        raise Failure(
            f"{bib_path}: the project bibliography cannot be the master library"
        )
    master_text = bib.read_text(master_path)
    local_text = bib.read_text(bib_path) if bib_path.is_file() else ""
    plan = synchronization.plan(
        master_text,
        local_text,
        cited,
        field_resolutions=_field_resolutions(args),
        identity_resolutions=_identity_resolutions(args),
        master_origin=master_path.name,
        local_origin=bib_path.name,
    )
    return master_path, bib_path, master_text, local_text, plan


def _field_resolutions(args):
    """Collect auditable file decisions and convenient one-off CLI flags."""
    resolutions = {}
    decision_file = getattr(args, "resolve_fields", None)
    if decision_file:
        text = bib.read_text(Path(decision_file).expanduser())
        resolutions, unread = synchronization.parse_field_resolutions(text)
        if unread:
            details = ", ".join(f"line {number}: {line!r}" for number, line in unread)
            raise Failure("not field decisions: " + details)

    for option, verb in (("keep_master", "master"), ("use_local", "local")):
        for specification in getattr(args, option, ()):
            local_key, separator, field = specification.rpartition(":")
            if not separator or not local_key or not field:
                raise Failure(f"{specification!r}: expected LOCAL_KEY:FIELD")
            key = (local_key, bib.canonical(field))
            previous = resolutions.get(key)
            if previous and previous != verb:
                raise Failure(f"contradictory decisions for {local_key}:{field}")
            resolutions[key] = verb
    return resolutions


def _identity_resolutions(args):
    decision_file = getattr(args, "resolve", None)
    if not decision_file:
        return {}
    path = Path(decision_file).expanduser()
    text = bib.read_text(path)
    resolutions, unread = library.parse_resolutions(text)
    if unread:
        details = ", ".join(f"line {number}: {line!r}" for number, line in unread)
        raise Failure("not identity decisions: " + details)
    return resolutions


def report_sync(plan, master_path, bib_path, applied=False):
    counts = synchronization.summary(plan)
    lines = [
        (
            f"{bib_path}: {counts['master_added']} to master, "
            f"{counts['master_enriched']} master completions, "
            f"{counts['master_corrected']} master corrections, "
            f"{counts['local_added']} copied locally, "
            f"{counts['local_updated']} local updates, "
            f"{counts['conflicts']} conflicts, {counts['unknown']} unknown"
        )
    ]
    for local, master in plan.aliases_added:
        lines.append(f"  = {local} -> {master}")
    for conflict in plan.conflicts:
        candidates = (
            " (" + ", ".join(conflict.master_keys) + ")" if conflict.master_keys else ""
        )
        lines.append(f"  ! {conflict.local_key}: {conflict.reason}{candidates}")
        if conflict.incoming:
            lines.append(
                f"      incoming {conflict.incoming.year or '????'}  "
                f"{conflict.incoming.title}"
            )
            for record in conflict.existing:
                lines.append(
                    f"      master   {record.year or '????'}  "
                    f"{record.title} ({record.key})"
                )
            lines.append(
                "      decide with --resolve FILE: "
                f"same|distinct|skip {conflict.local_key}"
            )
        for field in conflict.fields:
            lines.append(
                f"      {field.name}: master={field.master!r}; local={field.local!r}"
            )
            lines.append(
                f"      choose --keep-master {conflict.local_key}:{field.name} "
                f"or --use-local {conflict.local_key}:{field.name}"
            )
    for key, files in plan.unknown:
        lines.append(f"  ? {key}: " + ", ".join(Path(name).name for name in files))
    if plan.blocked:
        lines.append("Nothing was written.")
    elif applied:
        lines.append(f"Applied to {master_path} and {bib_path}.")
    else:
        lines.append("Plan only: run sync --apply to write it.")
    return "\n".join(lines)


def _run_project_plan(args, apply=False):
    master_path, bib_path, master_text, local_text, plan = _project_plan(args)
    applied = False
    if apply and not plan.blocked:
        master_digest = hashlib.sha256(master_path.read_bytes()).hexdigest()
        if plan.master_text != master_text:
            write_atomically(
                master_path, plan.master_text, expected_digest=master_digest
            )
        if plan.local_text != local_text:
            local_digest = (
                hashlib.sha256(bib_path.read_bytes()).hexdigest()
                if bib_path.is_file()
                else None
            )
            write_atomically(bib_path, plan.local_text, expected_digest=local_digest)
        applied = True

    if args.json:
        data = {"schema_version": SCHEMA_VERSION, **synchronization.as_dict(plan)}
        data.update(
            {
                "master_file": str(master_path),
                "local_file": str(bib_path),
                "applied": applied,
            }
        )
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(report_sync(plan, master_path, bib_path, applied))
    return 1 if plan.blocked or plan.unknown else 0


def cmd_sync(args):
    return _run_project_plan(args, apply=args.apply)


def cmd_init(args):
    path = library_path(args.library)
    if path.exists() or path.is_symlink():
        raise Failure(f"{path}: already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomically(path, "%% citekeep master bibliography\n")
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "library": str(path),
                    "created": True,
                }
            )
        )
    else:
        print(f"Created {path}")
    return 0


def cmd_emacs_path(args):
    """Print the editor package installed in a wheel or present in checkout."""
    installed = Path(__file__).parent / "editor" / "citekeep.el"
    checkout = Path(__file__).parents[2] / "editors" / "emacs" / "citekeep.el"
    path = next(
        (candidate for candidate in (installed, checkout) if candidate.is_file()), None
    )
    if path is None:
        raise Failure("the Emacs package is not present in this installation")
    if args.json:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "emacs_file": str(path)}))
    else:
        print(path)
    return 0


# --- materialising one master record ------------------------------------


def cmd_editor_materialize(args):
    master_path = library_path(args.library)
    records = {record.key: record for record in read_records(master_path)}
    record = records.get(args.key)
    if record is None:
        raise Failure(f"{args.key}: no such key in {master_path}")
    target = Path(args.into).expanduser()
    existing = bib.read_text(target) if target.is_file() else ""
    plan = catalog.materialize(existing, record)
    if plan.action != "unchanged":
        write_atomically(target, plan.text)
    data = {
        "schema_version": SCHEMA_VERSION,
        "file": str(target),
        "citation_key": plan.citation_key,
        "master_key": plan.master_key,
        "action": plan.action,
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"{plan.action} {plan.citation_key} in {target}")
    return 0


# --- verifying one local entry ------------------------------------------


def _record_named(text, key, origin):
    found = [record for record in duplicates.records(text, origin) if record.key == key]
    if not found:
        raise Failure(f"{key}: no such entry in {origin}")
    if len(found) > 1:
        raise Failure(f"{key}: appears {len(found)} times in {origin}")
    return found[0]


def _verification_candidate(report_, source):
    candidates = [
        candidate
        for candidate in report_.candidates
        if candidate.trusted_identity and (not source or candidate.source == source)
    ]
    if not candidates:
        detail = f" from {source}" if source else ""
        raise Failure("no trusted online record" + detail)
    return candidates[0]


def report_verification(report_):
    lines = [f"{report_.local.key}: {len(report_.candidates)} online answer(s)"]
    for candidate in report_.candidates:
        mark = "+" if candidate.trusted_identity else "?"
        lines.append(
            f"  {mark} {candidate.source}: {candidate.record.title} "
            f"({candidate.reason})"
        )
    for field in report_.fields:
        values = "; ".join(f"{source}={value}" for source, value in field.sources)
        lines.append(f"  {field.name}: local={field.local or '—'}; {values}")
    return "\n".join(lines)


def cmd_verify(args):
    target = Path(args.file).expanduser()
    text = bib.read_text(target)
    local = _record_named(text, args.key, target.name)
    try:
        report_ = verification.fetch_all(local)
    except sources.SourceError as error:
        raise Failure(str(error))

    mode = "replace" if args.replace else ("selected" if args.field else "complete")
    applied = None
    if args.apply:
        candidate = _verification_candidate(report_, args.source)
        try:
            refresh = verification.plan_refresh(local, candidate, mode, args.field)
        except ValueError as error:
            raise Failure(str(error))
        new_text = bib.transform_entries(
            text,
            lambda _type, key, raw, _body: (
                refresh.text if key == local.key and raw == local.raw else raw
            ),
        )
        write_atomically(target, new_text)
        applied = {
            "source": refresh.source,
            "mode": refresh.mode,
            "fields": list(refresh.fields),
        }

    if args.json:
        data = {"schema_version": SCHEMA_VERSION, **verification.as_dict(report_)}
        data.update({"file": str(target), "applied": applied})
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(report_verification(report_))
        if applied:
            print(f"Applied {applied['mode']} from {applied['source']}.")
    return 0


def cmd_editor_refresh_record(args):
    """Apply a fetched entry supplied on stdin without querying it again."""
    target = Path(args.file).expanduser()
    text = bib.read_text(target)
    local = _record_named(text, args.key, target.name)
    fetched_text = sys.stdin.read()
    try:
        (fetched,) = duplicates.records(fetched_text, args.source)
    except ValueError:
        raise Failure("standard input holds no single BibTeX entry")
    report_ = verification.report(local, [(args.source, fetched)])
    candidate = _verification_candidate(report_, args.source)
    try:
        refresh = verification.plan_refresh(local, candidate, args.mode, args.field)
    except ValueError as error:
        raise Failure(str(error))
    new_text = bib.transform_entries(
        text,
        lambda _type, key, raw, _body: (
            refresh.text if key == local.key and raw == local.raw else raw
        ),
    )
    write_atomically(target, new_text)
    data = {
        "schema_version": SCHEMA_VERSION,
        "file": str(target),
        "key": local.key,
        "source": refresh.source,
        "mode": refresh.mode,
        "fields": list(refresh.fields),
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Refreshed {local.key} from {refresh.source} ({refresh.mode}).")
    return 0


# --- deliberate library maintenance ------------------------------------


def duplicate_review(groups):
    """An editable, diffable review file; untouched groups remain on hold."""
    lines = [
        "# Replace hold with one keep and one or more drop decisions.",
        "# Add letters after keep/drop to split a candidate group.",
    ]
    for group in groups:
        lines.extend(
            (
                "",
                f"## {duplicates.group_id(group)}",
                f"# {duplicates.coherence(group) or 'coherent candidate'}",
            )
        )
        for record in sorted(group, key=lambda item: item.key.lower()):
            lines.append(f"  hold  {record.key}")
            lines.append(f"        {record.year or '????'}  {record.title}")
            if record.doi:
                lines.append(f"        DOI {record.doi}")
    return "\n".join(lines) + "\n"


def _maintenance_path(args):
    return Path(args.file).expanduser() if args.file else library_path(args.library)


def cmd_duplicates(args):
    path = _maintenance_path(args)
    records = read_records(path)
    groups = duplicates.find_groups(records)
    data = {
        "schema_version": SCHEMA_VERSION,
        **duplicates.summary(groups),
        "file": str(path),
        "groups_data": [duplicates.as_dict(group) for group in groups],
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(duplicate_review(groups))
    return 1 if groups else 0


def _accepted_suspects(specifications):
    accepted = set()
    for specification in specifications:
        survivor, separator, donor = specification.rpartition(":")
        if not separator or not survivor or not donor:
            raise Failure(f"{specification!r}: expected SURVIVOR:DONOR")
        accepted.add((survivor, donor))
    return accepted


def cmd_dedupe(args):
    path = _maintenance_path(args)
    text = bib.read_text(path)
    records = duplicates.records(text, path.name)
    review_text = bib.read_text(Path(args.resolve).expanduser())
    unread = decisions.unread_lines(review_text)
    if unread:
        details = ", ".join(f"line {number}: {line!r}" for number, line in unread)
        raise Failure("not duplicate decisions: " + details)
    plan = decisions.plan(records, decisions.parse(review_text), normalise_keys=False)
    accepted = _accepted_suspects(args.accept_suspect)
    suspects = tuple(pair for pair in plan.suspects if pair not in accepted)
    blocked = bool(plan.problems or suspects)
    changed = bool(plan.merges)
    applied = False
    if args.apply and not blocked and changed:
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        write_atomically(path, decisions.apply_text(text, records, plan), expected)
        applied = True
    data = {
        "schema_version": SCHEMA_VERSION,
        "file": str(path),
        "blocked": blocked,
        "changed": changed,
        "applied": applied,
        "merges": [
            {"survivor": merge.survivor, "donors": list(merge.donors)}
            for merge in plan.merges
        ],
        "problems": list(plan.problems),
        "suspects": [
            {"survivor": survivor, "donor": donor} for survivor, donor in suspects
        ],
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(
            f"{path}: {len(plan.merges)} reviewed merge(s), "
            f"{len(plan.problems)} problem(s), {len(suspects)} suspect(s)"
        )
        for problem in plan.problems:
            print(f"  ! {problem}")
        for survivor, donor in suspects:
            print(
                f"  ! suspect {donor} -> {survivor}; confirm with "
                f"--accept-suspect {survivor}:{donor}"
            )
        if blocked:
            print("Nothing was written.")
        elif applied:
            print("Applied; surviving citation keys were kept unchanged.")
        else:
            print("Plan only: add --apply to write it.")
    return 1 if blocked else 0


def cmd_migrate_keys(args):
    path = _maintenance_path(args)
    text = bib.read_text(path)
    records = duplicates.records(text, path.name)
    plan = decisions.plan(records, [], normalise_keys=True)
    mapping = {old: new for old, new in sorted(plan.mapping.items()) if old != new}
    applied = False
    if args.apply and mapping:
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        write_atomically(path, decisions.apply_text(text, records, plan), expected)
        applied = True
    data = {
        "schema_version": SCHEMA_VERSION,
        "file": str(path),
        "changed": bool(mapping),
        "applied": applied,
        "mapping": mapping,
        "collisions": plan.collisions,
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"{path}: {len(mapping)} key change(s)")
        for old, new in mapping.items():
            print(f"  {old} -> {new}")
        if mapping and not args.apply:
            print("Plan only: add --apply after reviewing dependent projects.")
        elif applied:
            print(
                "Applied. Update external citations and ckmasterkey links "
                "using the mapping above."
            )
    return 0


# --- entry point ---------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="citekeep", description="Keep one bibliography, and keep it clean."
    )
    parser.add_argument("--version", action="version", version=f"citekeep {_version()}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create an empty master bibliography")
    init.add_argument(
        "--library", required=True, help="path of the master .bib to create"
    )
    init.add_argument("--json", action="store_true")
    init.set_defaults(run=cmd_init)

    emacs_path = commands.add_parser(
        "emacs-path", help="print the installed citekeep.el path"
    )
    emacs_path.add_argument("--json", action="store_true")
    emacs_path.set_defaults(run=cmd_emacs_path)

    where = commands.add_parser("where", help="print the resolved library path")
    where.add_argument("--library", help="path to the library (master .bib)")
    where.add_argument("--json", action="store_true")
    where.set_defaults(run=cmd_where)

    search = commands.add_parser(
        "search", help="search the project bibliography, then the master"
    )
    search.add_argument("query", nargs="*", help="author, title, key or identifier")
    search.add_argument(
        "--local", metavar="FILE", help="project .bib to search before the master"
    )
    search.add_argument("--library", help="path to the library (master .bib)")
    search.add_argument("--json", action="store_true")
    search.set_defaults(run=cmd_search)

    fetch = commands.add_parser(
        "fetch", help="search online and see what the library knows"
    )
    fetch.add_argument("query", nargs="+", help="words, or an identifier")
    fetch.add_argument(
        "--count", type=int, default=10, help="how many results to ask for (default 10)"
    )
    fetch.add_argument(
        "--take", metavar="KEY", help="write the result carrying this key into --into"
    )
    fetch.add_argument(
        "--into", metavar="FILE", help="the project .bib to write to, and to check"
    )
    fetch.add_argument("--library", help="path to the library (master .bib)")
    fetch.add_argument("--json", action="store_true")
    fetch.set_defaults(run=cmd_fetch)

    verify_cmd = commands.add_parser(
        "verify", help="compare one local entry with every online source"
    )
    verify_cmd.add_argument("file", help="project .bib containing the entry")
    verify_cmd.add_argument("--key", required=True, help="local citation key")
    verify_cmd.add_argument(
        "--source",
        choices=tuple(sources.BY_NAME),
        help="source to apply (default: first trusted)",
    )
    verify_cmd.add_argument(
        "--replace",
        action="store_true",
        help="replace bibliographic metadata explicitly",
    )
    verify_cmd.add_argument(
        "--field",
        action="append",
        default=[],
        help="accept this field from the selected source",
    )
    verify_cmd.add_argument(
        "--apply",
        action="store_true",
        help="apply completion, selected fields or replacement",
    )
    verify_cmd.add_argument("--json", action="store_true")
    verify_cmd.set_defaults(run=cmd_verify)

    editor = commands.add_parser(
        "editor", help="structured protocol used by editor integrations"
    )
    editor_actions = editor.add_subparsers(dest="editor_action", required=True)

    editor_materialize = editor_actions.add_parser(
        "materialize", help="copy one canonical record into a project .bib"
    )
    editor_materialize.add_argument("key", help="canonical key in the master")
    editor_materialize.add_argument("--into", required=True, metavar="FILE")
    editor_materialize.add_argument("--library", help="path to the library")
    editor_materialize.add_argument("--json", action="store_true")
    editor_materialize.set_defaults(run=cmd_editor_materialize)

    editor_add = editor_actions.add_parser(
        "add-record", help="place the stdin BibTeX record into a project .bib"
    )
    editor_add.add_argument("--into", required=True, metavar="FILE")
    editor_add.add_argument("--library", help="path to the library")
    editor_add.add_argument("--json", action="store_true")
    editor_add.set_defaults(run=cmd_editor_add_record)

    editor_refresh = editor_actions.add_parser(
        "refresh-record", help="apply the stdin record to a local entry"
    )
    editor_refresh.add_argument("file", help="project .bib containing the entry")
    editor_refresh.add_argument("--key", required=True, help="local citation key")
    editor_refresh.add_argument(
        "--source", required=True, help="provenance of the stdin BibTeX entry"
    )
    editor_refresh.add_argument(
        "--mode", choices=("complete", "selected", "replace"), default="complete"
    )
    editor_refresh.add_argument("--field", action="append", default=[])
    editor_refresh.add_argument("--library", help=argparse.SUPPRESS)
    editor_refresh.add_argument("--json", action="store_true")
    editor_refresh.set_defaults(run=cmd_editor_refresh_record)

    duplicate_cmd = commands.add_parser(
        "duplicates", help="report possible duplicate records for review"
    )
    duplicate_cmd.add_argument(
        "file", nargs="?", help=".bib to inspect (default: master)"
    )
    duplicate_cmd.add_argument("--library", help="path of the default master")
    duplicate_cmd.add_argument("--json", action="store_true")
    duplicate_cmd.set_defaults(run=cmd_duplicates)

    dedupe = commands.add_parser(
        "dedupe", help="apply explicitly reviewed duplicate merges"
    )
    dedupe.add_argument("file", nargs="?", help=".bib to maintain (default: master)")
    dedupe.add_argument("--library", help="path of the default master")
    dedupe.add_argument(
        "--resolve",
        required=True,
        metavar="FILE",
        help="review file produced by the duplicates command",
    )
    dedupe.add_argument(
        "--accept-suspect",
        action="append",
        default=[],
        metavar="SURVIVOR:DONOR",
        help="confirm a reviewed merge lacking identity evidence",
    )
    dedupe.add_argument("--apply", action="store_true")
    dedupe.add_argument("--json", action="store_true")
    dedupe.set_defaults(run=cmd_dedupe)

    migrate = commands.add_parser(
        "migrate-keys", help="plan an explicit citation-key migration"
    )
    migrate.add_argument("file", nargs="?", help=".bib to migrate (default: master)")
    migrate.add_argument("--library", help="path of the default master")
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--json", action="store_true")
    migrate.set_defaults(run=cmd_migrate_keys)

    sync_cmd = commands.add_parser(
        "sync", help="plan or apply a complete project synchronisation"
    )
    sync_cmd.add_argument(
        "--project", default=".", help="project directory or a single .tex file"
    )
    sync_cmd.add_argument("--bib", help="project .bib to materialise")
    sync_cmd.add_argument("--library", help="path to the library (master .bib)")
    sync_cmd.add_argument(
        "--resolve",
        metavar="FILE",
        help="identity decisions: same|distinct|skip LOCAL_KEY [MASTER_KEY]",
    )
    _add_field_resolution_arguments(sync_cmd)
    sync_cmd.add_argument(
        "--apply",
        action="store_true",
        help="write the planned master and project changes",
    )
    sync_cmd.add_argument("--json", action="store_true")
    sync_cmd.set_defaults(run=cmd_sync)
    return parser


def _add_field_resolution_arguments(parser):
    parser.add_argument(
        "--resolve-fields",
        metavar="FILE",
        help="field decisions: 'master|local LOCAL_KEY FIELD', one per line",
    )
    parser.add_argument(
        "--keep-master",
        metavar="LOCAL_KEY:FIELD",
        action="append",
        default=[],
        help="keep the master value and restore it in the project view",
    )
    parser.add_argument(
        "--use-local",
        metavar="LOCAL_KEY:FIELD",
        action="append",
        default=[],
        help="promote the reviewed local value into the master",
    )


def _version():
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("citekeep")
    except PackageNotFoundError:
        return "0.0.0+dev"


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except Failure as error:
        print(f"citekeep: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"citekeep: {error}", file=sys.stderr)
        return 2
