"""Tests for entry rendering, CrossRef, and the source cascade."""

import os

import pytest

from citekeep import bib, sources
from citekeep.sources import base, crossref, zbmath

# --- rendering, shared by every source -----------------------------------


def test_render_orders_fields_predictably():
    out = bib.render_entry(
        "article",
        "k",
        {"year": "2020", "title": "T", "author": "Doe, J.", "doi": "10.1/x"},
    )
    names = [n for n, _v in bib.parse_fields(next(bib.iter_entries(out))[3])]
    assert names == ["author", "title", "year", "doi"]


def test_render_drops_empty_values():
    """An empty field is worse than an absent one: it reads as absent while
    blocking a later fill."""
    out = bib.render_entry("article", "k", {"title": "T", "volume": "", "pages": "   "})
    assert "volume" not in out and "pages" not in out


def test_render_keeps_unknown_fields():
    """A field a new source invents must not vanish silently."""
    out = bib.render_entry("article", "k", {"title": "T", "hal_id": "hal-042"})
    body = next(bib.iter_entries(out))[3]
    assert bib.get_field(body, "hal_id") == "hal-042"


def test_render_survives_an_entry_with_nothing_in_it():
    assert list(bib.iter_entries(bib.render_entry("misc", "k", {}))) != []


# --- shared identifier handling ------------------------------------------


def test_extract_doi_accepts_bare_and_url_forms():
    assert base.extract_doi("10.1214/13-AOS1158") == "10.1214/13-AOS1158"
    assert (
        base.extract_doi("https://doi.org/10.1214/13-AOS1158") == "10.1214/13-AOS1158"
    )
    assert base.extract_doi("Carroll bandwidth") is None


def test_identifiers_are_yielded_most_reliable_first():
    body = "mrnumber = {MR3161446}, zmnumber = {1292.62059}, doi = {10.1/x},"
    assert [kind for kind, _v in base.identifiers(body)] == ["doi", "zbl", "mr"]


def test_identifiers_strip_their_prefixes():
    found = dict(base.identifiers("mrnumber = {MR3161446 (2003m:62105)},"))
    assert found["mr"] == "3161446"


# --- CrossRef ------------------------------------------------------------

CROSSREF_RECORD = {
    "type": "journal-article",
    "title": ["Unexpected properties of bandwidth choice"],
    "author": [
        {"family": "Carroll", "given": "Raymond J."},
        {"family": "Delaigle", "given": "Aurore"},
    ],
    "container-title": ["The Annals of Statistics"],
    "short-container-title": ["Ann. Statist."],
    "volume": "41",
    "issue": "6",
    "page": "2739-2767",
    "issued": {"date-parts": [[2013, 12]]},
    "DOI": "10.1214/13-AOS1158",
    "publisher": "Institute of Mathematical Statistics",
}


def test_crossref_conversion():
    entry_type, key, fields = crossref.to_fields(CROSSREF_RECORD)
    assert entry_type == "article"
    assert fields["author"] == "Carroll, Raymond J. and Delaigle, Aurore"
    assert fields["pages"] == "2739--2767"
    assert fields["year"] == "2013"
    assert key == "carroll_unexpected_2013"


def test_both_sources_agree_on_the_citation_key():
    """The point of factoring key construction out of the sources.

    The same paper fetched from either service must land on one key; two keys
    for one paper is a mistake no later deduplication can undo.
    """
    from .test_zbmath import RECORD as ZB_RECORD

    assert zbmath.to_fields(ZB_RECORD)[1] == crossref.to_fields(CROSSREF_RECORD)[1]


def test_crossref_falls_back_through_date_fields():
    record = dict(CROSSREF_RECORD)
    del record["issued"]
    record["published-print"] = {"date-parts": [[2011]]}
    assert crossref.to_fields(record)[2]["year"] == "2011"


def test_crossref_ignores_a_zbl_number_it_cannot_use():
    """CrossRef knows nothing of zbMATH numbers, so such an entry must fall
    back to free text rather than issue a query that cannot match."""
    body = "title = {Adaptive estimation of density}, zmnumber = {1292.62059},"
    query = crossref.query_for_entry(body)
    assert query and "1292.62059" not in query


# --- the cascade ---------------------------------------------------------


class _Stub:
    def __init__(self, name, behaviour):
        self.NAME, self._behaviour = name, behaviour

    def fetch(self, query, count=1):
        if self._behaviour == "found":
            return [f"@article{{{self.NAME},\n}}\n"]
        raise (
            sources.NoResult(query)
            if self._behaviour == "empty"
            else sources.SourceError(f"{self.NAME} down")
        )

    def query_for_entry(self, body):
        return "q"


def test_first_source_that_answers_wins():
    name, _ = sources.lookup("q", sources=(_Stub("a", "found"), _Stub("b", "found")))
    assert name == "a"


def test_an_empty_source_is_skipped_silently():
    """Half a bibliography falls outside any given service; that is normal."""
    name, _ = sources.lookup("q", sources=(_Stub("a", "empty"), _Stub("b", "found")))
    assert name == "b"


def test_a_broken_source_does_not_mask_a_good_answer():
    name, _ = sources.lookup("q", sources=(_Stub("a", "error"), _Stub("b", "found")))
    assert name == "b"


def test_failures_are_reported_when_nothing_succeeds():
    with pytest.raises(sources.SourceError):
        sources.lookup("q", sources=(_Stub("a", "error"), _Stub("b", "empty")))


def test_no_result_when_every_source_is_simply_empty():
    with pytest.raises(sources.NoResult):
        sources.lookup("q", sources=(_Stub("a", "empty"), _Stub("b", "empty")))


# --- network -------------------------------------------------------------

network = pytest.mark.skipif(
    not os.environ.get("CITEKEEP_NETWORK_TESTS"),
    reason="set CITEKEEP_NETWORK_TESTS=1 to exercise the live APIs",
)


@network
def test_live_crossref_by_doi():
    """CrossRef lowercases DOIs, zbMATH preserves the registrant's case.

    DOIs are case-insensitive by specification, so both are correct — but any
    comparison across sources has to fold case, or the same paper looks like
    two.
    """
    entries = crossref.fetch("10.1214/13-AOS1158")
    body = next(bib.iter_entries(entries[0]))[3]
    assert bib.get_field(body, "doi").lower() == "10.1214/13-aos1158"


@network
def test_live_cascade_falls_through_to_crossref():
    """A machine-learning paper: outside zbMATH, inside CrossRef."""
    name, _entries = sources.lookup("10.1145/3292500.3330701")
    assert name == "crossref"


def test_same_doi_folds_case():
    """zbMATH gives 10.1214/13-AOS1158, CrossRef gives 10.1214/13-aos1158."""
    assert base.same_doi("10.1214/13-AOS1158", "10.1214/13-aos1158")
    assert not base.same_doi("10.1214/13-AOS1158", "10.1214/20-EJS1682")
    assert not base.same_doi("", "10.1/x")
