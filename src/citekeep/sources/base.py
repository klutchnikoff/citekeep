"""What every bibliographic source has in common.

A source knows how to talk to one web service and how to translate its answer
into a plain mapping of BibTeX field names to values. It never renders an
entry and never invents a citation key — `bib.render_entry` and
`bib.citation_key` do that, identically for all sources, so that the same
paper fetched from two services lands on the same key.
"""

from __future__ import annotations

import re

from .. import bib

TIMEOUT = 30

DOI_RE = re.compile(r"^(https?://(dx\.)?doi\.org/)?(10\.\d{4,}/\S+)$", re.IGNORECASE)


class NoResult(Exception):
    """The query ran and matched nothing.

    Distinct from a transport failure on purpose. Half of a working
    bibliography typically falls outside any given service's scope, so "not
    found" is an ordinary outcome and must not be reported as a breakage.
    """


class SourceError(Exception):
    """The service could not be reached, or answered something unusable."""


def extract_doi(text):
    """Return the bare DOI in TEXT, or None.

    Case is preserved: DOIs are case-insensitive for resolution, and services
    disagree on presentation — CrossRef lowercases, zbMATH keeps whatever the
    registrant deposited. Rewriting the case here would gratuitously change
    entries; `same_doi` is what comparisons should use.
    """
    match = DOI_RE.match((text or "").strip())
    return match.group(3) if match else None


def same_doi(left, right):
    """Do these two DOIs designate the same work?

    Folds case, because zbMATH and CrossRef present the same DOI differently
    and a naive comparison would see two papers where there is one.
    """
    return bool(left) and bool(right) and left.strip().lower() == right.strip().lower()


def free_text_query(body):
    """Build a search string from an entry that has no identifier.

    LaTeX has to go first: sending ``Gin\\'{e}`` raw makes the request fail in
    a way indistinguishable from "no such record", which once hid 53 silent
    failures in a single corpus.
    """
    title = bib.latex_clean(bib.get_field(body, "title"))
    author = bib.latex_clean(bib.get_field(body, "author"))
    first = author.split(" and ")[0].split(",")[0].strip()
    words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", title)[:6]
    if not words:
        return None
    return " ".join([first] + words) if first else " ".join(words)


def identifiers(body):
    """Identifiers usable to look an existing entry up, most reliable first.

    Yields ``(kind, value)`` with kind in ``doi``, ``zbl``, ``mr``.
    """
    doi = bib.get_field(body, "doi")
    if doi:
        yield "doi", re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip())
    zbl = bib.get_field(body, "zmnumber")
    if zbl:
        yield "zbl", zbl.strip().replace("Zbl", "").strip()
    mr = bib.get_field(body, "mrnumber")
    if mr:
        yield "mr", re.sub(r"^MR", "", mr.strip()).split()[0]
