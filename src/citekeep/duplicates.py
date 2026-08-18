"""Finding entries that describe the same work.

A bibliography assembled from many projects contains the same paper several
times under different keys: `MR2724359`, `Tsy09`, `tsybakov2009` and six more
were all one book in the corpus this was written for. Deduplicating by key —
the only thing a merge script can do safely on its own — leaves every one of
them in place.

This module only *detects*. It returns data structures and decides nothing:
merging two entries is a judgement (a preprint and its published version are
the same work; a paper and its supplementary material are not), and that
judgement belongs to a person, or to a front-end that asks one.
"""

from __future__ import annotations

import collections
import re

from . import bib
from .model import Record

# arXiv identifiers, old (math.ST/0503083) and new (1312.7402) style, with an
# optional version suffix that does not designate a different work.
ARXIV_RE = re.compile(
    r"(?:arxiv[:.]|arxiv\.org/(?:abs|pdf)/|10\.48550/arxiv\.)?"
    r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?",
    re.IGNORECASE,
)


def arxiv_id(body):
    """The arXiv identifier of an entry, in any of the forms it takes.

    A preprint and its published version share this and nothing else: the
    years differ, the titles are often reworded, and the DOI exists on only
    one of them. Without it they stay two entries for one work.

    The ``eprint`` field is not arXiv-specific — HAL uses it too — so an
    explicit repository name is honoured when there is one.
    """
    kind = (
        (bib.get_field(body, "eprinttype") or bib.get_field(body, "archiveprefix"))
        .strip()
        .lower()
    )
    # `arxivid` names the repository itself, so it needs no corroboration.
    candidates = [bib.get_field(body, "arxivid")]
    if not kind or kind == "arxiv":
        candidates.append(bib.get_field(body, "eprint"))
    for field in ("url", "doi", "note", "journal", "howpublished"):
        value = bib.get_field(body, field)
        if "arxiv" in value.lower():
            candidates.append(value)
    for candidate in candidates:
        match = ARXIV_RE.search(candidate.strip())
        if match:
            return match.group(1).lower()
    return ""


def records(text, origin=""):
    return [Record(t, k, r, b, origin) for t, k, r, b in bib.iter_entries(text)]


# --- grouping ------------------------------------------------------------
#
# Four criteria, applied together. None is sufficient alone: a DOI is missing
# from a third of a typical library; the normalised key separates a preprint
# from its published version because the years differ; titles alone would merge
# an article with its erratum; the arXiv identifier is the only thing a
# reworded preprint shares with the paper it became.


def fingerprints(record):
    """Hashable values that, if shared, suggest two records are one work."""
    if record.doi:
        yield "doi", record.doi
    if record.arxiv:
        yield "arxiv", record.arxiv
    yield "key", record.target
    if record.signature and record.names:
        yield "title", (bib.surname(record.names[0]).lower(), record.signature)


def find_groups(entries):
    """Group ENTRIES that may describe the same work.

    Returns groups of two or more, largest first, then by group id. Singletons
    are dropped: they are the normal case and carry no decision.

    Grouping is transitive — sharing any one fingerprint joins two records, and
    a chain of pairs becomes a single group. That is deliberate, so that a
    record linked by DOI to one variant and by title to another lands in one
    place rather than two; it is also why groups must be checked for internal
    coherence before anything is merged. See `coherence`.
    """
    parent = list(range(len(entries)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    buckets = collections.defaultdict(list)
    for index, record in enumerate(entries):
        for print_ in fingerprints(record):
            buckets[print_].append(index)
    for members in buckets.values():
        for other in members[1:]:
            root_a, root_b = find(members[0]), find(other)
            if root_a != root_b:
                parent[root_a] = root_b

    grouped = collections.defaultdict(list)
    for index in range(len(entries)):
        grouped[find(index)].append(entries[index])
    groups = [g for g in grouped.values() if len(g) > 1]
    return sorted(groups, key=lambda g: (-len(g), group_id(g)))


def group_id(group):
    """A stable identifier: the lowest original key in the group.

    Stable across runs and independent of file order, so that a decision
    recorded against a group still applies after the file is edited elsewhere.
    """
    return min(record.key.lower() for record in group)


# --- coherence -----------------------------------------------------------


def coherence(group):
    """Return None if GROUP is safe to merge, else why it is not.

    Three failures, all seen in real data:

    - Chaining pulled in a different paper. Bertin–Lacour–Rivoirard 2014
      ("Adaptive estimation of conditional density function") joined the
      Bertin–Klutchnikoff beta-kernel group through a shared fingerprint.
    - The variants carry different identifiers, which may mean one of them is
      wrong, or that a paper and its supplement have been conflated.
    - One of them carries no title at all. CrossRef answered a free-text
      query with a test account's record — a DOI, a publisher, and nothing
      else — and an empty signature agrees with everything. Absence of
      evidence is not agreement: unless a shared identifier vouches for them,
      a member with no title is a question, not a match.
    """
    dois = {record.doi for record in group if record.doi}
    if len(dois) > 1:
        return "several DOIs"
    eprints = {record.arxiv for record in group if record.arxiv}
    if len(eprints) > 1:
        return "several arXiv identifiers"

    vouched = (len(dois) == 1 and all(record.doi for record in group)) or (
        len(eprints) == 1 and all(record.arxiv for record in group)
    )
    if not vouched and any(not record.signature for record in group):
        return "no title to compare"

    signatures = {record.signature for record in group if record.signature}
    if not bib.same_work(signatures):
        return "titles disagree"
    return None


def winner(group):
    """The richest variant, the one a merge would keep.

    A proposal, not a decision: `bib.score` ranks how *complete* an entry is,
    which says nothing about which values are correct.
    """
    return min(group, key=bib.score)


def classify(groups):
    """Split GROUPS into ``(mergeable, review)``."""
    mergeable, review = [], []
    for group in groups:
        (review if coherence(group) else mergeable).append(group)
    return mergeable, review


# --- serialisation -------------------------------------------------------


def as_dict(group):
    """A JSON-serialisable view of one group.

    This is the interface a front-end works against — an Emacs buffer listing
    duplicates for selection, say — so it carries everything needed to decide
    without re-reading the .bib.
    """
    best = winner(group)
    return {
        "id": group_id(group),
        "reason": coherence(group),
        "target": best.target,
        "winner": best.key,
        "entries": [
            {
                "key": record.key,
                "type": record.type,
                "title": record.title,
                "year": record.year,
                "doi": record.doi,
                "arxiv": record.arxiv,
                "journal": record.journal,
                "fields": bib.count_fields(record.body),
                "origin": record.origin,
            }
            for record in sorted(group, key=bib.score)
        ],
    }


def summary(groups):
    mergeable, review = classify(groups)
    return {
        "groups": len(groups),
        "entries": sum(len(g) for g in groups),
        "mergeable": len(mergeable),
        "review": len(review),
        "removed_if_all_merged": sum(len(g) - 1 for g in groups),
    }
