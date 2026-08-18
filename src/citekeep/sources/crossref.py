"""CrossRef — the fallback for anything outside mathematics.

CrossRef indexes essentially every article that has a DOI, across all fields.
Its metadata is deposited by publishers rather than curated, so it is less
reliable than zbMATH where both have the record: measured on a sample of
already-curated entries, it added only `publisher` and sometimes lacked pages
or volume.

It earns its place on everything zbMATH does not cover — machine learning,
engineering, conference proceedings — which is a large part of an applied
bibliography.

CrossRef asks callers to identify themselves. A mailto in the User-Agent moves
the request to their "polite" pool, which is both courteous and faster.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .. import bib
from .base import (
    TIMEOUT,
    NoResult,
    SourceError,
    extract_doi,
    free_text_query,
    identifiers,
)

NAME = "crossref"
API = "https://api.crossref.org/works"

# CrossRef type -> BibTeX entry type.
ENTRY_TYPES = {
    "journal-article": "article",
    "book": "book",
    "book-chapter": "incollection",
    "proceedings-article": "inproceedings",
    "dissertation": "phdthesis",
    "posted-content": "misc",
    "report": "techreport",
}


def _user_agent():
    mail = os.environ.get("CITEKEEP_MAILTO")
    base = "citekeep (https://github.com/klutchnikoff/citekeep)"
    return f"{base} mailto:{mail}" if mail else base


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NoResult(url) from exc
        raise SourceError(f"CrossRef HTTP {exc.code}") from exc
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise SourceError(f"CrossRef unreachable: {exc}") from exc


def query_for_entry(body):
    """Best available query for an existing entry, or None.

    CrossRef knows nothing of zbMATH or MathSciNet numbers, so an entry
    identified only by those falls back to free text.
    """
    for kind, value in identifiers(body):
        if kind == "doi":
            return value
    return free_text_query(body)


def search(query, count=1):
    """Return raw CrossRef records for QUERY, which may be a DOI or free text."""
    doi = extract_doi(query) or (query if query.startswith("10.") else None)
    if doi:
        data = _get(f"{API}/{urllib.parse.quote(doi)}")
        message = data.get("message")
        return [message] if message else []

    url = f"{API}?" + urllib.parse.urlencode(
        {"query.bibliographic": query, "rows": count}
    )
    data = _get(url)
    items = ((data.get("message") or {}).get("items")) or []
    if not items:
        raise NoResult(query)
    return items


def _authors(record):
    out = []
    for person in record.get("author") or []:
        family, given = person.get("family"), person.get("given")
        if family and given:
            out.append(f"{family}, {given}")
        elif family:
            out.append(family)
        elif person.get("name"):
            out.append(person["name"])
    return out


def _year(record):
    for key in ("published-print", "published-online", "issued", "created"):
        parts = ((record.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            return str(parts[0])
    return ""


def to_fields(record):
    """Translate one CrossRef record into ``(entry_type, key, fields)``."""
    entry_type = ENTRY_TYPES.get(record.get("type", ""), "article")
    title = (record.get("title") or [""])[0].strip()
    authors = _authors(record)
    year = _year(record)
    container = (record.get("container-title") or [""])[0]
    short = (record.get("short-container-title") or [""])[0]

    fields = {
        "author": " and ".join(authors),
        "title": title,
        "journal": container,
        "shortjournal": short,
        "volume": record.get("volume") or "",
        "number": record.get("issue") or "",
        "pages": (record.get("page") or "").replace("-", "--"),
        "year": year,
        "publisher": record.get("publisher") or "",
        "doi": record.get("DOI") or "",
        "isbn": (record.get("ISBN") or [""])[0],
        "issn": (record.get("ISSN") or [""])[0],
        "url": record.get("URL") or "",
    }
    return entry_type, bib.citation_key(authors, year, title), fields


def fetch(query, count=1):
    """Search CrossRef and return rendered BibTeX entries."""
    records = search((query or "").strip(), count)
    if not records:
        raise NoResult(query)
    return [bib.render_entry(*to_fields(record)) for record in records]
