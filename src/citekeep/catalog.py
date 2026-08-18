"""Searching a project view first, then the canonical master."""

from __future__ import annotations

import re

from . import bib, library, project
from .model import MaterializePlan, SearchHit, SearchResults


def _words(text):
    cleaned = bib.latex_clean(text).lower()
    return tuple(re.findall(r"[a-z0-9]+", cleaned))


def _score(record, query):
    words = _words(query)
    if not words:
        return 1
    authors = " ".join(record.names)
    haystack = " ".join(
        (
            record.key,
            record.title,
            authors,
            record.year,
            record.journal,
            record.doi,
            record.arxiv,
        )
    ).lower()
    if not all(word in haystack for word in words):
        return 0
    score = sum(10 for word in words if word in record.title.lower())
    score += sum(6 for word in words if word in authors.lower())
    score += sum(4 for word in words if word in record.key.lower())
    if record.key.lower() == query.strip().lower():
        score += 100
    if record.doi and record.doi == query.strip().lower():
        score += 100
    return score or 1


def _linked_master(index_, by_key, record):
    if record.master_key:
        return by_key.get(record.master_key)
    match = library.look_up(index_, record)
    if match.kind in {"unchanged", "enrich"} and len(match.existing) == 1:
        return match.existing[0]
    return None


def search(master_records, local_records, query):
    """Return matching local records followed by unrepresented master works."""
    master_index = library.index(master_records)
    master_by_key = {record.key: record for record in master_records}
    represented = set()
    local_hits = []
    for record in local_records:
        canonical = _linked_master(master_index, master_by_key, record)
        if canonical:
            represented.add(canonical.key)
        score = _score(record, query)
        if score:
            local_hits.append(
                SearchHit(
                    "local",
                    record.key,
                    canonical.key if canonical else None,
                    record,
                    score,
                )
            )

    master_hits = []
    for record in master_records:
        if record.key in represented:
            continue
        score = _score(record, query)
        if score:
            master_hits.append(
                SearchHit("master", record.key, record.key, record, score)
            )

    ordering = lambda hit: (
        -hit.score,
        hit.record.title.lower(),
        hit.citation_key.lower(),
    )
    return SearchResults(
        tuple(sorted(local_hits, key=ordering)),
        tuple(sorted(master_hits, key=ordering)),
    )


def classify_fetched(master_records, local_records, record):
    """Classify an online RECORD in the editor's local-then-master order.

    A materialised local alias and its canonical master record deliberately
    describe the same work.  Putting both into one fingerprint index would
    therefore manufacture an ambiguous two-record match.  The project view
    wins first because its key is the one valid in the current document.
    """
    local_match = library.look_up(library.index(local_records), record)
    if local_match.kind != "new":
        return local_match
    return library.look_up(library.index(master_records), record)


def materialize(local_text, master_record):
    """Plan copying MASTER_RECORD into a project under its canonical key."""
    text, action = project.write_record(
        local_text, master_record.raw, master_record.key
    )
    return MaterializePlan(text, master_record.key, action, master_record.key)
