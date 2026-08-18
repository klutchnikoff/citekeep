from citekeep import bib, duplicates, sync


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    fields.setdefault("title", "A title")
    return bib.render_entry("article", key, fields)


def by_key(text, key):
    return next(record for record in duplicates.records(text) if record.key == key)


def test_a_new_foreign_entry_gets_a_canonical_master_key_and_local_link():
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    result = sync.plan("", local)
    assert not result.blocked
    assert result.master_additions == ("smith_adaptive_2023",)
    assert by_key(result.master_text, "smith_adaptive_2023").doi == "10.1/a"
    linked = by_key(result.local_text, "Smi23")
    assert linked.master_key == "smith_adaptive_2023"
    assert result.aliases_added == (("Smi23", "smith_adaptive_2023"),)


def test_an_existing_master_work_keeps_the_foreign_local_key():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        journal="Annals",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    result = sync.plan(master, local)
    linked = by_key(result.local_text, "Smi23")
    assert linked.master_key == "smith_adaptive_2023"
    assert linked.journal == "Annals"
    assert len(duplicates.records(result.master_text)) == 1


def test_a_local_value_disagreeing_with_the_master_blocks_the_plan():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2022",
        doi="10.1/a",
        file="papers/smith.pdf",
        ckmasterkey="smith_adaptive_2023",
    )
    result = sync.plan(master, local)
    assert result.blocked
    assert result.conflicts[0].reason == "field values disagree: year"
    assert result.master_text == master
    assert result.local_text == local
    conflict = result.conflicts[0].fields[0]
    assert (conflict.name, conflict.master, conflict.local) == ("year", "2023", "2022")


def test_a_field_decision_can_keep_master_and_refresh_the_local_view():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2022",
        doi="10.1/a",
        ckmasterkey="smith_adaptive_2023",
    )
    result = sync.plan(master, local, field_resolutions={("Smi23", "year"): "master"})
    assert not result.blocked
    assert by_key(result.master_text, "smith_adaptive_2023").year == "2023"
    assert by_key(result.local_text, "Smi23").year == "2023"
    assert result.master_corrections == ()


def test_a_field_decision_can_promote_a_verified_local_value_to_master():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2022",
        doi="10.1/a",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        file="papers/a.pdf",
        ckmasterkey="smith_adaptive_2023",
    )
    result = sync.plan(master, local, field_resolutions={("Smi23", "year"): "local"})
    assert not result.blocked
    assert result.master_corrections == (("smith_adaptive_2023", "year"),)
    assert by_key(result.master_text, "smith_adaptive_2023").year == "2023"
    refreshed = by_key(result.local_text, "Smi23")
    assert refreshed.year == "2023"
    assert bib.get_field(refreshed.body, "file") == "papers/a.pdf"


def test_field_resolution_files_are_plain_and_reject_malformed_lines():
    decisions, unread = sync.parse_field_resolutions(
        "# reviewed online\nlocal Smi23 year\nmaster Smi23 doi\nwrong X pages\n"
    )
    assert decisions == {("Smi23", "year"): "local", ("Smi23", "doi"): "master"}
    assert unread == [(4, "wrong X pages")]


def test_master_fields_missing_locally_refresh_the_view_without_a_conflict():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        journal="Annals",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        file="papers/smith.pdf",
        ckmasterkey="smith_adaptive_2023",
    )
    result = sync.plan(master, local)
    linked = by_key(result.local_text, "Smi23")
    assert linked.journal == "Annals"
    assert bib.get_field(linked.body, "file") == "papers/smith.pdf"


def test_a_local_missing_field_enriches_the_master_then_rematerialises():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
        ckmasterkey="smith_adaptive_2023",
    )
    result = sync.plan(master, local)
    assert result.master_enrichments == ("smith_adaptive_2023",)
    assert by_key(result.master_text, "smith_adaptive_2023").doi == "10.1/a"
    assert by_key(result.local_text, "Smi23").doi == "10.1/a"


def test_a_cited_master_entry_is_materialised_locally():
    master = entry("doe_minimax_2019", title="Minimax rates", year="2019")
    result = sync.plan(master, "", {"doe_minimax_2019": {"main.tex"}})
    assert result.local_additions == ("doe_minimax_2019",)
    assert by_key(result.local_text, "doe_minimax_2019").title == "Minimax rates"


def test_an_unknown_citation_is_reported_with_its_sources():
    result = sync.plan("", "", {"Unknown": {"chapter.tex", "main.tex"}})
    assert result.unknown == (("Unknown", ("chapter.tex", "main.tex")),)


def test_a_broken_explicit_link_blocks_the_plan():
    local = entry("Smi23", ckmasterkey="missing_master_key")
    result = sync.plan("", local)
    assert result.blocked
    assert result.conflicts[0].reason == "master key does not exist"


def test_identity_conflict_can_be_resolved_as_the_same_work():
    master = entry(
        "doe_original_2020", title="Original title", year="2020", doi="10.1/a"
    )
    local = entry("Foreign", title="Retitled work", year="2020", doi="10.1/a")
    blocked = sync.plan(master, local)
    assert blocked.blocked
    assert blocked.conflicts[0].answers == ("same", "distinct", "skip")

    result = sync.plan(master, local, identity_resolutions={"Foreign": ("same", None)})
    assert not result.blocked
    assert by_key(result.local_text, "Foreign").master_key == "doe_original_2020"
    assert by_key(result.local_text, "Foreign").title == "Original title"


def test_identity_conflict_can_be_resolved_as_distinct():
    master = entry(
        "doe_original_2020", title="Original title", year="2020", doi="10.1/a"
    )
    local = entry(
        "Foreign",
        author="Smith, Alice",
        title="Retitled work",
        year="2020",
        doi="10.1/a",
    )
    result = sync.plan(
        master, local, identity_resolutions={"Foreign": ("distinct", None)}
    )
    assert not result.blocked
    assert result.master_additions == ("smith_retitled_2020",)
    assert by_key(result.local_text, "Foreign").master_key == ("smith_retitled_2020")


def test_identity_conflict_can_be_skipped_without_changing_either_file():
    master = entry(
        "doe_original_2020", title="Original title", year="2020", doi="10.1/a"
    )
    local = entry("Foreign", title="Retitled work", year="2020", doi="10.1/a")
    result = sync.plan(master, local, identity_resolutions={"Foreign": ("skip", None)})
    assert not result.blocked
    assert result.master_text == master
    assert result.local_text == local
    assert result.local_skipped == ("Foreign",)


def test_sync_is_idempotent():
    master = entry(
        "smith_adaptive_2023",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    local = entry(
        "Smi23",
        author="Smith, Alice",
        title="Adaptive estimation",
        year="2023",
        doi="10.1/a",
    )
    once = sync.plan(master, local)
    twice = sync.plan(once.master_text, once.local_text)
    assert twice.master_text == once.master_text
    assert twice.local_text == once.local_text
    assert not twice.changed
