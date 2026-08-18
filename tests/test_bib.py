"""Regression tests for the parsing core.

Every case here comes from a bug that actually bit, found by hand while the
tool was still a set of scripts. They are kept as tests so that they cannot
come back.
"""

from citekeep import bib

SAMPLE = """
% a comment
@article{carroll_unexpected_2013,
  author = {Carroll, Raymond J. and Delaigle, Aurore and Hall, Peter},
  title = {Unexpected properties of bandwidth choice},
  volume = {41},
  year = {2013},
}

@book{knuth_texbook_1984,
  author = {Knuth, Donald E.},
  title = {The {\\TeX}book},
  publisher = {Addison-Wesley},
  year = {1984},
}
"""


def test_iter_entries_finds_all():
    entries = list(bib.iter_entries(SAMPLE))
    assert [e[1] for e in entries] == ["carroll_unexpected_2013", "knuth_texbook_1984"]


def test_raw_is_byte_identical():
    """Raw text must survive parsing untouched: brace protection depends on it."""
    entries = {k: raw for _t, k, raw, _b in bib.iter_entries(SAMPLE)}
    assert "{\\TeX}book" in entries["knuth_texbook_1984"]


def test_get_field_handles_nested_braces():
    _t, _k, _r, body = next(
        e for e in bib.iter_entries(SAMPLE) if e[1] == "knuth_texbook_1984"
    )
    assert bib.get_field(body, "title") == "The {\\TeX}book"


def test_string_entries_are_not_references():
    text = '@string{jmva = "J. Multivariate Anal."}\n' + SAMPLE
    assert len(list(bib.iter_entries(text))) == 2


# --- the empty-field bug -------------------------------------------------
#
# `volume = {}` reads as absent through get_field. Appending a second `volume`
# created a duplicate on every run and broke idempotence.

EMPTY = "@article{k,\n  title = {T},\n  volume = {},\n  year = {2020},\n}"


def test_empty_field_reads_as_absent():
    _t, _k, _r, body = next(bib.iter_entries(EMPTY))
    assert bib.get_field(body, "volume") == ""


def test_empty_field_is_detected_in_raw():
    _t, _k, raw, _b = next(bib.iter_entries(EMPTY))
    assert bib.has_empty_field(raw, "volume")
    assert not bib.has_empty_field(raw, "title")


def test_fill_field_does_not_duplicate():
    _t, _k, raw, _b = next(bib.iter_entries(EMPTY))
    filled = bib.fill_field(raw, "volume", "41")
    assert filled.count("volume") == 1
    _t, _k, _r, body = next(bib.iter_entries(filled))
    assert bib.get_field(body, "volume") == "41"


def test_append_fields_adds_before_closing_brace():
    _t, _k, raw, _b = next(bib.iter_entries(EMPTY))
    out = bib.append_fields(raw, [("doi", "10.1/x")])
    _t, _k, _r, body = next(bib.iter_entries(out))
    assert bib.get_field(body, "doi") == "10.1/x"
    assert bib.get_field(body, "year") == "2020"


# --- removing fields -----------------------------------------------------
#
# A real library carries fields that describe someone else's machine: 416
# entries in one corpus held a `file` path under /home/johndoe, imported from a
# borrowed .bib.

FULL = """@article{k,
  author   = {Doe, Jane},
  title    = {Estimation of {DNA} sequences},
  file     = {paper.pdf:/home/johndoe/Docs/paper.pdf:application/pdf},
  urldate  = {2020-01-22},
  year     = {2020},
}"""


def test_drop_fields_removes_only_what_is_named():
    out = bib.drop_fields(FULL, ["file", "urldate"])
    names = [n for n, _v in bib.parse_fields(next(bib.iter_entries(out))[3])]
    assert names == ["author", "title", "year"]


def test_drop_fields_leaves_the_rest_byte_identical():
    """Alignment and brace protection must survive; a diff should show only
    the lines that went."""
    out = bib.drop_fields(FULL, ["file", "urldate"])
    assert "  title    = {Estimation of {DNA} sequences},\n" in out
    assert out.startswith("@article{k,\n")
    assert out.endswith("}")


def test_drop_fields_handles_a_value_spanning_lines():
    """One junk value in 1905 entries wrapped across lines, which is why this
    cannot be done line by line."""
    raw = (
        "@misc{k,\n  optvolume = {{MICCAI} Workshop on Microscopic Image\n"
        "              Analysis},\n  year = {2008},\n}"
    )
    out = bib.drop_fields(raw, ["optvolume"])
    assert "MICCAI" not in out
    assert bib.get_field(next(bib.iter_entries(out))[3], "year") == "2008"


def test_drop_fields_of_the_last_field():
    raw = "@article{k,\n  year = {2020},\n  file = {x.pdf},\n}"
    out = bib.drop_fields(raw, ["file"])
    assert out == "@article{k,\n  year = {2020},\n}"


def test_drop_fields_is_a_no_op_when_nothing_matches():
    assert bib.drop_fields(FULL, ["abstract"]) == FULL


def test_drop_fields_matches_case_insensitively():
    raw = "@article{k,\n  FILE = {x.pdf},\n  year = {2020},\n}"
    assert "x.pdf" not in bib.drop_fields(raw, ["file"])


# --- merging one entry into another --------------------------------------


def test_merge_into_fills_gaps_only():
    """A donor completes; it never corrects. A wrong DOI in a variant being
    discarded must not displace a right one."""
    raw = "@article{k,\n  title = {T},\n  doi = {10.1/right},\n}"
    donor = "title = {T}, doi = {10.2/wrong}, pages = {1--20},"
    out = bib.merge_into(raw, [donor])
    body = next(bib.iter_entries(out))[3]
    assert bib.get_field(body, "doi") == "10.1/right"
    assert bib.get_field(body, "pages") == "1--20"


def test_merge_into_fills_an_empty_field_rather_than_adding_one():
    raw = "@article{k,\n  volume = {},\n  year = {2020},\n}"
    out = bib.merge_into(raw, ["volume = {41},"])
    assert out.count("volume") == 1
    assert bib.get_field(next(bib.iter_entries(out))[3], "volume") == "41"


def test_merge_into_never_duplicates_a_name_it_cannot_fill():
    """`has_empty_field` only sees an empty field that starts its own line.

    Counting the others as absent would append a second copy on every run —
    the bug that grew duplicate fields across a whole corpus.
    """
    raw = "@article{k,\n  year = {2020}, volume = {},\n}"
    out = bib.merge_into(raw, ["volume = {41},"])
    assert out.count("volume") == 1


def test_merge_into_is_idempotent():
    raw = "@article{k,\n  title = {T},\n}"
    once = bib.merge_into(raw, ["title = {T}, pages = {1--20},"])
    assert bib.merge_into(once, ["title = {T}, pages = {1--20},"]) == once


# --- malformed sources ---------------------------------------------------
#
# A stray `=` after a comma: BibTeX tolerates it, parsebib gives up on the
# whole file, so citar shows nothing.

MALFORMED = "@article{k,\n  title = {T},=\n  pages = {1--2},\n}"


def test_malformed_body_is_detected():
    _t, _k, _r, body = next(bib.iter_entries(MALFORMED))
    assert not bib.is_wellformed(body)


def test_repair_keeps_every_valid_field():
    """The first repair lost `pages`: recovery skipped to the next comma and
    swallowed the valid field that followed the typo."""
    _t, _k, _r, body = next(bib.iter_entries(MALFORMED))
    repaired = bib.repair_body(body)
    names = {n.lower() for n, _v in bib.parse_fields(repaired, tolerant=True)}
    assert names == {"title", "pages"}


# --- title comparison ----------------------------------------------------


def test_same_work_tolerates_a_missing_subtitle():
    sigs = {"adaptive estimation", "adaptive estimation a new approach"}
    assert bib.same_work(sigs)


def test_same_work_rejects_different_papers():
    sigs = {"adaptive estimation", "minimax lower bounds"}
    assert not bib.same_work(sigs)


def test_title_signature_ignores_latex_and_accents():
    assert bib.title_signature(r"Estimation \'{e}nonc\'{e}e") == bib.title_signature(
        "Estimation enoncee"
    )


# --- LaTeX cleaning for API queries -------------------------------------


def test_latex_clean_rejoins_accented_names():
    """`Gin\\'{e}` must come out as `Gine`, not `Gin e`.

    The accent command and the braces disappear without leaving a gap, so the
    name stays searchable as one word — which is what the API needs.
    """
    assert bib.latex_clean(r"Gin\'{e}, Evarist") == "Gine, Evarist"
    assert bib.latex_clean(r"M\"{u}ller") == "Muller"


def test_latex_clean_strips_commands():
    assert bib.latex_clean(r"\textbf{Adaptive} $L_2$") == "Adaptive L_2"


def test_latex_clean_leaves_plain_text_alone():
    assert bib.latex_clean("Carroll bandwidth choice") == "Carroll bandwidth choice"


# --- arbitration ---------------------------------------------------------


def test_score_prefers_the_richer_entry():
    poor = ("article", "k", "raw", "title = {T}, year = {2020},", "a.bib")
    rich = (
        "article",
        "k",
        "raw",
        "title = {T}, year = {2020}, doi = {10.1/x}, pages = {1--2},",
        "z.bib",
    )
    assert min([poor, rich], key=bib.score) is rich


def test_score_ties_when_only_a_value_differs():
    """The reason corrections must not go through `score`.

    Two entries with the same fields tie on every meaningful criterion; only
    the origin string separates them, which is arbitrary. Whether a fix was
    accepted used to depend on the alphabetical order of the file path.
    """
    before = ("article", "k", "r", "title = {T}, pages = {100--200},", "master.bib")
    after = ("article", "k", "r", "title = {T}, pages = {105--210},", "master.bib")
    assert bib.score(before) == bib.score(after)


# --- surnames ------------------------------------------------------------
#
# BibTeX allows both name orders, and a library accumulated over decades
# contains both. Taking everything before the comma silently produced
# `evaristgine` for 151 entries out of 2438.


def test_surname_from_last_first():
    assert bib.surname("Giné, Evarist") == "Giné"


def test_surname_from_first_last():
    assert bib.surname("Evarist Giné") == "Giné"
    assert bib.surname("T. Klein") == "Klein"


def test_surname_keeps_nobiliary_particles():
    assert bib.surname("Aad van der Vaart") == "van der Vaart"
    assert bib.surname("van der Vaart, Aad") == "van der Vaart"


def test_surname_of_an_empty_field():
    assert bib.surname("") == ""


def test_citation_key_uses_the_surname_only():
    assert (
        bib.citation_key(["Evarist Giné"], "2010", "Confidence bands")
        == "gine_confidence_2010"
    )
    assert (
        bib.citation_key(["Giné, Evarist"], "2010", "Confidence bands")
        == "gine_confidence_2010"
    )
