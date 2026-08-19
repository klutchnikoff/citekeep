"""Tests for proposing project records to the master library."""

import pytest

from citekeep import bib, duplicates, library


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    return bib.render_entry("article", key, fields)


LIBRARY = (
    "%% master.bib\n\n"
    + entry(
        "doe_adaptive_2019",
        title="Adaptive estimation",
        year="2019",
        doi="10.1/right",
        journal="Ann. Statist.",
    )
    + "\n"
    + entry(
        "roe_minimax_2001", title="Minimax bounds", year="2001", author="Roe, Richard"
    )
)


def proposals(incoming_text, library_text=LIBRARY):
    return library.plan_proposals(
        duplicates.records(library_text, "master.bib"),
        duplicates.records(incoming_text, "projet.bib"),
    )


# --- the ordinary case ---------------------------------------------------


def test_an_entry_already_present_is_silent():
    """The common case on every sync. If it prompted, nobody would read the
    prompts."""
    plan = proposals(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
        )
    )
    assert not (plan.additions or plan.enrichments or plan.conflicts or plan.skipped)
    assert plan.unchanged == ("doe_adaptive_2019",)


def test_a_matching_entry_with_more_fields_enriches():
    plan = proposals(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            pages="1--20",
            volume="47",
        )
    )
    (change,) = plan.enrichments
    assert change.key == "doe_adaptive_2019"
    assert {n for n, _v in change.fields} == {"pages", "volume"}


def test_enrichment_never_overwrites_the_library():
    """The library is the reference; a correction is a separate operation."""
    plan = proposals(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Revue Inventée",
            pages="1--20",
        )
    )
    out = library.apply_proposals(LIBRARY, plan)
    body = next(b for _t, k, _r, b in bib.iter_entries(out) if k == "doe_adaptive_2019")
    assert bib.get_field(body, "journal") == "Ann. Statist."
    assert bib.get_field(body, "pages") == "1--20"


def test_an_unrelated_entry_is_added_under_its_normalised_key():
    plan = proposals(
        entry(
            "SmithEtAl",
            title="Wavelet thresholding",
            year="2005",
            author="Smith, Alice",
        )
    )
    (addition,) = plan.additions
    assert addition.key == "smith_wavelet_2005"
    assert not plan.blocked


# --- matching across the four fingerprints -------------------------------


def test_a_preprint_matches_the_published_version_by_arxiv():
    text = "%% master\n\n" + entry(
        "gine_confidence_2010",
        title="Confidence bands",
        year="2010",
        eprint="1005.4444",
        doi="10.1/x",
    )
    plan = proposals(
        entry(
            "gine2009preprint",
            title="Confidence bands for densities",
            year="2009",
            eprint="1005.4444",
        ),
        text,
    )
    assert plan.unchanged or plan.enrichments
    assert not plan.conflicts


def test_a_different_key_is_no_obstacle():
    """Keys carry no information: the project may call it anything."""
    plan = proposals(
        entry("ZZZ", title="Adaptive estimation", year="2019", doi="10.1/right")
    )
    assert not plan.additions and not plan.conflicts


# --- conflicts -----------------------------------------------------------


def test_a_disagreeing_title_is_a_conflict_not_a_merge():
    """Same author, same year, so the same normalised key — but a different
    paper. This is the Bertin case: two 2014 papers that only the titles
    tell apart."""
    plan = proposals(
        entry(
            "x", title="Minimax rates under dependence", year="2019", doi="10.1/right"
        )
    )
    (conflict,) = plan.conflicts
    assert conflict.reason == "titles disagree"
    assert plan.blocked


def test_a_prefix_title_still_counts_as_one_work():
    """`same_work` treats a shorter title as a subtitle that went missing.

    It is what lets one source's "Adaptive estimation" meet another's
    "Adaptive estimation: a new approach" — and it means a truncated title in
    the library will absorb anything that extends it.
    """
    plan = proposals(
        entry(
            "x",
            title="Adaptive estimation: a new approach",
            year="2019",
            doi="10.1/right",
        )
    )
    assert not plan.conflicts


def test_a_contradictory_doi_is_a_conflict():
    plan = proposals(
        entry("x", title="Adaptive estimation", year="2019", doi="10.9/other")
    )
    assert plan.conflicts[0].reason == "several DOIs"


def test_two_works_sharing_a_normalised_key_need_no_arbitration():
    """Two 2020 papers by one author, both titled "Adaptive…".

    Only the derived key linked them; their DOIs, titles and co-authors all
    said otherwise. The question used to come back at every synchronisation,
    and answering it changed nothing, since the keys were already distinct.
    """
    incoming = entry(
        "one",
        author="Bertin, Karine and Léon, Jose R.",
        title="Adaptive density estimation on bounded domains",
        year="2020",
        doi="10.1214/20-EJS1682",
    ) + entry(
        "two",
        author="Bertin, Karine and Panloup, Fabien",
        title="Adaptive estimation of the stationary density",
        year="2020",
        doi="10.1007/s11203-020-09218-0",
    )
    plan = proposals(incoming, "%% master\n\n")
    assert not plan.blocked
    assert [addition.key for addition in plan.additions] == [
        "bertin_adaptive_2020",
        "bertin_adaptive_2020a",
    ]


def test_a_new_work_landing_on_a_used_key_is_a_conflict():
    """A safety net for a library whose keys are not normalised.

    The key cannot simply be suffixed: references to the existing entry exist,
    so it cannot be renamed, and guessing is worse than asking.
    """
    text = "%% master\n\n" + entry(
        "doe_adaptive_2019", title="Wavelets", year="1990", author="Zed, Zoe"
    )
    plan = proposals(
        entry("x", title="Adaptive estimation", year="2019", doi="10.2/b"), text
    )
    assert plan.conflicts[0].reason == "key already in use"
    assert plan.blocked


def test_applying_a_blocked_push_refuses():
    plan = proposals(
        entry(
            "x", title="Minimax rates under dependence", year="2019", doi="10.1/right"
        )
    )
    with pytest.raises(ValueError):
        library.apply_proposals(LIBRARY, plan)


# --- two incoming entries describing one work ----------------------------


def test_planned_additions_meet_each_other():
    """Otherwise a file holding a paper twice would put it in the library
    twice, which is exactly how the mess began."""
    incoming = (
        entry(
            "A",
            title="Wavelet thresholding",
            year="2005",
            author="Smith, Alice",
            doi="10.5/w",
        )
        + "\n"
        + entry(
            "B",
            title="Wavelet thresholding",
            year="2005",
            author="Smith, Alice",
            doi="10.5/w",
            pages="1--30",
        )
    )
    plan = proposals(incoming)
    assert len(plan.additions) == 1
    assert len(plan.enrichments) + len(plan.unchanged) == 1


# --- applying ------------------------------------------------------------


def test_apply_keeps_the_header_and_appends_a_new_entry():
    plan = proposals(
        entry("AAA", title="Wavelet thresholding", year="2005", author="Smith, Alice")
    )
    out = library.apply_proposals(LIBRARY, plan)
    keys = [k for _t, k, _r, _b in bib.iter_entries(out)]
    assert out.startswith("%% master.bib")
    assert keys[-1] == "smith_wavelet_2005"
    assert "smith_wavelet_2005" in keys


def test_apply_preserves_brace_protection():
    plan = proposals(
        entry(
            "AAA",
            title="Estimation of {DNA} sequences",
            year="2005",
            author="Smith, Alice",
        )
    )
    assert "{DNA}" in library.apply_proposals(LIBRARY, plan)


def test_apply_is_idempotent():
    """Pushing the same file twice must change nothing the second time."""
    incoming = entry(
        "AAA",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
        doi="10.5/w",
    )
    once = library.apply_proposals(LIBRARY, proposals(incoming))
    twice = library.apply_proposals(once, proposals(incoming, once))
    assert once == twice


def test_apply_without_changes_is_byte_identical():
    plan = proposals(
        entry(
            "Doe19",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
        )
    )
    out = library.apply_proposals(LIBRARY, plan)
    assert out == LIBRARY


def test_apply_preserves_directives_comments_and_trailing_text():
    text = (
        '@string{J = "Journal"}\n\n'
        "% before the entry\n"
        + entry(
            "doe_adaptive_2019",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
        )
        + "\n% trailing comment\n"
    )
    plan = library.plan_proposals(duplicates.records(text), [])
    assert library.apply_proposals(text, plan) == text


def test_a_second_incoming_variant_completes_a_planned_addition():
    incoming = entry(
        "A",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
        doi="10.5/w",
    ) + entry(
        "B",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
        doi="10.5/w",
        pages="1--30",
    )
    plan = library.plan_proposals(
        duplicates.records(LIBRARY), duplicates.records(incoming)
    )
    out = library.apply_proposals(LIBRARY, plan)
    added = next(
        body
        for _t, key, _raw, body in bib.iter_entries(out)
        if key == "smith_wavelet_2005"
    )
    assert bib.get_field(added, "pages") == "1--30"


def test_two_incoming_enrichments_with_different_dois_conflict():
    master = entry(
        "smith_wavelet_2005",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
    )
    incoming = entry(
        "A",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
        doi="10.1/a",
    ) + entry(
        "B",
        title="Wavelet thresholding",
        year="2005",
        author="Smith, Alice",
        doi="10.1/b",
    )
    plan = library.plan_proposals(
        duplicates.records(master), duplicates.records(incoming)
    )
    assert plan.blocked
    assert plan.conflicts[0].reason == "several DOIs"


# --- one entry at a time, for the fetch-time check ------------------------
#
# A record fetched from zbMATH while writing goes through the same code as a
# whole file being pushed. Catching a duplicate here is cheapest: the user is
# already looking at that reference.


def look_up(incoming_text, library_text=LIBRARY):
    index = library.index(duplicates.records(library_text, "master.bib"))
    (record,) = duplicates.records(incoming_text, "zbmath")
    return library.look_up(index, record)


def test_a_fetched_record_the_library_already_has():
    match = look_up(
        entry(
            "zb1",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
        )
    )
    assert match.kind == "unchanged"
    assert match.key == "doe_adaptive_2019"


def test_a_fetched_record_that_would_complete_the_library():
    """The case that keeps the library growing without anyone thinking about
    it: insert the existing key, and take the fields it was missing."""
    match = look_up(
        entry(
            "zb1",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            pages="1--20",
        )
    )
    assert match.kind == "enrich"
    assert [n for n, _v in match.fields] == ["pages"]


def test_a_fetched_record_nobody_has():
    match = look_up(
        entry("zb1", title="Wavelet thresholding", year="2005", author="Smith, Alice")
    )
    assert match == library.Match("new", "smith_wavelet_2005")


def test_a_fetched_record_that_needs_a_question():
    match = look_up(
        entry(
            "zb1", title="Minimax rates under dependence", year="2019", doi="10.1/right"
        )
    )
    assert match.kind == "conflict"
    assert match.existing[0].key == "doe_adaptive_2019"


# --- what a donor may and may not carry ----------------------------------


def test_biblatex_spellings_do_not_duplicate_what_is_there():
    """`date` next to `year`, `journaltitle` next to `journal`: a Zotero
    biblatex export would double the vocabulary of every entry it touched."""
    match = look_up(
        entry(
            "zb1",
            title="Adaptive estimation",
            date="2019-05",
            doi="10.1/right",
            journaltitle="Ann. Statist.",
        )
    )
    assert match.kind == "unchanged"


def test_fields_describing_the_source_are_never_carried_over():
    """They were removed from the library once; a merge must not bring them
    back on the next sync."""
    match = look_up(
        entry(
            "zb1",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
            urldate="2025-09-27",
            file="/home/johndoe/x.pdf",
            shorttitle="Adaptive",
        )
    )
    assert match.kind == "unchanged"


def test_a_genuinely_new_field_is_still_carried_over():
    match = look_up(
        entry(
            "zb1",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/right",
            journal="Ann. Statist.",
            zmnumber="1292.62059",
            urldate="2025-09-27",
        )
    )
    assert [n for n, _v in match.fields] == ["zmnumber"]


# --- settling a conflict -------------------------------------------------

CLASH = entry(
    "x",
    title="Minimax rates under dependence",
    year="2019",
    doi="10.1/right",
    pages="1--20",
)


def settled(text):
    resolutions, _unread = library.parse_resolutions(text)
    return library.plan_proposals(
        duplicates.records(LIBRARY, "master.bib"),
        duplicates.records(CLASH, "projet.bib"),
        resolutions,
    )


def test_an_unanswered_conflict_still_blocks():
    assert settled("").blocked


def test_same_completes_the_entry_it_belongs_to():
    plan = settled("same x\n")
    assert not plan.blocked
    (change,) = plan.enrichments
    assert change.key == "doe_adaptive_2019"


def test_distinct_gives_it_a_key_of_its_own():
    plan = settled("distinct x\n")
    (addition,) = plan.additions
    assert addition.key == "doe_minimax_2019"
    assert not plan.blocked


def test_distinct_suffixes_when_the_key_is_taken():
    """The entry already holding the key keeps it: documents this tool cannot
    see refer to it, and renaming it would break them."""
    clash = entry(
        "x", title="Adaptive rates under dependence", year="2019", doi="10.9/other"
    )
    resolutions, _ = library.parse_resolutions("distinct x\n")
    plan = library.plan_proposals(
        duplicates.records(LIBRARY, "master.bib"),
        duplicates.records(clash, "projet.bib"),
        resolutions,
    )
    assert plan.additions[0].key == "doe_adaptive_2019a"


def test_skip_leaves_it_out_altogether():
    plan = settled("skip x\n")
    assert plan.skipped == ("x",)
    assert not (plan.additions or plan.enrichments or plan.conflicts)


def test_same_needs_to_say_which_when_several_entries_match():
    text = entry(
        "doe_adaptive_2019", title="Adaptive estimation", year="2019", doi="10.1/right"
    ) + entry(
        "doe_adaptive_2019bis",
        title="Adaptive estimation",
        year="2019",
        eprint="1005.4444",
    )
    incoming = entry(
        "x",
        title="Something else entirely",
        year="2019",
        doi="10.1/right",
        eprint="1005.4444",
    )
    resolutions, _ = library.parse_resolutions("same x\n")
    plan = library.plan_proposals(
        duplicates.records(text, "master.bib"),
        duplicates.records(incoming, "projet.bib"),
        resolutions,
    )
    assert "which entry" in plan.conflicts[0].reason


def test_same_accepts_the_entry_it_is_told():
    text = entry(
        "doe_adaptive_2019", title="Adaptive estimation", year="2019", doi="10.1/right"
    ) + entry(
        "doe_adaptive_2019bis",
        title="Adaptive estimation",
        year="2019",
        eprint="1005.4444",
    )
    incoming = entry(
        "x",
        title="Something else entirely",
        year="2019",
        doi="10.1/right",
        eprint="1005.4444",
        pages="1--20",
    )
    resolutions, _ = library.parse_resolutions("same x doe_adaptive_2019bis\n")
    plan = library.plan_proposals(
        duplicates.records(text, "master.bib"),
        duplicates.records(incoming, "projet.bib"),
        resolutions,
    )
    assert plan.enrichments[0].key == "doe_adaptive_2019bis"


def test_a_named_entry_that_does_not_match_is_refused():
    plan = settled("same x roe_minimax_2001\n")
    assert "not one of the entries" in plan.conflicts[0].reason


def test_comments_and_blank_lines_are_ignored():
    resolutions, unread = library.parse_resolutions(
        "# à revoir avec Karine\n\n  same  x\n"
    )
    assert resolutions == {"x": ("same", None)} and unread == []


def test_a_mistyped_verb_is_reported_not_swallowed():
    """A decision silently dropped leaves the user believing they answered."""
    _resolutions, unread = library.parse_resolutions("sam x\nskip y\n")
    assert [n for n, _l in unread] == [1]
