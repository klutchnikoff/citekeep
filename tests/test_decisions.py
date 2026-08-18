"""Tests for reading a reviewed report and planning its effect."""

from citekeep import bib, decisions, duplicates

REPORT = """\
# Doublons

## beek   [several DOIs]   -> bertin_adaptive_2019
  drop a  BKKP
        2019  @article  16 champs
        Adaptive density estimation on bounded domains
  keep a  BEEK
        2019  @article  16 champs
  keep b  MR4097810
        2020  @article  15 champs
  drop b  BKLP
        2020  @article  14 champs
  hold    MR4029144
        2019  @article  15 champs

## other   -> doe_minimax_2001
  keep  A
  drop  B
"""


def test_parse_reads_verbs_letters_and_groups():
    parsed = decisions.parse(REPORT)
    assert [(d.group, d.verb, d.part, d.key) for d in parsed] == [
        ("beek", "drop", "a", "BKKP"),
        ("beek", "keep", "a", "BEEK"),
        ("beek", "keep", "b", "MR4097810"),
        ("beek", "drop", "b", "BKLP"),
        ("beek", "hold", "", "MR4029144"),
        ("other", "keep", "", "A"),
        ("other", "drop", "", "B"),
    ]


def test_descriptive_lines_are_never_read_as_decisions():
    """A title beginning with a verb would otherwise become a decision."""
    text = (
        "## g\n  keep  A\n        2019  @article  3 champs\n"
        "        Hold on to your priors\n"
    )
    assert [d.key for d in decisions.parse(text)] == ["A"]


def test_annotations_are_allowed_anywhere():
    text = "## g\n  keep  A\n  # à revoir avec Karine\n  drop  B\n"
    assert len(decisions.parse(text)) == 2


# --- validation ----------------------------------------------------------


def test_a_damaged_verb_line_is_reported():
    """The failure mode a real review produced: a value pasted over the verb.

    Such a line is not a decision, so it is skipped — and the entry silently
    keeps its own key. It has to be surfaced.
    """
    text = (
        "## g\n  keep  A\n"
        "  doi:10.1093/biomet/82.2.327  B\n"
        "        1995  @article  6 champs\n"
    )
    assert [d.key for d in decisions.parse(text)] == ["A"]
    assert [n for n, _l in decisions.unread_lines(text)] == [3]


def test_descriptive_and_comment_lines_are_not_reported():
    assert decisions.unread_lines(REPORT) == []
    assert decisions.unread_lines("## g\n  keep  A\n  # à revoir\n") == []


def test_drops_without_a_keep_are_reported():
    problems = decisions.validate(
        decisions.parse("## g\n  drop  A\n  drop  B\n"), {"A", "B"}
    )
    assert any("sans « keep »" in p for p in problems)


def test_two_keeps_in_one_part_are_reported():
    problems = decisions.validate(
        decisions.parse("## g\n  keep  A\n  keep  B\n  drop  C\n"), {"A", "B", "C"}
    )
    assert any("2 « keep »" in p for p in problems)


def test_an_unknown_key_is_reported():
    problems = decisions.validate(decisions.parse("## g\n  keep  Zz\n"), {"A"})
    assert any("clé inconnue" in p for p in problems)


def test_letters_make_two_keeps_legitimate():
    assert (
        decisions.validate(
            decisions.parse(REPORT),
            {"BKKP", "BEEK", "MR4097810", "BKLP", "MR4029144", "A", "B"},
        )
        == []
    )


# --- planning ------------------------------------------------------------


def entry(key, **fields):
    fields.setdefault("author", "Doe, Jane")
    return bib.render_entry("article", key, fields)


LIBRARY = "\n".join(
    [
        entry(
            "BKKP",
            title="Adaptive density estimation on bounded domains",
            year="2019",
            author="Bertin, K. and El Kolei, S.",
            doi="10.1/aihp",
        ),
        entry(
            "BEEK",
            title="Adaptive density estimation on bounded domains",
            year="2019",
            author="Bertin, K. and El Kolei, S.",
            volume="55",
        ),
        entry(
            "MR4097810",
            title="Adaptive density estimation under mixing",
            year="2020",
            author="Bertin, K. and Prieur, C.",
            doi="10.2/ejs",
        ),
        entry(
            "BKLP",
            title="Adaptive density estimation under mixing",
            year="2020",
            author="Bertin, K. and Prieur, C.",
            pages="1--30",
        ),
    ]
)


def make_plan(report, text=LIBRARY):
    entries = duplicates.records(text, origin="master.bib")
    return entries, decisions.plan(entries, decisions.parse(report))


def test_each_part_gets_its_own_key_from_its_keep():
    """The correction that prompted the letters.

    Two works in one block have different authors and years, so their keys
    differ naturally. The letter partitions; it never suffixes.
    """
    _entries, result = make_plan(REPORT)
    assert result.mapping["BEEK"] == "bertin_adaptive_2019"
    assert result.mapping["MR4097810"] == "bertin_adaptive_2020"
    assert result.collisions == {}


def test_dropped_keys_map_to_their_survivor():
    """What lets a project's .bib and its \\cite commands be rewritten."""
    _entries, result = make_plan(REPORT)
    assert result.mapping["BKKP"] == "bertin_adaptive_2019"
    assert result.mapping["BKLP"] == "bertin_adaptive_2020"


def test_entries_no_decision_mentions_are_still_renamed():
    text = LIBRARY + entry("Zz", title="Minimax bounds", year="2001")
    _entries, result = make_plan("## g\n", text)
    assert result.mapping["Zz"] == "doe_minimax_2001"


def test_distinct_works_sharing_a_key_are_suffixed():
    text = "\n".join(
        [
            entry(
                "one",
                title="Adaptive estimation",
                year="2019",
                author="Roe, R.",
                doi="10.1/a",
            ),
            entry(
                "two",
                title="Adaptive estimation",
                year="2019",
                author="Roe, R.",
                doi="10.2/b",
            ),
        ]
    )
    _entries, result = make_plan("## g\n  hold  one\n  hold  two\n", text)
    assert set(result.mapping.values()) == {"roe_adaptive_2019a", "roe_adaptive_2019b"}
    assert result.collisions == {"roe_adaptive_2019": ["one", "two"]}


def test_hold_leaves_an_entry_alone():
    _entries, result = make_plan(REPORT)
    assert [m.survivor for m in result.merges] == ["BEEK", "MR4097810"]
    assert all("MR4029144" not in m.donors for m in result.merges)


# --- merges that join two different works --------------------------------


def test_a_mistyped_letter_merges_the_wrong_pair():
    """The failure the letters make possible, from the real review.

    `drop a` instead of `drop b` merged a preprint into an unrelated paper by
    the same author. The file parses, the plan is consistent, and the only
    visible damage is in the key mapping — a citation silently redirected to
    another article.
    """
    text = "\n".join(
        [
            entry(
                "beta",
                author="Bertin, K.",
                year="2014",
                title="Adaptive estimation of a density function using beta kernels",
                doi="10.1051/ps/2014010",
            ),
            entry(
                "cond_published",
                author="Bertin, K.",
                year="2016",
                title="Adaptive pointwise estimation of conditional density function",
                eprint="1312.7402",
                doi="10.1214/14-AIHP665",
            ),
            entry(
                "cond_preprint",
                author="Bertin, K.",
                year="2014",
                title="Adaptive estimation of conditional density function",
                eprint="1312.7402",
            ),
        ]
    )
    wrong = "## g\n  keep a  beta\n  keep b  cond_published\n  drop a  cond_preprint\n"
    _entries, result = make_plan(wrong, text)
    assert result.suspects == (("beta", "cond_preprint"),)

    right = "## g\n  hold  beta\n  keep  cond_published\n  drop  cond_preprint\n"
    _entries, result = make_plan(right, text)
    assert result.suspects == ()


def test_a_retitled_preprint_is_not_reported():
    """Titles disagree, yet the arXiv identifier vouches for the pair.

    Li et al. 2020 "Density estimation and modeling on symmetric spaces"
    became Chevallier et al. 2022 "Exponential-wrapped distributions on
    symmetric spaces". Reporting this would train the reviewer to ignore the
    warning.
    """
    text = "\n".join(
        [
            entry(
                "published",
                author="Chevallier, E.",
                year="2022",
                title="Exponential-wrapped distributions on symmetric spaces",
                eprint="2009.01983",
                doi="10.1137/21M1461551",
            ),
            entry(
                "preprint",
                author="Li, D.",
                year="2020",
                title="Density estimation and modeling on symmetric spaces",
                eprint="2009.01983",
            ),
        ]
    )
    _entries, result = make_plan("## g\n  keep  published\n  drop  preprint\n", text)
    assert result.suspects == ()


def test_a_shared_doi_also_vouches_for_a_merge():
    text = "\n".join(
        [
            entry(
                "a",
                title="Smooth optimum kernel estimators near endpoints",
                year="1991",
                doi="10.1/x",
            ),
            entry("b", title="On boundary effects", year="1991", doi="10.1/X"),
        ]
    )
    _entries, result = make_plan("## g\n  keep  a\n  drop  b\n", text)
    assert result.suspects == ()


# --- applying ------------------------------------------------------------


def test_merge_fills_gaps_without_overwriting():
    """A wrong value in a discarded variant must not displace a right one."""
    entries, result = make_plan(REPORT)
    out = decisions.apply_plan(entries, result)
    body = next(
        b for _t, k, _r, b in bib.iter_entries(out) if k == "bertin_adaptive_2019"
    )
    assert bib.get_field(body, "volume") == "55"  # the survivor's own
    assert bib.get_field(body, "doi") == "10.1/aihp"  # donated


def test_apply_removes_the_donors_and_renames_the_rest():
    entries, result = make_plan(REPORT)
    keys = [
        k for _t, k, _r, _b in bib.iter_entries(decisions.apply_plan(entries, result))
    ]
    assert keys == ["bertin_adaptive_2019", "bertin_adaptive_2020"]


def test_apply_keeps_raw_text_intact():
    """Brace-protected capitalisation must survive: reformatting would lose it."""
    text = entry("k", title="Estimation of {DNA} sequences", year="2020")
    entries, result = make_plan("## g\n", text)
    assert "{DNA}" in decisions.apply_plan(entries, result)


def test_apply_is_a_no_op_without_decisions_beyond_renaming():
    entries, result = make_plan("")
    out = decisions.apply_plan(entries, result)
    assert len(list(bib.iter_entries(out))) == len(entries)


def test_deduplication_can_leave_all_surviving_keys_unchanged():
    text = entry("Original", title="A title", year="2020")
    entries = duplicates.records(text)
    result = decisions.plan(entries, [], normalise_keys=False)
    assert result.mapping == {"Original": "Original"}
    assert decisions.apply_text(text, entries, result) == text


def test_lossless_application_preserves_directives_comments_and_trailing_text():
    first = entry("keep", title="A title", year="2020")
    second = entry("drop", title="A title", year="2020", doi="10.1/a")
    text = (
        "@string{j = {Journal}}\n% before\n"
        + first
        + "\n% between\n"
        + second
        + "\n% after\n"
    )
    entries = duplicates.records(text)
    reviewed = decisions.parse("## a\n  keep  keep\n  drop  drop\n")
    result = decisions.plan(entries, reviewed, normalise_keys=False)
    out = decisions.apply_text(text, entries, result)
    assert "@string{j = {Journal}}" in out
    assert "% before" in out and "% between" in out and "% after" in out
    assert [key for _type, key, _raw, _body in bib.iter_entries(out)] == ["keep"]
    assert "10.1/a" in out
