"""Tests for the command line, exercised through main() as a user would."""

import io
import json
from pathlib import Path

import pytest

from citekeep import bib, cli, duplicates, sync
from citekeep import verify as verification


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    return bib.render_entry("article", key, fields)


LIBRARY = "%% master.bib\n\n" + entry(
    "doe_adaptive_2019",
    title="Adaptive estimation",
    year="2019",
    doi="10.1/right",
    journal="Ann. Statist.",
)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.delenv("CITEKEEP_LIBRARY", raising=False)
    monkeypatch.setattr(cli, "CONFIG", tmp_path / "absent.toml")
    master = tmp_path / "master.bib"
    master.write_text(LIBRARY, encoding="utf-8")
    return tmp_path, master


# --- locating the library ------------------------------------------------


def test_the_flag_wins_over_the_environment(paths, monkeypatch):
    tmp_path, master = paths
    monkeypatch.setenv("CITEKEEP_LIBRARY", str(tmp_path / "other.bib"))
    assert cli.library_path(str(master)) == master


def test_the_environment_is_used_when_no_flag(paths, monkeypatch):
    _tmp, master = paths
    monkeypatch.setenv("CITEKEEP_LIBRARY", str(master))
    assert cli.library_path() == master


def test_the_config_file_is_the_last_resort(paths, monkeypatch):
    tmp_path, master = paths
    config = tmp_path / "config.toml"
    config.write_text(f'library = "{master}"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG", config)
    assert cli.library_path() == master


def test_no_library_configured_is_reported_not_crashed(paths, capsys):
    assert cli.main(["sync", "--bib", "whatever.bib"]) == 2
    assert "no library configured" in capsys.readouterr().err


# --- where ---------------------------------------------------------------


def test_where_prints_the_resolved_path(paths, capsys):
    """An editor asks rather than reimplementing the resolution order."""
    _tmp, master = paths
    assert cli.main(["where", "--library", str(master)]) == 0
    assert capsys.readouterr().out.strip() == str(master)


def test_where_says_when_the_library_is_absent(paths, capsys):
    tmp_path, _master = paths
    absent = tmp_path / "nope.bib"
    assert cli.main(["where", "--library", str(absent), "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": 1,
        "library": str(absent),
        "exists": False,
    }


# --- editor protocol -----------------------------------------------------


def feed(monkeypatch, text):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(text))


def test_editor_add_places_a_record_under_the_library_key(paths, monkeypatch):
    """Search once, choose, then send the record here — no second request."""
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "whatever",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            pages="1--20",
        ),
    )
    assert (
        cli.main(
            ["editor", "add-record", "--into", str(target), "--library", str(master)]
        )
        == 0
    )
    assert "doe_adaptive_2019" in target.read_text()


def test_editor_add_materialises_master_values_and_only_completes_its_gaps(
    paths, monkeypatch
):
    """An online spelling must not become a project/master disagreement."""
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "whatever",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="The Annals of Statistics",
            pages="1--20",
        ),
    )
    assert (
        cli.main(
            ["editor", "add-record", "--into", str(target), "--library", str(master)]
        )
        == 0
    )
    text = target.read_text()
    assert "journal = {Ann. Statist.}" in text
    assert "pages = {1--20}" in text
    assert "The Annals of Statistics" not in text
    follow_up = sync.plan(master.read_text(), text, {})
    assert not follow_up.conflicts
    assert follow_up.master_enrichments == ("doe_adaptive_2019",)


def test_editor_add_can_resolve_a_key_collision_as_distinct(paths, monkeypatch, capsys):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "remote",
            title="Adaptive smoothing",
            year="2019",
            doi="10.1/other",
        ),
    )
    assert (
        cli.main(
            [
                "editor",
                "add-record",
                "--into",
                str(target),
                "--library",
                str(master),
                "--decision",
                "distinct",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["match"]["kind"] == "new"
    assert data["match"]["key"] == "doe_adaptive_2019a"
    assert data["written"]["key"] == "doe_adaptive_2019a"
    assert "@article{doe_adaptive_2019a," in target.read_text()


def test_editor_add_can_skip_a_conflict(paths, monkeypatch, capsys):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "remote",
            title="Adaptive smoothing",
            year="2019",
            doi="10.1/other",
        ),
    )
    assert (
        cli.main(
            [
                "editor",
                "add-record",
                "--into",
                str(target),
                "--library",
                str(master),
                "--decision",
                "skip",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["match"]["kind"] == "skip"
    assert data["written"] is None
    assert not target.exists()


def test_editor_add_honours_skip_even_when_nothing_looks_conflicted(
    paths, monkeypatch, capsys
):
    """A refusal does not depend on a classification.

    The editor asks about the conflict it saw when the record was fetched;
    the command reclassifies afterwards. If the files moved in between and
    nothing resembles the record any more, the answer still stands.
    """
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "shannon_mathematical_1948",
            title="A Mathematical Theory of Communication",
            year="1948",
            doi="10.1002/j.1538-7305.1948.tb01338.x",
        ),
    )
    assert (
        cli.main(
            [
                "editor",
                "add-record",
                "--into",
                str(target),
                "--library",
                str(master),
                "--decision",
                "skip",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["match"]["kind"] == "skip"
    assert data["written"] is None
    assert not target.exists()


def test_editor_add_can_resolve_a_conflict_as_the_same_work(paths, monkeypatch, capsys):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "remote",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/other",
        ),
    )
    assert (
        cli.main(
            [
                "editor",
                "add-record",
                "--into",
                str(target),
                "--library",
                str(master),
                "--decision",
                "same",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["match"]["kind"] == "unchanged"
    assert data["match"]["key"] == "doe_adaptive_2019"
    text = target.read_text()
    body = next(bib.iter_entries(text))[3]
    assert bib.get_field(body, "doi") == "10.1/right"
    assert "10.1/other" not in text


def test_editor_add_refuses_a_record_that_needs_a_decision(paths, monkeypatch):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    feed(
        monkeypatch,
        entry(
            "x", title="Minimax rates under dependence", year="2019", doi="10.1/right"
        ),
    )
    assert (
        cli.main(
            ["editor", "add-record", "--into", str(target), "--library", str(master)]
        )
        == 1
    )
    assert not target.exists()


def test_editor_add_never_writes_to_the_library(paths, monkeypatch):
    tmp_path, master = paths
    before = master.read_text()
    feed(
        monkeypatch,
        entry("x", title="Wavelet thresholding", year="2005", author="Smith, Alice"),
    )
    cli.main(
        [
            "editor",
            "add-record",
            "--into",
            str(tmp_path / "refs.bib"),
            "--library",
            str(master),
        ]
    )
    assert master.read_text() == before


def test_editor_add_rejects_non_entry_input(paths, monkeypatch, capsys):
    tmp_path, master = paths
    feed(monkeypatch, "bonjour")
    assert (
        cli.main(
            [
                "editor",
                "add-record",
                "--into",
                str(tmp_path / "refs.bib"),
                "--library",
                str(master),
            ]
        )
        == 2
    )
    assert "no single BibTeX entry" in capsys.readouterr().err


# --- search --------------------------------------------------------------


def fake_results(monkeypatch, *texts):
    monkeypatch.setattr(cli.sources, "lookup", lambda *a, **k: ("zbmath", list(texts)))


def test_search_annotates_every_result_with_what_the_library_knows(
    paths, monkeypatch, capsys
):
    """The point of the list: you can see, before choosing, which results you
    already have."""
    _tmp, master = paths
    fake_results(
        monkeypatch,
        entry(
            "a",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
        ),
        entry(
            "b",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            pages="1--20",
        ),
        entry("c", title="Wavelet thresholding", year="2005", author="Smith, Alice"),
    )
    cli.main(["fetch", "estimation", "--library", str(master), "--json"])
    view = json.loads(capsys.readouterr().out)
    kinds = [r["match"]["kind"] for r in view["results"]]
    assert kinds == ["unchanged", "enrich", "new"]
    assert view["results"][0]["match"]["key"] == "doe_adaptive_2019"


def test_search_gives_an_author_line_for_picking(paths, monkeypatch, capsys):
    _tmp, master = paths
    fake_results(
        monkeypatch,
        entry(
            "a",
            title="Something",
            year="2013",
            author="Carroll, R. J. and Delaigle, A. and Hall, P.",
        ),
    )
    cli.main(["fetch", "x", "--library", str(master), "--json"])
    view = json.loads(capsys.readouterr().out)
    assert view["results"][0]["authors"] == "Carroll et al."


def test_search_writes_nothing_without_take(paths, monkeypatch):
    tmp_path, master = paths
    fake_results(
        monkeypatch,
        entry("a", title="Wavelet thresholding", year="2005", author="Smith, Alice"),
    )
    cli.main(
        [
            "fetch",
            "wavelet",
            "--library",
            str(master),
            "--into",
            str(tmp_path / "refs.bib"),
        ]
    )
    assert not (tmp_path / "refs.bib").exists()


def test_take_writes_the_chosen_result(paths, monkeypatch, capsys):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    fake_results(
        monkeypatch,
        entry("a", title="Adaptive estimation", year="2019", doi="10.1/right"),
        entry(
            "smith_wavelet_2005",
            title="Wavelet thresholding",
            year="2005",
            author="Smith, Alice",
        ),
    )
    cli.main(
        [
            "fetch",
            "x",
            "--library",
            str(master),
            "--into",
            str(target),
            "--take",
            "smith_wavelet_2005",
        ]
    )
    assert "smith_wavelet_2005" in target.read_text()
    assert "Adaptive estimation" not in target.read_text()


def test_take_uses_the_key_the_library_already_uses(paths, monkeypatch):
    """Choosing a result the library already has must not create a second
    name for it."""
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    fake_results(
        monkeypatch,
        entry(
            "zb_2019",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            pages="1--20",
        ),
    )
    cli.main(
        [
            "fetch",
            "x",
            "--library",
            str(master),
            "--into",
            str(target),
            "--take",
            "zb_2019",
        ]
    )
    assert "doe_adaptive_2019" in target.read_text()


def test_take_uses_a_local_alias_instead_of_seeing_two_matches(
    paths, monkeypatch, capsys
):
    tmp_path, master = paths
    target = tmp_path / "refs.bib"
    target.write_text(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            ckmasterkey="doe_adaptive_2019",
        )
    )
    fake_results(
        monkeypatch,
        entry("zb_2019", title="Adaptive estimation", year="2019", doi="10.1/right"),
    )
    assert (
        cli.main(
            [
                "fetch",
                "x",
                "--library",
                str(master),
                "--into",
                str(target),
                "--take",
                "zb_2019",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["results"][0]["match"]["key"] == "Doe19"
    assert data["written"]["action"] == "unchanged"


def test_take_refuses_a_result_that_needs_a_decision(paths, monkeypatch, capsys):
    tmp_path, master = paths
    fake_results(
        monkeypatch,
        entry(
            "zb", title="Minimax rates under dependence", year="2019", doi="10.1/right"
        ),
    )
    assert (
        cli.main(
            [
                "fetch",
                "x",
                "--library",
                str(master),
                "--into",
                str(tmp_path / "refs.bib"),
                "--take",
                "zb",
            ]
        )
        == 2
    )
    assert "decide before taking it" in capsys.readouterr().err


def test_take_an_unknown_key_is_reported(paths, monkeypatch, capsys):
    tmp_path, master = paths
    fake_results(monkeypatch, entry("a", title="X", year="2000"))
    assert (
        cli.main(
            [
                "fetch",
                "x",
                "--library",
                str(master),
                "--into",
                str(tmp_path / "refs.bib"),
                "--take",
                "nope",
            ]
        )
        == 2
    )
    assert "not among the results" in capsys.readouterr().err


def test_a_web_query_matching_nothing_is_reported(paths, monkeypatch, capsys):
    _tmp, master = paths

    def empty(*a, **k):
        raise cli.sources.NoResult("nothing")

    monkeypatch.setattr(cli.sources, "lookup", empty)
    assert cli.main(["fetch", "zzz", "--library", str(master)]) == 2
    assert "no record found" in capsys.readouterr().err


# --- local then master search -------------------------------------------


def test_search_groups_local_results_before_master(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "project.bib"
    local.write_text(
        entry(
            "LocalSmith", author="Smith, Alice", title="Local Smith paper", year="2020"
        )
    )
    assert (
        cli.main(
            [
                "search",
                "smith",
                "--local",
                str(local),
                "--library",
                str(master),
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert [item["citation_key"] for item in data["local"]] == ["LocalSmith"]


def test_search_hides_a_master_work_represented_by_a_local_alias(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "project.bib"
    local.write_text(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            ckmasterkey="doe_adaptive_2019",
        )
    )
    cli.main(
        [
            "search",
            "adaptive",
            "--local",
            str(local),
            "--library",
            str(master),
            "--json",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert [item["citation_key"] for item in data["local"]] == ["Doe19"]
    assert data["master"] == []


def test_search_without_query_returns_the_complete_editor_catalog(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "project.bib"
    local.write_text(
        entry(
            "LocalSmith",
            author="Smith, Alice and Doe, Bob",
            title="Local paper",
            year="2020",
        )
    )
    assert (
        cli.main(["search", "--local", str(local), "--library", str(master), "--json"])
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert [item["citation_key"] for item in data["local"]] == ["LocalSmith"]
    assert data["local"][0]["authors_full"] == "Smith, Alice and Doe, Bob"
    assert data["master"]


# --- status and unified sync --------------------------------------------


def test_sync_plans_without_writing(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry("Smi05", author="Smith, Alice", title="Wavelet thresholding", year="2005")
    )
    before = master.read_text()
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["master_added"] == 1
    assert not data["applied"]
    assert master.read_text() == before
    assert "ckmasterkey" not in local.read_text()


def test_sync_rejects_the_master_as_project_bibliography(paths, capsys):
    tmp_path, master = paths
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(master),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
            ]
        )
        == 2
    )
    assert "project bibliography cannot be the master" in (capsys.readouterr().err)


def test_sync_only_writes_with_apply(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry("Smi05", author="Smith, Alice", title="Wavelet thresholding", year="2005")
    )
    cli.main(
        [
            "sync",
            "--bib",
            str(local),
            "--project",
            str(tmp_path),
            "--library",
            str(master),
        ]
    )
    assert "smith_wavelet_2005" not in master.read_text()
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--apply",
            ]
        )
        == 0
    )
    assert "smith_wavelet_2005" in master.read_text()
    assert "ckmasterkey" in local.read_text()


def test_sync_reports_field_values_and_can_promote_the_reviewed_local_value(
    paths, capsys
):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2020",
            doi="10.1/right",
            ckmasterkey="doe_adaptive_2019",
        )
    )

    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--json",
            ]
        )
        == 1
    )
    conflict = json.loads(capsys.readouterr().out)["conflicts"][0]
    assert conflict["fields"] == [{"name": "year", "master": "2019", "local": "2020"}]

    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--use-local",
                "Doe19:year",
                "--apply",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["master"]["corrected"] == [
        {"key": "doe_adaptive_2019", "field": "year"}
    ]
    assert duplicates.records(master.read_text())[0].year == "2020"


def test_sync_can_keep_the_master_value(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2020",
            doi="10.1/right",
            ckmasterkey="doe_adaptive_2019",
        )
    )
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--keep-master",
                "Doe19:year",
                "--apply",
            ]
        )
        == 0
    )
    assert duplicates.records(local.read_text())[0].year == "2019"


def test_sync_resolves_identity_conflicts(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry("Foreign", title="Retitled work", year="2019", doi="10.1/right")
    )
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--json",
            ]
        )
        == 1
    )
    conflict = json.loads(capsys.readouterr().out)["conflicts"][0]
    assert conflict["answers"] == ["same", "distinct", "skip"]
    assert conflict["incoming"]["key"] == "Foreign"

    answers = tmp_path / "identity-decisions.txt"
    answers.write_text("same Foreign\n")
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--resolve",
                str(answers),
                "--apply",
            ]
        )
        == 0
    )
    assert duplicates.records(local.read_text())[0].master_key == ("doe_adaptive_2019")


def test_a_malformed_field_resolution_file_is_rejected(paths, tmp_path, capsys):
    _tmp, master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2020",
            doi="10.1/right",
            ckmasterkey="doe_adaptive_2019",
        )
    )
    answers = tmp_path / "answers.txt"
    answers.write_text("promote Doe19 year\n")
    assert (
        cli.main(
            [
                "sync",
                "--bib",
                str(local),
                "--project",
                str(tmp_path),
                "--library",
                str(master),
                "--resolve-fields",
                str(answers),
                "--apply",
            ]
        )
        == 2
    )
    assert "not field decisions" in capsys.readouterr().err


def test_init_creates_a_new_master(tmp_path, capsys):
    master = tmp_path / "config" / "master.bib"
    assert cli.main(["init", "--library", str(master), "--json"]) == 0
    assert master.read_text() == "%% citekeep master bibliography\n"
    assert json.loads(capsys.readouterr().out)["created"] is True


def test_emacs_path_points_to_the_distributed_editor_package(capsys):
    assert cli.main(["emacs-path"]) == 0
    path = Path(capsys.readouterr().out.strip())
    assert path.name == "citekeep.el" and path.is_file()


def test_editor_materialize_copies_one_master_record(paths, capsys):
    tmp_path, master = paths
    local = tmp_path / "refs.bib"
    assert (
        cli.main(
            [
                "editor",
                "materialize",
                "doe_adaptive_2019",
                "--into",
                str(local),
                "--library",
                str(master),
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["citation_key"] == "doe_adaptive_2019"
    assert "@article{doe_adaptive_2019," in local.read_text()


def test_verify_can_complete_one_local_record(paths, monkeypatch, capsys):
    tmp_path, _master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry("Smi23", author="Smith, Alice", title="Adaptive estimation", year="2023")
    )
    fetched = entry(
        "z",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )

    def fake_report(record):
        (online,) = duplicates.records(fetched, "zbmath")
        return verification.report(record, [("zbmath", online)])

    monkeypatch.setattr(cli.verification, "fetch_all", fake_report)
    assert cli.main(["verify", str(local), "--key", "Smi23", "--apply", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["applied"]["mode"] == "complete"
    assert "10.1/a" in local.read_text()


def test_editor_refresh_uses_a_fetched_entry_without_another_network_call(
    paths, monkeypatch, capsys
):
    tmp_path, _master = paths
    local = tmp_path / "refs.bib"
    local.write_text(
        entry(
            "Smi23",
            author="Smith, Alice",
            title="Adaptive estimation",
            year="2022",
            file="papers/a.pdf",
        )
    )
    fetched = entry(
        "z",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(fetched))
    assert (
        cli.main(
            [
                "editor",
                "refresh-record",
                str(local),
                "--key",
                "Smi23",
                "--source",
                "zbmath",
                "--mode",
                "selected",
                "--field",
                "year",
                "--field",
                "doi",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["fields"] == ["doi", "year"]
    (updated,) = duplicates.records(local.read_text())
    assert updated.key == "Smi23"
    assert updated.year == "2023"
    assert bib.get_field(updated.body, "file") == "papers/a.pdf"


# --- explicit maintenance commands -------------------------------------


def test_duplicates_produces_an_editable_hold_first_review(paths, capsys):
    tmp_path, _master = paths
    target = tmp_path / "messy.bib"
    target.write_text(
        entry("A", title="Same work", year="2020")
        + entry("B", title="Same work", year="2020")
    )
    assert cli.main(["duplicates", str(target)]) == 1
    report = capsys.readouterr().out
    assert "## a" in report
    assert "hold  A" in report and "hold  B" in report


def test_dedupe_merges_only_reviewed_entries_without_renaming_survivor(paths, capsys):
    tmp_path, _master = paths
    target = tmp_path / "messy.bib"
    target.write_text(
        "% header\n"
        + entry("ForeignA", title="Same work", year="2020")
        + "\n% middle\n"
        + entry("ForeignB", title="Same work", year="2020", doi="10.1/a")
    )
    review = tmp_path / "review.txt"
    review.write_text("## foreigna\n  keep  ForeignA\n  drop  ForeignB\n")
    assert (
        cli.main(["dedupe", str(target), "--resolve", str(review), "--apply", "--json"])
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["applied"]
    assert [record.key for record in duplicates.records(target.read_text())] == [
        "ForeignA"
    ]
    assert "% header" in target.read_text() and "% middle" in target.read_text()
    assert "10.1/a" in target.read_text()


def test_migrate_keys_is_a_separate_plan_then_apply_command(paths, capsys):
    tmp_path, _master = paths
    target = tmp_path / "legacy.bib"
    target.write_text(
        entry(
            "OddKey", author="Smith, Alice", title="Wavelet thresholding", year="2005"
        )
    )
    assert cli.main(["migrate-keys", str(target), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mapping"] == {"OddKey": "smith_wavelet_2005"}
    assert "OddKey" in target.read_text()
    assert cli.main(["migrate-keys", str(target), "--apply"]) == 0
    capsys.readouterr()
    assert duplicates.records(target.read_text())[0].key == "smith_wavelet_2005"
