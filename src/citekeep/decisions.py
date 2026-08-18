"""Reading a reviewed duplicate report, and turning it into a plan.

`duplicates` finds candidates; a person decides. This module reads those
decisions back and works out exactly what would happen, without doing any of
it — the plan is inspected before it is applied.

The decision file is plain text so that it can be edited in any editor and
diffed. Only lines of the form ``keep|drop|hold [letter] KEY`` carry meaning;
everything else, including the descriptive lines under each entry, is ignored,
so the reviewer can annotate freely.
"""

from __future__ import annotations

import collections
import re
from typing import NamedTuple

from . import bib
from .sources import base

GROUP_RE = re.compile(r"^##\s+(\S+)")
# Bounded indentation: the descriptive lines under each entry are indented
# further, and a title such as "Hold on to your priors" must not read as a
# decision.
VERB_RE = re.compile(r"^ {1,6}(keep|drop|hold)(?:\s+([a-z]))?\s+(\S+)\s*$")


class Decision(NamedTuple):
    group: str
    verb: str
    part: str  # "" unless the reviewer split the group
    key: str


def parse(text):
    """Read decisions from a reviewed report."""
    out, group = [], ""
    for line in text.splitlines():
        head = GROUP_RE.match(line)
        if head:
            group = head.group(1)
            continue
        match = VERB_RE.match(line)
        if match and group:
            out.append(
                Decision(group, match.group(1), match.group(2) or "", match.group(3))
            )
    return out


def unread_lines(text):
    """Lines inside a group that look like decisions but were not read.

    Silence here is the dangerous kind: a mistyped verb makes the line vanish,
    the entry keeps its own key, and nothing says so. Two lines out of 874 were
    damaged this way in the first real review — a yanked value pasted over the
    verb.

    Returns ``[(line number, line)]``. Descriptive lines are indented further
    and are not reported; nor are comments the reviewer added.
    """
    out, inside = [], False
    for number, line in enumerate(text.splitlines(), start=1):
        if GROUP_RE.match(line):
            inside = True
            continue
        if not inside or not line.strip():
            continue
        if not re.match(r"^ {1,6}\S", line) or line.lstrip().startswith("#"):
            continue
        if not VERB_RE.match(line):
            out.append((number, line.rstrip()))
    return out


def validate(decisions, known_keys):
    """Return the list of problems that would make a plan meaningless.

    Reported rather than raised: a review of hundreds of groups should come
    back with every mistake at once, not one per run.
    """
    problems = []
    seen = collections.Counter(d.key for d in decisions)
    for key, count in sorted(seen.items()):
        if key not in known_keys:
            problems.append(f"{key}: clé inconnue dans la bibliothèque")
        if count > 1:
            problems.append(f"{key}: {count} décisions pour la même entrée")

    parts = collections.defaultdict(list)
    for decision in decisions:
        if decision.verb != "hold":
            parts[(decision.group, decision.part)].append(decision)
    for (group, part), members in sorted(parts.items()):
        label = f"{group}" + (f" (partie {part})" if part else "")
        keeps = [d for d in members if d.verb == "keep"]
        if not keeps:
            problems.append(f"{label} : des « drop » sans « keep »")
        elif len(keeps) > 1:
            problems.append(
                f"{label} : {len(keeps)} « keep » — utilise une lettre pour les séparer"
            )
    return problems


class Merge(NamedTuple):
    survivor: str
    donors: tuple


class Plan(NamedTuple):
    """What applying the decisions would do.

    `mapping` sends every old key to the key that replaces it, including the
    keys of merged-away entries. It is what lets a project bibliography and
    its `\\cite` commands be updated afterwards.
    """

    merges: tuple
    mapping: dict
    collisions: dict
    problems: tuple
    suspects: tuple


def _suffixed(keys_by_target):
    """Give distinct works that land on one key a stable ``a``/``b`` suffix.

    Ordered by year then original key, so the suffix a reference carries does
    not move when an unrelated entry is added later.
    """
    resolved, collisions = {}, {}
    for target, records in sorted(keys_by_target.items()):
        if len(records) == 1:
            resolved[records[0].key] = target
            continue
        ordered = sorted(records, key=lambda r: (r.year, r.key.lower()))
        collisions[target] = [r.key for r in ordered]
        for index, record in enumerate(ordered):
            resolved[record.key] = f"{target}{chr(ord('a') + index)}"
    return resolved, collisions


def suspect_merges(by_key, merges):
    """Merges that join what look like two different works.

    A reviewer works from a list where several works can share a block, and
    says which entry joins which by a letter. Mistyping that letter merges the
    wrong pair — twice out of seven blocks in the first real review. Nothing
    else catches it: the file is well-formed and the plan is consistent.

    Disagreeing titles alone are not evidence, because a preprint is often
    retitled before publication. The pair is only reported when the titles
    disagree *and* no identifier vouches for them being one work.

    Returns ``[(survivor, donor)]``.
    """
    out = []
    for merge in merges:
        survivor = by_key.get(merge.survivor)
        if survivor is None:
            continue
        for key in merge.donors:
            donor = by_key.get(key)
            if donor is None:
                continue
            if bib.same_work({survivor.signature, donor.signature}):
                continue
            if base.same_doi(survivor.doi, donor.doi):
                continue
            if survivor.arxiv and survivor.arxiv == donor.arxiv:
                continue
            out.append((merge.survivor, key))
    return tuple(out)


def plan(entries, decisions, normalise_keys=True):
    """Work out the effect of DECISIONS on ENTRIES.

    ENTRIES is a list of `duplicates.Record`. Entries no decision mentions are
    kept as they are.  When NORMALISE_KEYS is true, every survivor is also
    renamed to its computed target; a routine deduplication passes false so
    that key migration remains a separate, explicit maintenance operation.
    """
    by_key = {record.key: record for record in entries}
    problems = validate(decisions, set(by_key))

    dropped, merges = {}, []
    parts = collections.defaultdict(list)
    for decision in decisions:
        if decision.verb != "hold" and decision.key in by_key:
            parts[(decision.group, decision.part)].append(decision)
    for _label, members in sorted(parts.items()):
        keeps = [d.key for d in members if d.verb == "keep"]
        donors = tuple(d.key for d in members if d.verb == "drop")
        if len(keeps) != 1 or not donors:
            continue
        merges.append(Merge(keeps[0], donors))
        for donor in donors:
            dropped[donor] = keeps[0]

    survivors = [r for r in entries if r.key not in dropped]
    if normalise_keys:
        by_target = collections.defaultdict(list)
        for record in survivors:
            by_target[record.target].append(record)
        resolved, collisions = _suffixed(by_target)
    else:
        resolved = {record.key: record.key for record in survivors}
        collisions = {}

    mapping = dict(resolved)
    for donor, survivor in dropped.items():
        mapping[donor] = resolved[survivor]
    return Plan(
        tuple(merges),
        mapping,
        collisions,
        tuple(problems),
        suspect_merges(by_key, merges),
    )


# --- applying ------------------------------------------------------------


def apply_plan(entries, plan_):
    """Return the new bibliography text.

    Entries keep their source order and their raw text; only the key line is
    rewritten. Reformatting them would destroy brace-protected capitalisation
    and turn every future diff into a whole-file change.
    """
    by_key = {record.key: record for record in entries}
    donors_of = {
        merge.survivor: [by_key[k].body for k in merge.donors if k in by_key]
        for merge in plan_.merges
    }
    dropped = {key for merge in plan_.merges for key in merge.donors}

    out = []
    for record in entries:
        if record.key in dropped:
            continue
        raw = bib.merge_into(record.raw, donors_of.get(record.key, []))
        new_key = plan_.mapping.get(record.key, record.key)
        out.append(bib.ENTRY_HEAD.sub(f"@{record.type}{{{new_key},", raw, count=1))
    return "\n\n".join(out) + "\n"


def apply_text(text, entries, plan_):
    """Apply PLAN_ without reconstructing the surrounding BibTeX file.

    Comments, strings, preambles, whitespace between entries and unrelated
    formatting survive.  ``apply_plan`` remains for callers that deliberately
    want a bibliography consisting of entries alone.
    """
    by_key = {record.key: record for record in entries}
    donors_of = {
        merge.survivor: [by_key[key].body for key in merge.donors if key in by_key]
        for merge in plan_.merges
    }
    dropped = {key for merge in plan_.merges for key in merge.donors}

    def transform(type_, key, raw, _body):
        if key in dropped:
            return ""
        raw = bib.merge_into(raw, donors_of.get(key, []))
        new_key = plan_.mapping.get(key, key)
        return bib.ENTRY_HEAD.sub(f"@{type_}{{{new_key},", raw, count=1)

    return bib.transform_entries(text, transform)
