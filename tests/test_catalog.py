from citekeep import bib, catalog, duplicates


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    fields.setdefault("title", "A title")
    return bib.render_entry("article", key, fields)


def records(text, origin):
    return duplicates.records(text, origin)


MASTER = entry(
    "smith_adaptive_2023",
    author="Smith, Alice",
    title="Adaptive estimation",
    year="2023",
    doi="10.1/a",
) + entry("doe_minimax_2019", title="Minimax rates", year="2019")


def test_search_returns_local_before_master():
    local = entry(
        "LocalSmith", author="Smith, Alice", title="Another Smith paper", year="2020"
    )
    result = catalog.search(
        records(MASTER, "master"), records(local, "project"), "smith"
    )
    assert [hit.citation_key for hit in result.local] == ["LocalSmith"]
    assert [hit.citation_key for hit in result.master] == ["smith_adaptive_2023"]


def test_a_local_alias_masks_the_master_work():
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        ckmasterkey="smith_adaptive_2023",
    )
    result = catalog.search(
        records(MASTER, "master"), records(local, "project"), "adaptive"
    )
    assert [hit.citation_key for hit in result.local] == ["Smi23"]
    assert result.local[0].master_key == "smith_adaptive_2023"
    assert result.master == ()


def test_an_unannotated_local_variant_also_masks_the_master():
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    result = catalog.search(
        records(MASTER, "master"), records(local, "project"), "adaptive"
    )
    assert [hit.citation_key for hit in result.local] == ["Smi23"]
    assert result.master == ()


def test_a_fetched_record_uses_the_local_alias_before_the_master():
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        ckmasterkey="smith_adaptive_2023",
    )
    (fetched,) = records(
        entry(
            "zb",
            author="Smith, Alice",
            title="Adaptive estimation",
            year="2023",
            doi="10.1/a",
        ),
        "zbmath",
    )
    match = catalog.classify_fetched(
        records(MASTER, "master"), records(local, "project"), fetched
    )
    assert match.kind == "unchanged"
    assert match.key == "Smi23"


def test_materialising_a_master_record_uses_its_canonical_key():
    (master,) = records(
        entry(
            "smith_adaptive_2023",
            author="Smith, Alice",
            title="Adaptive estimation",
            year="2023",
        ),
        "master",
    )
    plan = catalog.materialize("", master)
    assert plan.citation_key == "smith_adaptive_2023"
    assert plan.action == "added"
    assert "@article{smith_adaptive_2023," in plan.text


def test_set_field_adds_and_updates_the_master_link():
    raw = entry("Smi23")
    linked = bib.set_field(raw, "ckmasterkey", "smith_adaptive_2023")
    assert (
        bib.get_field(next(bib.iter_entries(linked))[3], "ckmasterkey")
        == "smith_adaptive_2023"
    )
    updated = bib.set_field(linked, "ckmasterkey", "smith_adaptive_2023a")
    assert updated.count("ckmasterkey") == 1
    assert "smith_adaptive_2023a" in updated


def test_master_link_is_never_donated():
    body = next(
        bib.iter_entries(
            entry("Smi23", ckmasterkey="smith_adaptive_2023", doi="10.1/a")
        )
    )[3]
    assert [name for name, _key, _value in bib.donatable(body)] == [
        "author",
        "title",
        "doi",
    ]
