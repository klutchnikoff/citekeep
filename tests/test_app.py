import pytest

from citekeep import Citekeep, bib, storage


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    fields.setdefault("title", "A title")
    return bib.render_entry("article", key, fields)


def test_public_api_searches_local_then_master(tmp_path):
    master = tmp_path / "master.bib"
    local = tmp_path / "refs.bib"
    master.write_text(entry("doe_master_2020", title="Master paper", year="2020"))
    local.write_text(entry("doe_local_2021", title="Local paper", year="2021"))
    result = Citekeep.open(master).search("paper", local)
    assert [hit.citation_key for hit in result.local] == ["doe_local_2021"]
    assert [hit.citation_key for hit in result.master] == ["doe_master_2020"]


def test_public_api_plans_and_applies_a_project_sync(tmp_path):
    master = tmp_path / "master.bib"
    local = tmp_path / "refs.bib"
    tex = tmp_path / "main.tex"
    master.write_text(entry("doe_master_2020", title="Master paper", year="2020"))
    tex.write_text(r"\cite{doe_master_2020}\bibliography{refs}")
    app = Citekeep.open(master)
    plan = app.plan_project(tmp_path)
    assert plan.local_additions == ("doe_master_2020",)
    app.apply(plan)
    assert "doe_master_2020" in local.read_text()


def test_public_api_rejects_the_master_as_project_bibliography(tmp_path):
    master = tmp_path / "master.bib"
    master.write_text(entry("doe_master_2020", year="2020"))
    app = Citekeep.open(master)
    with pytest.raises(ValueError, match="cannot be the master"):
        app.plan_project(tmp_path, master)


def test_public_api_rejects_a_concurrent_master_edit(tmp_path):
    master = tmp_path / "master.bib"
    tex = tmp_path / "main.tex"
    master.write_text(entry("doe_master_2020", title="Master paper", year="2020"))
    tex.write_text(r"\cite{doe_master_2020}\bibliography{refs}")
    app = Citekeep.open(master)
    plan = app.plan_project(tmp_path)
    master.write_text(master.read_text() + "% concurrent\n")
    with pytest.raises(storage.ConcurrentModification):
        app.apply(plan)


def test_public_api_accepts_explicit_field_arbitration(tmp_path):
    master = tmp_path / "master.bib"
    local = tmp_path / "refs.bib"
    master.write_text(entry("doe_master_2020", year="2020", doi="10.1/a"))
    local.write_text(
        entry("Foreign", year="2021", doi="10.1/a", ckmasterkey="doe_master_2020")
    )
    app = Citekeep.open(master)
    blocked = app.plan_project(tmp_path, local)
    assert blocked.blocked
    plan = app.plan_project(tmp_path, local, {("Foreign", "year"): "local"})
    assert not plan.blocked
    assert plan.master_corrections == (("doe_master_2020", "year"),)


def test_public_api_accepts_explicit_identity_arbitration(tmp_path):
    master = tmp_path / "master.bib"
    local = tmp_path / "refs.bib"
    master.write_text(
        entry("doe_master_2020", title="Original title", year="2020", doi="10.1/a")
    )
    local.write_text(entry("Foreign", title="Retitled work", year="2020", doi="10.1/a"))
    app = Citekeep.open(master)
    blocked = app.plan_project(tmp_path, local)
    assert blocked.blocked
    plan = app.plan_project(
        tmp_path, local, identity_resolutions={"Foreign": ("same", None)}
    )
    assert not plan.blocked
    assert plan.aliases_added == (("Foreign", "doe_master_2020"),)
