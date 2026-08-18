"""zbMATH Open — the preferred source for mathematics.

Freely accessible since 2021, no API key. Records are curated by human
reviewers, where a publisher-deposit aggregator republishes whatever was
deposited. Measured on a 2400-entry corpus, zbMATH matched every field of
already-curated entries and added the arXiv identifier and MSC classification.

It covers mathematics and its applications only; roughly half of an applied
bibliography falls outside it. That is what `crossref` is for.
"""

from __future__ import annotations

import json
import re
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

NAME = "zbmath"
API = "https://api.zbmath.org/v1/document/_search"

# zbMATH document type -> BibTeX entry type. Anything unlisted becomes @article.
ENTRY_TYPES = {
    "journal article": "article",
    "book": "book",
    "collection article": "incollection",
    "book article": "incollection",
    "proceedings paper": "inproceedings",
    "thesis": "phdthesis",
}


def normalise_query(text):
    """Turn user input into the most precise query zbMATH accepts."""
    text = (text or "").strip()
    doi = extract_doi(text)
    if doi:
        return f"doi:{doi}"
    if re.match(r"^an:", text, re.IGNORECASE):
        return text
    return text


def query_for_entry(body):
    """Best available query for an existing entry, or None."""
    for kind, value in identifiers(body):
        if kind == "doi":
            return f"doi:{value}"
        if kind == "zbl":
            return f"an:{value}"
    return free_text_query(body)


def search(query, count=1):
    """Return raw zbMATH records for QUERY."""
    url = f"{API}?" + urllib.parse.urlencode(
        {"search_string": query, "results_per_page": count, "page": 0}
    )
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as fh:
            data = json.load(fh)
    except urllib.error.HTTPError as exc:
        # zbMATH answers 404 for an empty result set.
        if exc.code == 404:
            raise NoResult(query) from exc
        raise SourceError(f"zbMATH HTTP {exc.code}") from exc
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise SourceError(f"zbMATH unreachable: {exc}") from exc
    results = data.get("result") or []
    if not results:
        raise NoResult(query)
    return results


def to_fields(record):
    """Translate one zbMATH record into ``(entry_type, key, fields)``."""
    doc_type = record.get("document_type") or {}
    if isinstance(doc_type, dict):
        doc_type = doc_type.get("description") or ""
    entry_type = ENTRY_TYPES.get(str(doc_type).lower(), "article")

    title = ((record.get("title") or {}).get("title") or "").strip()
    authors = [
        a.get("name", "")
        for a in (record.get("contributors") or {}).get("authors") or []
    ]
    year = str(record.get("year") or "")

    source = record.get("source") or {}
    series = (source.get("series") or [{}])[0]
    links = {
        l.get("type"): l.get("identifier")
        for l in (record.get("links") or [])
        if l.get("type")
    }
    msc = [m.get("code") for m in record.get("msc") or [] if m.get("code")]

    fields = {
        "author": " and ".join(authors),
        "title": title,
        "journal": series.get("title") or "",
        "shortjournal": series.get("short_title") or "",
        "volume": series.get("volume") or "",
        "number": series.get("issue") or "",
        # BibTeX wants a double hyphen for page ranges.
        "pages": re.sub(r"(?<=\d)-(?=\d)", "--", source.get("pages") or ""),
        "year": year,
        "publisher": series.get("publisher") or "",
        "doi": links.get("doi") or "",
        "eprint": links.get("arxiv") or "",
        "eprinttype": "arXiv" if links.get("arxiv") else "",
        "zmnumber": record.get("identifier") or "",
        "mrclass": " ".join(msc),
        "keywords": ", ".join(k for k in record.get("keywords") or [] if k),
        "url": record.get("zbmath_url") or "",
    }
    return entry_type, bib.citation_key(authors, year, title), fields


def fetch(query, count=1):
    """Search zbMATH and return rendered BibTeX entries."""
    return [
        bib.render_entry(*to_fields(record))
        for record in search(normalise_query(query), count)
    ]
