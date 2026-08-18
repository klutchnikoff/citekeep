"""Tests for the zbMATH client.

Conversion is tested against a captured API response, so the suite runs
offline and stays stable when the service changes. Two tests hit the network
and are skipped unless CITEKEEP_NETWORK_TESTS is set.
"""

import os

import pytest

from citekeep import bib, sources
from citekeep.sources import zbmath

# A real response, trimmed to the fields the converter reads.
RECORD = {
    "document_type": {"description": "journal article"},
    "title": {"title": "Unexpected properties of bandwidth choice"},
    "contributors": {
        "authors": [
            {"name": "Carroll, Raymond J."},
            {"name": "Delaigle, Aurore"},
            {"name": "Hall, Peter"},
        ]
    },
    "year": 2013,
    "identifier": "1292.62059",
    "zbmath_url": "https://zbmath.org/6279910",
    "source": {
        "pages": "2739-2767",
        "series": [
            {
                "title": "The Annals of Statistics",
                "short_title": "Ann. Stat.",
                "volume": "41",
                "issue": "6",
                "publisher": "Institute of Mathematical Statistics",
            }
        ],
    },
    "links": [
        {"type": "doi", "identifier": "10.1214/13-AOS1158"},
        {"type": "arxiv", "identifier": "1312.5082"},
    ],
    "msc": [{"code": "62G08"}],
    "keywords": ["bandwidth", "functional data"],
}


@pytest.fixture
def entry_body():
    return next(bib.iter_entries(bib.render_entry(*zbmath.to_fields(RECORD))))[3]


def test_conversion_produces_a_parsable_entry():
    entries = list(bib.iter_entries(bib.render_entry(*zbmath.to_fields(RECORD))))
    assert len(entries) == 1
    assert bib.is_wellformed(entries[0][3])


def test_core_fields(entry_body):
    assert bib.get_field(entry_body, "journal") == "The Annals of Statistics"
    assert bib.get_field(entry_body, "volume") == "41"
    assert bib.get_field(entry_body, "number") == "6"
    assert bib.get_field(entry_body, "year") == "2013"


def test_authors_are_joined_the_bibtex_way(entry_body):
    assert bib.get_field(entry_body, "author") == (
        "Carroll, Raymond J. and Delaigle, Aurore and Hall, Peter"
    )


def test_page_range_uses_a_double_hyphen(entry_body):
    """`2739-2767` from the API must become `2739--2767` for LaTeX."""
    assert bib.get_field(entry_body, "pages") == "2739--2767"


def test_fields_crossref_does_not_provide(entry_body):
    """The reason zbMATH is preferred for mathematics."""
    assert bib.get_field(entry_body, "shortjournal") == "Ann. Stat."
    assert bib.get_field(entry_body, "eprint") == "1312.5082"
    assert bib.get_field(entry_body, "mrclass") == "62G08"
    assert bib.get_field(entry_body, "zmnumber") == "1292.62059"


def test_citation_key_matches_the_zotero_convention():
    """Records must land on the key an existing library already uses.

    Getting this wrong means the same paper lives under two keys, which no
    later deduplication can undo.
    """
    key = next(bib.iter_entries(bib.render_entry(*zbmath.to_fields(RECORD))))[1]
    assert key == "carroll_unexpected_2013"


def test_citation_key_skips_stopwords():
    assert (
        bib.citation_key(["Doe, Jane"], "2020", "On the estimation of x")
        == "doe_estimation_2020"
    )


def test_citation_key_survives_missing_data():
    assert bib.citation_key([], "", "") == "anon_untitled_nd"


# --- query construction --------------------------------------------------


def test_bare_doi_becomes_a_doi_query():
    assert zbmath.normalise_query("10.1214/13-AOS1158") == "doi:10.1214/13-AOS1158"
    assert (
        zbmath.normalise_query("https://doi.org/10.1214/13-AOS1158")
        == "doi:10.1214/13-AOS1158"
    )


def test_free_text_is_left_alone():
    assert zbmath.normalise_query("Carroll bandwidth") == "Carroll bandwidth"


def test_query_for_entry_prefers_the_doi():
    body = "title = {T}, doi = {10.1/x}, zmnumber = {1234.56789},"
    assert zbmath.query_for_entry(body) == "doi:10.1/x"


def test_query_for_entry_falls_back_to_the_zbl_number():
    assert (
        zbmath.query_for_entry("title = {T}, zmnumber = {1234.56789},")
        == "an:1234.56789"
    )


def test_query_for_entry_strips_latex_from_free_text():
    """53 queries in a real corpus failed because of this, silently."""
    body = r"title = {Adaptive \'{e}stimation of density}, author = {Gin\'{e}, E.},"
    query = zbmath.query_for_entry(body)
    assert "\\" not in query and "{" not in query
    assert query.startswith("Gine")


def test_query_for_entry_gives_up_without_a_usable_title():
    assert zbmath.query_for_entry("author = {Doe, J.},") is None


# --- network -------------------------------------------------------------

network = pytest.mark.skipif(
    not os.environ.get("CITEKEEP_NETWORK_TESTS"),
    reason="set CITEKEEP_NETWORK_TESTS=1 to exercise the live API",
)


@network
def test_live_lookup_by_doi():
    entries = zbmath.fetch("10.1214/13-AOS1158")
    key = next(bib.iter_entries(entries[0]))[1]
    assert key == "carroll_unexpected_2013"


@network
def test_live_missing_record_raises_noresult():
    """404 means "nothing matched", not "the service is down"."""
    with pytest.raises(sources.NoResult):
        zbmath.fetch("Zzzq Wxyv Qqjk Nonexistent Paper Title 12345")
