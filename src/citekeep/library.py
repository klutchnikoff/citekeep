"""Proposing a project's bibliography to the master library.

The library is the reference: it is not regenerated, it only ever grows, and
nothing enters it silently that a person has not seen. That constraint comes
from experience — a library assembled by merging on citation keys alone ended
up holding the same paper nine times, under nine keys.

The proposal planner sorts every incoming entry into one of four outcomes,
and only the last one asks anything of anybody:

- **unchanged** — the library already has this work, with nothing to add. The
  ordinary case, and it must stay silent: a prompt here, on every sync, is a
  prompt that stops being read.
- **enriched** — the library has the work but lacks some fields. They are
  filled in. The library's own values are never overwritten; a correction is
  a separate, deliberate operation.
- **added** — nothing in the library resembles it. It goes in under its
  normalised key.
- **conflict** — something resembles it, but not closely enough to be sure.
  Reported, never guessed. A plan carrying a conflict does not apply.
"""

from __future__ import annotations

import collections
import re
from typing import NamedTuple

from . import bib, duplicates


class Enrichment(NamedTuple):
    """An entry the library has, and that the incoming file completes."""

    key: str  # the key it lives under in the library
    incoming: duplicates.Record
    fields: tuple  # (name, value) pairs the library is missing


class Addition(NamedTuple):
    """An entry the library does not have."""

    key: str  # the normalised key it will take
    incoming: duplicates.Record


class Conflict(NamedTuple):
    """An entry that resembles something in the library, inconclusively."""

    key: str
    incoming: duplicates.Record
    existing: tuple
    reason: str


class ProposalPlan(NamedTuple):
    additions: tuple
    enrichments: tuple
    conflicts: tuple
    unchanged: tuple  # keys already present with nothing to add
    skipped: tuple = ()  # deliberately left out of this synchronisation
    links: tuple = ()  # (incoming key, canonical key) for accepted records

    @property
    def blocked(self):
        """Would applying this plan require a decision nobody has made?"""
        return bool(self.conflicts)


def missing_fields(existing, incoming):
    """Fields INCOMING has and EXISTING does not.

    Mirrors `bib.merge_into` exactly — same notion of "already present", same
    refusal to carry fields describing the source — so that what a report
    announces is what an application does.
    """
    have = {
        bib.canonical(name)
        for name, _v in (bib.parse_fields(existing.body, tolerant=True) or [])
    }
    out = []
    for name, key, value in bib.donatable(incoming.body):
        if bib.has_empty_field(existing.raw, name) or key not in have:
            out.append((name, value))
            have.add(key)
    return tuple(out)


# --- one entry at a time -------------------------------------------------
#
# The same question gets asked in two places: of a whole file about to be
# proposed, and of a single record just fetched from zbMATH or CrossRef while
# the user is writing. The second is where duplicates are cheapest to catch —
# the user is already looking at that reference — so both must go through one
# implementation, or the two will drift apart.


class Index(NamedTuple):
    """A library prepared for lookup."""

    by_print: dict
    by_key: dict
    keys: set


class Match(NamedTuple):
    """What the library already knows about one entry.

    KIND is one of:

    - ``unchanged`` — the library has this work and lacks nothing;
    - ``enrich`` — the library has it; FIELDS would complete it;
    - ``new`` — nothing resembles it; KEY is the key it would take;
    - ``conflict`` — something resembles it, inconclusively; see REASON.
    """

    kind: str
    key: str
    existing: tuple = ()
    fields: tuple = ()
    reason: str = ""


def index(records):
    """Prepare RECORDS for lookup."""
    by_print = collections.defaultdict(list)
    for record in records:
        for print_ in duplicates.fingerprints(record):
            by_print[print_].append(record)
    return Index(
        by_print,
        {record.key: record for record in records},
        {record.key for record in records},
    )


def register(index_, record, key):
    """Add RECORD to INDEX under KEY, as though it were already in place.

    Used while planning, so that two incoming entries describing one work meet
    each other instead of both landing in the library.
    """
    effective = record._replace(
        key=key, raw=bib.ENTRY_HEAD.sub(f"@{record.type}{{{key},", record.raw, count=1)
    )
    index_.keys.add(key)
    index_.by_key[key] = effective
    for print_ in duplicates.fingerprints(effective):
        index_.by_print[print_].append(effective)
    return effective


def replace(index_, old, new):
    """Replace OLD by NEW in an index representing the planned future."""
    for print_ in duplicates.fingerprints(old):
        bucket = index_.by_print.get(print_)
        if bucket and old in bucket:
            bucket.remove(old)
            if not bucket:
                del index_.by_print[print_]
    for print_ in duplicates.fingerprints(new):
        index_.by_print[print_].append(new)
    index_.by_key.pop(old.key, None)
    index_.by_key[new.key] = new


def completed(existing, incoming):
    """The effective record after INCOMING fills EXISTING's gaps."""
    raw = bib.merge_into(existing.raw, [incoming.body])
    (record,) = duplicates.records(raw, existing.origin)
    return record


def look_up(index_, record):
    """What the library makes of RECORD."""
    if record.master_key:
        existing = index_.by_key.get(record.master_key)
        if existing is None:
            return Match(
                "conflict", record.master_key, reason="master key does not exist"
            )
        reason = duplicates.coherence([existing, record])
        # The explicit link is evidence of identity; missing descriptive data
        # alone does not invalidate it, while contradictions still do.
        if reason and reason != "no title to compare":
            return Match("conflict", record.master_key, (existing,), reason=reason)
        fields = missing_fields(existing, record)
        return Match(
            "enrich" if fields else "unchanged", existing.key, (existing,), fields
        )

    found = []
    for print_ in duplicates.fingerprints(record):
        for other in index_.by_print.get(print_, ()):
            if other not in found:
                found.append(other)

    if not found:
        key = record.target
        # A key in use by an entry sharing no fingerprint is a different work
        # under the same name. The existing one cannot be renamed — references
        # to it exist — so this needs a decision.
        if key in index_.keys:
            return Match("conflict", key, reason="key already in use")
        return Match("new", key)

    if len(found) > 1:
        return Match(
            "conflict", record.target, tuple(found), reason="matches several entries"
        )

    existing = found[0]
    reason = duplicates.coherence([existing, record])
    if reason:
        return Match("conflict", record.target, (existing,), reason=reason)

    fields = missing_fields(existing, record)
    return Match("enrich" if fields else "unchanged", existing.key, (existing,), fields)


# --- settling what the evidence could not --------------------------------
#
# A conflict is a question, and these are the three answers it admits. They
# are recorded as plain text so that the decision can be read back, kept, and
# argued with — not buried in a session.

VERBS = ("same", "distinct", "skip")

RESOLUTION = re.compile(r"^\s*(same|distinct|skip)\s+(\S+)(?:\s+(\S+))?\s*$")


def parse_resolutions(text):
    """Read identity decisions.

    Returns ``({key: (verb, target)}, [(line number, line)])`` — the second
    being lines that look like decisions and are not, because a mistyped verb
    that is silently ignored leaves the user believing they answered.
    """
    out, unread = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = RESOLUTION.match(line)
        if match:
            out[match.group(2)] = (match.group(1), match.group(3))
        else:
            unread.append((number, line.rstrip()))
    return out, unread


def free_key(index_, base):
    """A key like BASE that nothing uses yet.

    The entry already holding BASE keeps it: references to it exist elsewhere,
    in documents this tool cannot see, so renaming it would break them. The
    newcomer takes the suffix instead.
    """
    if base not in index_.keys:
        return base
    for offset in range(26):
        candidate = f"{base}{chr(ord('a') + offset)}"
        if candidate not in index_.keys:
            return candidate
    raise ValueError(f"no free key left for {base}")


def settle(index_, record, match, verb, target):
    """Apply one decision to one conflict.  Returns (kind, payload).

    VERB is one of `VERBS`. The payload is what the plan carries for that
    kind: an `Addition`, an `Enrichment`, a `Conflict`, or a bare key. Callers
    filing a single record want `settle_match` instead.

    This is the single place where a decision becomes an outcome. Both the
    synchroniser and the editor's one-record path go through it, so that
    `distinct` allocates the next free suffix by one rule rather than two.
    """
    if verb == "skip":
        return "skip", record.key
    if verb == "distinct":
        key = free_key(index_, record.target)
        return "new", Addition(key, record)
    # "same": the library entry it belongs to. With one candidate there is
    # nothing to name; with several the answer has to say which.
    candidates = {other.key: other for other in match.existing}
    if target:
        existing = candidates.get(target)
    elif len(candidates) == 1:
        existing = next(iter(candidates.values()))
    else:
        existing = None
    if existing is None:
        return "conflict", Conflict(
            match.key,
            record,
            match.existing,
            "which entry? name it after « same »"
            if not target
            else f"{target} is not one of the entries it resembles",
        )
    fields = missing_fields(existing, record)
    if not fields:
        return "unchanged", existing.key
    return "enrich", Enrichment(existing.key, record, fields)


def _named(records, key):
    return next(record for record in records if record.key == key)


def settle_match(index_, record, match, verb, target):
    """Apply one decision to MATCH, and describe the result as a `Match`.

    The counterpart of `settle` for callers that file one record rather than
    plan many: an editor knows what a `Match` means, and has no use for the
    plan's `Addition` and `Enrichment` payloads.
    """
    kind, payload = settle(index_, record, match, verb, target)
    if kind == "new":
        return Match("new", payload.key)
    if kind == "skip":
        return Match("skip", payload)
    if kind == "unchanged":
        return Match("unchanged", payload, (_named(match.existing, payload),))
    if kind == "enrich":
        return Match(
            "enrich",
            payload.key,
            (_named(match.existing, payload.key),),
            payload.fields,
        )
    return Match("conflict", payload.key, payload.existing, reason=payload.reason)


def plan_proposals(library, incoming, resolutions=None):
    """Work out what adding INCOMING to LIBRARY would do.

    Both are lists of `duplicates.Record`. RESOLUTIONS answers conflicts a
    previous run reported, keyed by the incoming entry's own key.

    Nothing is written and nothing is decided here; the result is a
    description a person or a front end can read.
    """
    resolutions = resolutions or {}
    index_ = index(library)
    additions, enrichments, conflicts = [], [], []
    unchanged, skipped, links = [], [], []

    for record in incoming:
        match = look_up(index_, record)
        kind, payload = match.kind, None
        if kind == "new":
            payload = Addition(match.key, record)
        elif kind == "enrich":
            payload = Enrichment(match.key, record, match.fields)
        elif kind == "unchanged":
            payload = match.key
        else:
            verb, target = resolutions.get(record.key, (None, None))
            if verb in VERBS:
                kind, payload = settle(index_, record, match, verb, target)
            else:
                payload = Conflict(match.key, record, match.existing, match.reason)

        if kind == "new":
            additions.append(payload)
            register(index_, record, payload.key)
            links.append((record.key, payload.key))
        elif kind == "enrich":
            enrichments.append(payload)
            # A resolution may have selected one candidate out of several;
            # PAYLOAD names the effective target, while MATCH preserves all
            # candidates for the report.
            existing = index_.by_key[payload.key]
            replace(index_, existing, completed(existing, record))
            links.append((record.key, payload.key))
        elif kind == "unchanged":
            unchanged.append(payload)
            links.append((record.key, payload))
        elif kind == "skip":
            skipped.append(payload)
        else:
            conflicts.append(payload)

    return ProposalPlan(
        tuple(additions),
        tuple(enrichments),
        tuple(conflicts),
        tuple(unchanged),
        tuple(skipped),
        tuple(links),
    )


def apply_proposals(text, plan):
    """Return the new library text.

    Entries keep their raw source text; only missing fields are appended and,
    for an addition, the key line rewritten. New entries are appended. This
    preserves every unrelated byte, including comments and BibTeX directives;
    sorting is an explicit formatting operation, not a side effect of a sync.

    Raises ValueError on a plan carrying conflicts: the library never gains an
    entry that nobody has looked at.
    """
    if plan.blocked:
        raise ValueError(f"{len(plan.conflicts)} conflit(s) à arbitrer")

    donors = collections.defaultdict(list)
    for change in plan.enrichments:
        donors[change.key].append(change.incoming.body)

    result = bib.transform_entries(
        text, lambda _type, key, raw, _body: bib.merge_into(raw, donors.get(key, []))
    )

    added = []
    for addition in plan.additions:
        record = addition.incoming
        raw = bib.ENTRY_HEAD.sub(
            f"@{record.type}{{{addition.key},", record.raw, count=1
        )
        added.append(bib.merge_into(raw, donors.get(addition.key, [])))

    if not added:
        return result
    body = "\n\n".join(added)
    if not result.strip():
        return body + "\n"
    return result.rstrip("\n") + "\n\n" + body + "\n"
