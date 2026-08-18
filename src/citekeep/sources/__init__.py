"""Bibliographic sources, tried in order of trustworthiness.

zbMATH comes first because its records are curated; CrossRef catches
everything outside mathematics. The order matters and is not a detail: on an
entry both services know, zbMATH's version is the better one.
"""

from __future__ import annotations

from . import crossref, zbmath
from .base import NoResult, SourceError

#: Default order. First source that answers wins.
DEFAULT = (zbmath, crossref)

BY_NAME = {module.NAME: module for module in DEFAULT}

__all__ = [
    "BY_NAME",
    "DEFAULT",
    "NoResult",
    "SourceError",
    "crossref",
    "lookup",
    "zbmath",
]


def lookup(query, count=1, sources=DEFAULT):
    """Fetch BibTeX entries for QUERY, trying each source in turn.

    Returns ``(source_name, [entry, ...])``.

    A source that simply has no record is skipped silently — that is the
    normal case, not a failure. A source that is unreachable is remembered and
    reported only if *no* source succeeds, so a network hiccup on the first
    service does not mask a perfectly good answer from the second.
    """
    failures = []
    for module in sources:
        try:
            return module.NAME, module.fetch(query, count)
        except NoResult:
            continue
        except SourceError as exc:
            failures.append(str(exc))
    if failures:
        raise SourceError("; ".join(failures))
    raise NoResult(query)
