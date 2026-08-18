from citekeep import bib, duplicates, verify
from citekeep.model import SourceCandidate


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    fields.setdefault("title", "A title")
    return bib.render_entry("article", key, fields)


def record(text, origin="local"):
    (result,) = duplicates.records(text, origin)
    return result


def candidate(local, fetched, source="zbmath"):
    report = verify.report(local, [(source, fetched)])
    return report.candidates[0]


def test_report_compares_all_sources_field_by_field():
    local = record(entry("Smi23", title="Adaptive estimation", year="2022"))
    zbmath = record(
        entry("z", title="Adaptive estimation", year="2023", doi="10.1/a"), "zbmath"
    )
    crossref = record(
        entry(
            "c", title="Adaptive estimation", year="2023", doi="10.1/a", pages="1--20"
        ),
        "crossref",
    )
    result = verify.report(local, [("zbmath", zbmath), ("crossref", crossref)])
    years = next(field for field in result.fields if field.name == "year")
    assert years.sources == (("zbmath", "2023"), ("crossref", "2023"))
    assert years.agrees
    assert {field.name for field in result.fields} >= {"year", "doi", "pages"}


def test_a_shared_doi_vouches_for_a_reworded_record():
    local = record(entry("Smi23", title="Old prepublication title", doi="10.1/a"))
    fetched = record(entry("z", title="Published title", doi="10.1/a"), "zbmath")
    result = candidate(local, fetched)
    assert result.trusted_identity
    assert result.reason == "shared DOI"


def test_a_shared_doi_does_not_hide_a_conflicting_arxiv_identifier():
    local = record(
        entry(
            "Smi23",
            title="A title",
            doi="10.1/a",
            eprint="2101.00001",
            eprinttype="arXiv",
        )
    )
    fetched = record(
        entry(
            "z", title="A title", doi="10.1/a", eprint="2101.00002", eprinttype="arXiv"
        ),
        "zbmath",
    )
    result = candidate(local, fetched)
    assert not result.trusted_identity
    assert result.reason == "different arXiv identifiers"


def test_complete_only_fills_gaps_and_keeps_the_local_key():
    local = record(entry("Smi23", title="Local title", year="2022"))
    fetched = record(
        entry("z", title="Local title", year="2023", doi="10.1/a"), "zbmath"
    )
    result = verify.plan_refresh(local, candidate(local, fetched), "complete")
    updated = record(result.text)
    assert updated.key == "Smi23"
    assert updated.year == "2022"
    assert updated.doi == "10.1/a"


def test_selected_fields_can_correct_existing_values():
    local = record(entry("Smi23", title="Adaptive estimation", year="2022"))
    fetched = record(
        entry("z", title="Adaptive estimation", year="2023", doi="10.1/a"), "zbmath"
    )
    result = verify.plan_refresh(
        local, candidate(local, fetched), "selected", ["year", "doi"]
    )
    updated = record(result.text)
    assert updated.key == "Smi23"
    assert updated.year == "2023"
    assert updated.doi == "10.1/a"


def test_replace_preserves_key_master_link_and_project_metadata():
    local = record(
        entry(
            "Smi23",
            title="Bad title",
            year="2022",
            doi="10.1/a",
            file="papers/a.pdf",
            ckmasterkey="smith_adaptive_2023",
        )
    )
    fetched = record(
        entry(
            "z", title="Published title", year="2023", doi="10.1/a", journal="Annals"
        ),
        "zbmath",
    )
    result = verify.plan_refresh(local, candidate(local, fetched), "replace")
    updated = record(result.text)
    assert updated.key == "Smi23"
    assert updated.title == "Published title"
    assert updated.master_key == "smith_adaptive_2023"
    assert bib.get_field(updated.body, "file") == "papers/a.pdf"


def test_an_uncertain_source_cannot_replace_the_entry():
    local = record(entry("Smi23", title="Adaptive estimation"))
    fetched = record(entry("z", title="A completely different paper"), "crossref")
    untrusted = SourceCandidate("crossref", fetched, False, "titles disagree")
    try:
        verify.plan_refresh(local, untrusted, "replace")
    except ValueError as error:
        assert "uncertain" in str(error)
    else:
        raise AssertionError("an uncertain result was accepted")
