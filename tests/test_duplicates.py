"""Tests for duplicate detection.

The two failure cases here are taken from a real library of 2438 entries, and
are the reason detection never merges on its own.
"""

from citekeep import bib, duplicates


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    return bib.render_entry("article", key, fields)


def records(*texts):
    return duplicates.records("\n".join(texts), origin="master.bib")


# --- the criteria --------------------------------------------------------


def test_same_doi_groups_despite_unrelated_keys():
    """Keys carry no information: `MR2724359` and `Tsy09` are the same book."""
    entries = records(
        entry(
            "MR3161446",
            title="Unexpected properties",
            year="2013",
            doi="10.1214/13-AOS1158",
        ),
        entry(
            "carroll13",
            title="Unexpected properties",
            year="2013",
            doi="10.1214/13-aos1158",
        ),
    )
    assert len(duplicates.find_groups(entries)) == 1


def test_grouping_survives_a_preprint_and_its_published_version():
    """Different years, so the normalised keys differ; only the DOI links them."""
    entries = records(
        entry(
            "arXiv:2209.04757",
            title="Normal models",
            year="2024",
            doi="10.1214/25-ejs2407",
        ),
        entry(
            "MR4939549", title="Normal models", year="2025", doi="10.1214/25-ejs2407"
        ),
    )
    groups = duplicates.find_groups(entries)
    assert len(groups) == 1 and len(groups[0]) == 2


def test_titles_group_entries_that_have_no_doi():
    """A third of a working library has no DOI at all."""
    entries = records(
        entry(
            "T2009",
            title="Introduction to nonparametric estimation",
            year="2009",
            author="Tsybakov, A. B.",
        ),
        entry(
            "tsybakov2009",
            title="Introduction to {Nonparametric} {Estimation}",
            year="2009",
            author="Tsybakov, Alexandre B.",
        ),
    )
    assert len(duplicates.find_groups(entries)) == 1


def test_unrelated_entries_are_not_grouped():
    entries = records(
        entry("a", title="Minimax lower bounds", year="2001"),
        entry("b", title="Adaptive estimation", year="2002", author="Roe, Richard"),
    )
    assert duplicates.find_groups(entries) == []


def test_singletons_are_dropped():
    assert duplicates.find_groups(records(entry("a", title="T"))) == []


# --- biblatex spellings --------------------------------------------------
#
# Zotero's biblatex export writes `date` and `journaltitle`. A real project
# bibliography of 44 entries held not one `year` field; reading only `year`
# gave every entry a "no date" key and made unrelated papers collide.


def test_year_is_read_from_a_biblatex_date():
    entries = records(
        "@article{k,\n  title = {T},\n  author = {Doe, J.},\n  date = {2025-01},\n}"
    )
    assert entries[0].year == "2025"
    assert entries[0].target == "doe_t_2025"


def test_a_date_range_yields_its_first_year():
    entries = records("@article{k,\n  date = {2020/2021},\n}")
    assert entries[0].year == "2020"


def test_year_wins_over_date_when_both_are_present():
    entries = records("@article{k,\n  year = {1999},\n  date = {2025-01},\n}")
    assert entries[0].year == "1999"


def test_journaltitle_is_read_as_the_journal():
    entries = records("@article{k,\n  journaltitle = {Electron. J. Stat.},\n}")
    assert entries[0].journal == "Electron. J. Stat."


# --- arXiv ---------------------------------------------------------------
#
# All four forms occur in one real library, one of them as a citation key.


def test_arxiv_id_is_read_from_every_form():
    forms = {
        "eprint = {1312.7402},": "1312.7402",
        "url = {http://arxiv.org/abs/1312.7402},": "1312.7402",
        "doi = {10.48550/arXiv.2108.06507},": "2108.06507",
        "note = {arXiv:2306.16091},": "2306.16091",
        "eprint = {math.ST/0503083},": "math.st/0503083",
    }
    for body, expected in forms.items():
        assert duplicates.arxiv_id(body) == expected


def test_arxivid_is_read_too():
    """Zotero writes `arxivid`. One entry in a real corpus carried its
    identifier only there, and was invisible to duplicate detection."""
    assert duplicates.arxiv_id("arxivid = {2005.12345},") == "2005.12345"


def test_arxiv_version_suffix_is_ignored():
    """v1 and v2 are the same work."""
    assert duplicates.arxiv_id("eprint = {2108.06507v2},") == "2108.06507"


def test_a_hal_eprint_is_not_taken_for_arxiv():
    body = "eprint = {hal-01234567}, eprinttype = {HAL},"
    assert duplicates.arxiv_id(body) == ""


def test_a_plain_doi_is_not_mined_for_an_arxiv_id():
    assert duplicates.arxiv_id("doi = {10.1214/aos/1176350258},") == ""


def test_a_reworded_preprint_is_grouped_with_its_published_version():
    """Different year, different title, no shared DOI — only the eprint links
    them. Five such pairs hid in a library of 2438 entries."""
    entries = records(
        entry(
            "BertinLacourRivoirard2014",
            author="Bertin, K.",
            title="Adaptive estimation of conditional density function",
            year="2014",
            url="http://arxiv.org/abs/1312.7402",
        ),
        entry(
            "BLR",
            author="Bertin, Karine",
            title="Adaptive pointwise estimation of conditional density function",
            year="2016",
            eprint="1312.7402",
            doi="10.1214/14-AIHP665",
        ),
    )
    groups = duplicates.find_groups(entries)
    assert len(groups) == 1 and len(groups[0]) == 2


# --- coherence -----------------------------------------------------------
#
# Grouping is transitive, so a group can contain a record that belongs to none
# of the others. Coherence is what stops that reaching a merge.


def test_chaining_pulls_in_a_different_paper():
    """Bertin 2014, from the real corpus.

    Two papers by the same author, same year, joined through a shared
    fingerprint with a third variant. Merging them would lose a reference.
    """
    entries = records(
        entry(
            "bertin2014adaptive",
            author="Bertin, Karine",
            title="Adaptive estimation of a density function using beta kernels",
            year="2014",
        ),
        entry(
            "bertin_adaptive_2014",
            author="Bertin, Karine",
            title="Adaptive estimation of a density function using beta kernels",
            year="2014",
        ),
        entry(
            "BertinLacourRivoirard2014",
            author="Bertin, Karine",
            title="Adaptive estimation of conditional density function",
            year="2014",
        ),
    )
    (group,) = duplicates.find_groups(entries)
    assert duplicates.coherence(group) == "titles disagree"


def test_conflicting_dois_are_not_merged_silently():
    entries = records(
        entry("a", title="Smooth optimum kernel estimators", year="1991", doi="10.1/x"),
        entry("b", title="Smooth optimum kernel estimators", year="1991", doi="10.2/y"),
    )
    (group,) = duplicates.find_groups(entries)
    assert duplicates.coherence(group) == "several DOIs"


def test_a_record_without_a_title_vouches_for_nothing():
    """CrossRef answered a free-text query with a test account's record — a
    DOI, a publisher, no title, no author. An empty signature agrees with
    everything, so it would have been merged into a real entry."""
    entries = records(
        entry("mine", title="Wxyv qqjk nonexistent paper", year="1999"),
        "@article{theirs,\n  year = {2025},\n  doi = {10.5555/grant-new},\n}",
    )
    assert duplicates.coherence(entries) == "no title to compare"


def test_a_shared_doi_vouches_even_without_a_title():
    entries = records(
        entry("mine", title="Adaptive estimation", year="2019", doi="10.1/x"),
        "@article{theirs,\n  year = {2019},\n  doi = {10.1/x},\n}",
    )
    assert duplicates.coherence(entries) is None


def test_two_arxiv_identifiers_are_two_works():
    entries = records(
        entry("a", title="Adaptive estimation", year="2019", eprint="1005.4444"),
        entry("b", title="Adaptive estimation", year="2019", eprint="2108.06507"),
    )
    assert duplicates.coherence(entries) == "several arXiv identifiers"


def test_a_missing_subtitle_stays_mergeable():
    entries = records(
        entry("a", title="Adaptive estimation", year="2019"),
        entry("b", title="Adaptive estimation: a new approach", year="2019"),
    )
    (group,) = duplicates.find_groups(entries)
    assert duplicates.coherence(group) is None


def test_classify_separates_the_two_kinds():
    entries = records(
        entry("a", title="Adaptive estimation", year="2019"),
        entry("b", title="Adaptive estimation", year="2019", doi="10.1/x"),
        entry("c", author="Roe, R.", title="Minimax bounds", year="2001", doi="10.2/y"),
        entry("d", author="Roe, R.", title="Minimax bounds", year="2001", doi="10.3/z"),
    )
    mergeable, review = duplicates.classify(duplicates.find_groups(entries))
    assert len(mergeable) == 1 and len(review) == 1


# --- identity and proposals ----------------------------------------------


def test_group_id_does_not_depend_on_file_order():
    first = records(
        entry("Zed", title="T", year="2000"), entry("Alpha", title="T", year="2000")
    )
    second = records(
        entry("Alpha", title="T", year="2000"), entry("Zed", title="T", year="2000")
    )
    assert duplicates.group_id(duplicates.find_groups(first)[0]) == duplicates.group_id(
        duplicates.find_groups(second)[0]
    )


def test_title_is_flattened():
    """A wrapped title reached the report as two lines, one of which then
    looked like a line of the report's own format."""
    text = (
        "@article{k,\n  title = {Nonparametric multiplicative bias\n"
        "  correction for kernel-type estimation},\n  year = {2010},\n}"
    )
    (record,) = duplicates.records(text)
    assert record.title == (
        "Nonparametric multiplicative bias correction for kernel-type estimation"
    )


def test_winner_is_the_richest_entry():
    entries = records(
        entry("poor", title="Adaptive estimation", year="2019"),
        entry(
            "rich",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/x",
            volume="41",
            pages="1--20",
            journal="Ann. Stat.",
        ),
    )
    (group,) = duplicates.find_groups(entries)
    assert duplicates.winner(group).key == "rich"


def test_as_dict_is_json_serialisable_and_complete():
    """The front-end must be able to decide without reopening the .bib."""
    import json

    entries = records(
        entry(
            "T2009",
            title="Introduction to nonparametric estimation",
            year="2009",
            author="Tsybakov, A. B.",
            doi="10.1/x",
        ),
        entry(
            "Tsy09",
            title="Introduction to nonparametric estimation",
            year="2009",
            author="Tsybakov, A. B.",
        ),
    )
    (group,) = duplicates.find_groups(entries)
    view = json.loads(json.dumps(duplicates.as_dict(group)))
    assert view["id"] == "t2009"
    assert view["target"] == "tsybakov_introduction_2009"
    assert {e["key"] for e in view["entries"]} == {"T2009", "Tsy09"}
    assert view["reason"] is None


def test_summary_counts_what_a_merge_would_remove():
    entries = records(
        entry("a", title="Adaptive estimation", year="2019"),
        entry("b", title="Adaptive estimation", year="2019"),
        entry("c", title="Adaptive estimation", year="2019"),
    )
    assert duplicates.summary(duplicates.find_groups(entries)) == {
        "groups": 1,
        "entries": 3,
        "mergeable": 1,
        "review": 0,
        "removed_if_all_merged": 2,
    }


# --- refutation ----------------------------------------------------------
#
# Taken from a real library: two 2020 papers by the same first author whose
# titles both begin "Adaptive". Nothing but the derived key linked them, and
# that was enough to demand an arbitration at every synchronisation.


BERTIN_ONE = entry(
    "bertin_adaptive_2020",
    author="Bertin, Karine and Klutchnikoff, Nicolas and Léon, Jose R.",
    title="Adaptive density estimation on bounded domains under mixing conditions",
    year="2020",
    doi="10.1214/20-EJS1682",
)

BERTIN_TWO = entry(
    "bertin_adaptive_2020a",
    author="Bertin, Karine and Klutchnikoff, Nicolas and Panloup, Fabien",
    title="Adaptive estimation of the stationary density of a stochastic "
    "differential equation",
    year="2020",
    doi="10.1007/s11203-020-09218-0",
)


def test_different_dois_and_different_work_refute_each_other():
    one, two = records(BERTIN_ONE, BERTIN_TWO)
    assert duplicates.refuted(one, two)


def test_one_title_and_one_authorship_under_two_dois_stays_a_question():
    """A duplicate registration, or a journal and a conference version.

    Refuting here would decide something only a person can.
    """
    one, two = records(
        entry("a", title="Adaptive estimation", year="2019", doi="10.1/a"),
        entry("b", title="Adaptive estimation", year="2019", doi="10.1/b"),
    )
    assert not duplicates.refuted(one, two)


def test_a_shared_arxiv_identifier_outranks_two_dois():
    """A preprint and the paper it became: two DOIs, one work."""
    one, two = records(
        entry(
            "preprint",
            title="On computable numbers",
            year="2019",
            doi="10.48550/arXiv.1901.00001",
            eprint="1901.00001",
            eprinttype="arXiv",
        ),
        entry(
            "published",
            title="On computable numbers, with an application",
            year="2021",
            doi="10.1214/21-AOS2000",
            eprint="1901.00001",
            eprinttype="arXiv",
        ),
    )
    assert not duplicates.refuted(one, two)


def test_a_missing_doi_refutes_nothing():
    """Silence is not disagreement."""
    one, two = records(
        entry("a", title="Adaptive estimation", year="2019", doi="10.1/a"),
        entry("b", title="Something else entirely", year="2019"),
    )
    assert not duplicates.refuted(one, two)


def test_an_author_set_truncated_by_et_al_still_agrees():
    one, two = records(
        entry(
            "full",
            author="Doe, Jane and Roe, Richard and Poe, Paula",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/a",
        ),
        entry(
            "short",
            author="Doe, Jane and Roe, Richard",
            title="Adaptive estimation",
            year="2019",
            doi="10.1/b",
        ),
    )
    assert duplicates.describe_one_work(one, two)
    assert not duplicates.refuted(one, two)


def test_a_refuted_pair_forms_no_group():
    """What `sync` treats as two works, the review file must not offer to merge."""
    assert duplicates.find_groups(records(BERTIN_ONE, BERTIN_TWO)) == []


def test_a_third_record_resembling_both_still_makes_one_group():
    """Refutation removes an edge, not a record.

    An entry compatible with two the evidence separates draws them back into
    one group — and that group is a real question, not an artefact.
    """
    undecided = entry(
        "bertin_adaptive_2020b",
        author="Bertin, Karine",
        title="Adaptive density estimation on bounded domains under mixing conditions",
        year="2020",
    )
    groups = duplicates.find_groups(records(BERTIN_ONE, BERTIN_TWO, undecided))
    assert len(groups) == 1
    assert len(groups[0]) == 3
    assert duplicates.coherence(groups[0]) == "several DOIs"
