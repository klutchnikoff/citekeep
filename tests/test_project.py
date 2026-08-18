"""Tests for keeping a project .bib in step with what the document cites."""

from citekeep import bib, duplicates, project


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    fields.setdefault("title", "A title")
    return bib.render_entry("article", key, fields)


# --- reading the sources -------------------------------------------------


def test_every_dialect_of_citation_command_is_found():
    """natbib and biblatex share the stem; a project may use either, and the
    same library serves both."""
    text = (
        r"\citet{a} \citep{b} \parencite{c} \autocite{d} \nocite{e} "
        r"\citeyearpar{f} \textcite{g} \citealp{h}"
    )
    assert project.cited_keys(text) == set("abcdefgh")


def test_optional_arguments_and_several_keys():
    assert project.cited_keys(r"\citep[see][p.~5]{alpha, beta}") == {"alpha", "beta"}


def test_a_commented_citation_is_not_a_citation():
    text = "\\citep{real}\n% \\citep{commented}\n"
    assert project.cited_keys(text) == {"real"}


def test_an_escaped_percent_does_not_start_a_comment():
    assert project.cited_keys(r"100\% \citep{real}") == {"real"}


def test_declared_bibliographies_in_either_dialect():
    text = r"\bibliography{refs} \addbibresource{bibliographie/nk.bib}"
    assert project.bibliographies(text) == ["refs", "bibliographie/nk.bib"]


# --- scanning a tree -----------------------------------------------------


def build(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_scan_reports_where_each_key_is_cited(tmp_path):
    """A key that will not resolve is far easier to fix when you know which
    file writes it."""
    root = build(
        tmp_path,
        {
            "main.tex": r"\citep{alpha} \bibliography{refs}",
            "chapters/one.tex": r"\citet{alpha} \citep{beta}",
        },
    )
    cited, declared = project.scan(root)
    assert set(cited) == {"alpha", "beta"}
    assert {p.name for p in cited["alpha"]} == {"main.tex", "one.tex"}
    assert declared == [root / "refs.bib"]


def test_scan_skips_build_directories(tmp_path):
    root = build(
        tmp_path,
        {
            "main.tex": r"\citep{alpha}",
            "build/main.tex": r"\citep{stale}",
            ".git/x.tex": r"\citep{never}",
        },
    )
    cited, _declared = project.scan(root)
    assert set(cited) == {"alpha"}


# --- planning ------------------------------------------------------------

LIBRARY = entry("doe_adaptive_2019", year="2019") + entry(
    "roe_minimax_2001", year="2001"
)


def plan(project_text, cited):
    return project.plan_materialization(
        duplicates.records(LIBRARY, "master.bib"),
        duplicates.records(project_text, "projet.bib"),
        {k: {"main.tex"} for k in cited},
    )


def test_a_cited_entry_the_project_lacks_is_copied():
    result = plan("", ["doe_adaptive_2019"])
    assert [r.key for r in result.missing] == ["doe_adaptive_2019"]
    assert not result.unknown


def test_a_cited_key_nobody_has_is_named_with_its_file():
    result = plan("", ["ghost_key_1999"])
    assert result.unknown == (("ghost_key_1999", ["main.tex"]),)
    assert not result.missing


def test_an_old_key_is_reported_rather_than_guessed_at():
    """A document written before the library's keys were normalised cites
    names that no longer exist. Saying so beats picking something close."""
    result = plan("", ["Doe19"])
    assert result.unknown[0][0] == "Doe19"


def test_an_entry_already_present_is_not_copied_again():
    result = plan(entry("doe_adaptive_2019", year="2019"), ["doe_adaptive_2019"])
    assert not result.missing


def test_an_uncited_entry_is_reported_never_removed():
    """A .bib may be shared between documents, or hold something about to be
    cited."""
    result = plan(entry("roe_minimax_2001", year="2001"), ["doe_adaptive_2019"])
    assert result.unused == ("roe_minimax_2001",)


# --- applying ------------------------------------------------------------


def test_apply_appends_and_leaves_the_rest_alone():
    """We do not reformat a file we do not own."""
    existing = "% notes de Karine\n" + entry("roe_minimax_2001", year="2001")
    result = plan(existing, ["doe_adaptive_2019", "roe_minimax_2001"])
    out = project.apply_materialization(existing, result.missing)
    assert out.startswith("% notes de Karine")
    assert [k for _t, k, _r, _b in bib.iter_entries(out)] == [
        "roe_minimax_2001",
        "doe_adaptive_2019",
    ]


def test_apply_to_an_empty_file():
    result = plan("", ["doe_adaptive_2019"])
    out = project.apply_materialization("", result.missing)
    assert len(list(bib.iter_entries(out))) == 1


def test_apply_is_idempotent():
    first = project.apply_materialization("", plan("", ["doe_adaptive_2019"]).missing)
    second_plan = plan(first, ["doe_adaptive_2019"])
    second = project.apply_materialization(first, second_plan.missing)
    assert first == second


# --- putting a fetched record into a project .bib ------------------------

FETCHED = entry(
    "zbmath_key", title="Adaptive estimation", year="2019", doi="10.1/x", pages="1--20"
)


def test_a_fetched_record_takes_the_key_the_library_uses():
    """So that the citation written in the document resolves on both sides."""
    out, action = project.write_record("", FETCHED, "doe_adaptive_2019")
    assert action == "added"
    assert [k for _t, k, _r, _b in bib.iter_entries(out)] == ["doe_adaptive_2019"]


def test_a_fetched_record_completes_an_entry_already_there():
    existing = entry("doe_adaptive_2019", title="Adaptive estimation", year="2019")
    out, action = project.write_record(existing, FETCHED, "doe_adaptive_2019")
    assert action == "completed"
    body = next(b for _t, k, _r, b in bib.iter_entries(out) if k == "doe_adaptive_2019")
    assert bib.get_field(body, "pages") == "1--20"
    assert len(list(bib.iter_entries(out))) == 1


def test_a_fetched_record_never_overwrites_what_is_there():
    existing = entry(
        "doe_adaptive_2019", title="Adaptive estimation", year="2019", doi="10.9/mine"
    )
    out, _action = project.write_record(existing, FETCHED, "doe_adaptive_2019")
    body = next(bib.iter_entries(out))[3]
    assert bib.get_field(body, "doi") == "10.9/mine"


def test_writing_a_record_twice_changes_nothing_the_second_time():
    once, _a = project.write_record("", FETCHED, "doe_adaptive_2019")
    twice, action = project.write_record(once, FETCHED, "doe_adaptive_2019")
    assert action == "unchanged" and twice == once


def test_copied_entries_keep_their_raw_text():
    library = entry("k", year="2020", title="Estimation of {DNA} sequences")
    result = project.plan_materialization(
        duplicates.records(library, "master.bib"), [], {"k": {"main.tex"}}
    )
    assert "{DNA}" in project.apply_materialization("", result.missing)
