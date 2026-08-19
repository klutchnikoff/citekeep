"""BibTeX parsing and entry arbitration.

This module is deliberately pure: it reads text, returns data structures, and
never touches the filesystem beyond `read_text`. Everything that decides *which*
variant of an entry wins lives here, so that every command arbitrates the same
way.

Entries are kept as their **raw source text**. Reformatting them would destroy
brace-protected capitalisation (`{DNA}`) and LaTeX commands, and would turn
every operation into a full-file rewrite in version control.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

ENTRY_HEAD = re.compile(r"@(\w+)\s*\{\s*([^,\s}]+)\s*,", re.IGNORECASE)

# @string, @preamble and @comment are not references.
NON_ENTRY = {"string", "preamble", "comment"}

# Fields that mark a carefully filled entry, used to break ties in `score`.
RICH_FIELDS = (
    "doi",
    "mrnumber",
    "isbn",
    "issn",
    "pages",
    "url",
    "publisher",
    "volume",
    "number",
)

IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_+:.\-]*")


class EntrySpan(NamedTuple):
    """One reference entry and its exact location in a BibTeX document."""

    start: int
    end: int
    type: str
    key: str
    raw: str
    body: str


def read_text(path):
    """Read a .bib file whatever its encoding.

    Bibliographies accumulated over decades mix UTF-8 and latin-1, often
    without declaring it.  Filesystem errors are deliberately not hidden: an
    empty bibliography and an unreadable one require very different actions.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Every byte sequence is valid latin-1, which makes this a reliable
        # fallback while retaining the historical compatibility promise.
        return data.decode("latin-1")


def iter_entry_spans(text):
    """Yield reference entries with their exact spans in TEXT.

    Brace counting rather than a regex: entry bodies nest braces arbitrarily
    deep, and `raw` must come out byte-identical to the source.

    Advancing past each complete entry also prevents an ``@type{`` sequence in
    a field value from being mistaken for another top-level entry.
    """
    position = 0
    while match := ENTRY_HEAD.search(text, position):
        entry_type = match.group(1).lower()
        depth = 0
        found_end = None
        for j in range(match.start(), len(text)):
            char = text[j]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    found_end = j + 1
                    break
        if found_end is None:
            # Keep the old tolerant parsing behaviour for now, but do not scan
            # the malformed fragment repeatedly.
            position = match.end()
            continue
        if entry_type not in NON_ENTRY:
            yield EntrySpan(
                match.start(),
                found_end,
                entry_type,
                match.group(2),
                text[match.start() : found_end],
                text[match.end() : found_end - 1],
            )
        position = found_end


def iter_entries(text):
    """Yield ``(type, key, raw, body)`` for every entry in TEXT."""
    for span in iter_entry_spans(text):
        yield span.type, span.key, span.raw, span.body


def transform_entries(text, transform):
    """Transform reference entries without touching surrounding text.

    TRANSFORM receives ``(type, key, raw, body)`` and returns the replacement
    raw entry.  Directives, comments, whitespace and malformed fragments are
    copied byte-for-byte.
    """
    out, position = [], 0
    for span in iter_entry_spans(text):
        out.append(text[position : span.start])
        out.append(transform(span.type, span.key, span.raw, span.body))
        position = span.end
    out.append(text[position:])
    return "".join(out)


def get_field(body, name):
    """Return the value of field NAME, honouring nested braces.

    Returns an empty string both when the field is absent and when it is
    present but empty (``volume = {}``). Callers that need to tell those apart
    must look at the raw text — see `has_empty_field`.
    """
    match = re.search(r"\b" + name + r"\s*=\s*", body, re.IGNORECASE)
    if not match:
        return ""
    i = match.end()
    while i < len(body) and body[i] in " \t\n":
        i += 1
    if i >= len(body):
        return ""
    if body[i] in '{"':
        opener, depth, out = body[i], 1, []
        for j in range(i + 1, len(body)):
            char = body[j]
            if opener == "{":
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        break
            elif char == '"':
                break
            out.append(char)
        return "".join(out)
    return re.split(r"[,\n]", body[i:])[0].strip()


def year_of(body):
    """The publication year, whichever spelling the source uses.

    biblatex replaced `year` with `date`, and Zotero's biblatex export uses it
    exclusively — a whole project bibliography can hold not one `year` field.
    Reading only `year` there gives every entry the same "no date" key, and
    unrelated papers by one author collide.

    `date` may carry a month (``2025-01``) or a range (``2020/2021``); the
    first four-digit group is the year in both.
    """
    year = get_field(body, "year").strip()
    if year:
        return year
    match = re.search(r"\d{4}", get_field(body, "date"))
    return match.group(0) if match else ""


def journal_of(body):
    """The journal or book title, whichever spelling the source uses."""
    for name in ("journal", "journaltitle", "booktitle"):
        value = get_field(body, name).strip()
        if value:
            return value
    return ""


def has_empty_field(raw, name):
    """Is field NAME present in RAW but empty?

    ``volume = {}`` is common in hand-maintained sources. Treating it as
    absent and appending a second ``volume`` would create a duplicate on every
    run; it must be *filled* instead.
    """
    return bool(
        re.search(
            rf"(?im)^[ \t]*{re.escape(name)}[ \t]*="
            rf"[ \t]*(\{{[ \t]*\}}|\"[ \t]*\")",
            raw,
        )
    )


def fill_field(raw, name, value):
    """Replace the empty value of field NAME in RAW with VALUE."""
    return re.sub(
        rf"(?im)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*)"
        rf"(\{{[ \t]*\}}|\"[ \t]*\")",
        lambda m: m.group(1) + "{" + value + "}",
        raw,
        count=1,
    )


def append_fields(raw, pairs):
    """Return RAW with PAIRS appended as new fields before the closing brace."""
    if not pairs:
        return raw
    width = max(len(name) for name, _ in pairs)
    extra = "".join(f"  {name.ljust(width)} = {{{value}}},\n" for name, value in pairs)
    raw = raw.rstrip()
    assert raw.endswith("}")
    raw = raw[:-1].rstrip()
    if not raw.endswith(","):
        raw += ","
    return raw + "\n" + extra + "}"


# Names that designate the same thing. BibTeX and biblatex disagree, and a
# library fed by both must not end up holding `year` next to `date` and
# `journal` next to `journaltitle` in one entry. The first name of each group
# is the one this tool considers canonical.
EQUIVALENT_FIELDS = (
    ("year", "date"),
    ("journal", "journaltitle"),
    ("language", "langid"),
    ("keywords", "keyword"),
    ("eprint", "arxivid"),
    ("zmnumber", "zbl"),
)

_CANONICAL = {name: group[0] for group in EQUIVALENT_FIELDS for name in group}

# Fields that describe a machine, a session or a catalogue rather than the
# work. They ride along in borrowed .bib files — one library held 416 file
# paths pointing at a stranger's home directory — and re-enter on every merge
# unless a merge refuses to carry them.
IGNORED_FIELDS = frozenset(
    {
        "file",
        "pdf",
        "urldate",
        "shorttitle",
        "rights",
        "copyright",
        "bdsk-url-1",
        "bdsk-url-2",
        "timestamp",
        "date-added",
        "date-modified",
        "owner",
        "added-at",
        "interhash",
        "intrahash",
        "read",
        "rating",
        "biburl",
        "bibsource",
        "ppn_gvk",
        "adsurl",
        "adsnote",
        # Relationship metadata carried by project views, never by the master.
        "ckmasterkey",
    }
)


def set_field(raw, name, value):
    """Set a simple braced field, appending it when it is absent.

    This is primarily used for citekeep's own key metadata, whose value cannot
    contain nested braces. Existing formatting around the field is retained.
    """
    replaced = replace_field_value(raw, name, value)
    if replaced is not None:
        return replaced
    return append_fields(raw, [(name.lower(), value)])


def replace_field_value(raw, name, value):
    """Replace one field's value losslessly, or return None if absent."""
    head = ENTRY_HEAD.match(raw)
    if not head:
        return None
    body_start, body_end = head.end(), raw.rindex("}")
    body = raw[body_start:body_end]
    for found, _old, start, end in _scan(body, tolerant=True):
        if found.lower() != name.lower():
            continue
        equals = body.find("=", start, end)
        value_start = equals + 1
        while value_start < end and body[value_start].isspace():
            value_start += 1
        replacement = body[start:value_start] + "{" + value + "}"
        changed = body[:start] + replacement + body[end:]
        return raw[:body_start] + changed + raw[body_end:]
    return None


def canonical(name):
    """The name under which FIELD's meaning is tracked."""
    return _CANONICAL.get(name.lower(), name.lower())


def donatable(body):
    """Fields of BODY worth carrying into another entry.

    Yields ``(name, canonical name, value)``, skipping empty values and
    anything that describes the source rather than the work.
    """
    for name, _value in parse_fields(body, tolerant=True) or []:
        lowered = name.lower()
        if lowered in IGNORED_FIELDS:
            continue
        value = get_field(body, name).strip()
        if value:
            yield lowered, canonical(lowered), value


def merge_into(raw, donor_bodies):
    """Return RAW completed by the fields it is missing, taken from DONORS.

    RAW's own values are never overwritten: a donor can only fill a gap — a
    field absent, or present but empty. That asymmetry is what makes a merge
    safe to run without re-reading every value, since a wrong DOI in a
    discarded variant cannot displace a right one. Corrections are a separate
    operation, made deliberately.
    """
    # Every name already present counts as taken, even one whose value is
    # empty. `has_empty_field` only recognises an empty field that starts its
    # own line; treating the others as absent would append a second copy on
    # every run, which is how a whole corpus once grew duplicate fields.
    have = {canonical(name) for name, _v in (parse_fields(raw, tolerant=True) or [])}
    extra = []
    for body in donor_bodies:
        for name, key, value in donatable(body):
            if has_empty_field(raw, name):
                raw = fill_field(raw, name, value)
                have.add(key)
            elif key not in have:
                extra.append((name, value))
                have.add(key)
    return append_fields(raw, extra) if extra else raw


def count_fields(body):
    return len(re.findall(r"\b\w+\s*=", body))


class _Malformed(Exception):
    """A body that is not a sequence of ``field = value`` pairs."""


def _scan(body, tolerant=False):
    """Yield ``(name, value, start, end)`` for each field in BODY.

    START is the offset of the field name and END the offset just past its
    value; the separating comma lies beyond END. The offsets are what lets a
    field be removed without reformatting everything around it.
    """
    i, n = 0, len(body)
    while True:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            return
        start = i
        match = IDENT.match(body, i)
        ok = bool(match)
        if ok:
            i = match.end()
            while i < n and body[i] in " \t\r\n":
                i += 1
            ok = i < n and body[i] == "="
        if not ok:
            if not tolerant:
                raise _Malformed
            # Skip ONLY the offending fragment: running to the next comma
            # would swallow the valid field that follows it.
            i = match.end() if match else start + 1
            continue
        name, i = match.group(0), i + 1
        value_start = i
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            if tolerant:
                return
            raise _Malformed
        char = body[i]
        if char == "{":
            depth = 0
            while i < n:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        elif char == '"':
            i += 1
            while i < n and body[i] != '"':
                i += 1
            i = min(i + 1, n)
        else:
            match2 = re.match(r"[^,\s]+", body[i:])
            i += match2.end() if match2 else 1
        yield name, body[value_start:i].strip(), start, i
        while i < n and body[i] not in ",":
            if not body[i].isspace() and not tolerant:
                raise _Malformed
            i += 1


def parse_fields(body, tolerant=False):
    """Return ``[(name, raw_value)]`` for a body, or None if malformed.

    With TOLERANT, unparsable fragments are skipped instead of aborting.
    """
    try:
        return [(name, value) for name, value, _s, _e in _scan(body, tolerant)]
    except _Malformed:
        return None


def drop_fields(raw, names):
    """Return RAW without the fields in NAMES, matched case-insensitively.

    Everything else stays byte-identical: brace-protected capitalisation and
    hand-made alignment survive, and a diff shows only the lines that went.
    Removing a field is not cosmetic — a `file` field can name a path on
    someone else's machine, and a stale `urldate` outlives what it describes.
    """
    wanted = {name.lower() for name in names}
    head = ENTRY_HEAD.match(raw)
    if not head:
        return raw
    start, end = head.end(), raw.rindex("}")
    body = raw[start:end]
    cuts = [
        (s, e)
        for name, _v, s, e in _scan(body, tolerant=True)
        if name.lower() in wanted
    ]
    if not cuts:
        return raw

    out, last = [], 0
    for cut_start, cut_end in cuts:
        # Take the separating comma and the empty line it would leave.
        while cut_end < len(body) and body[cut_end] in " \t":
            cut_end += 1
        if cut_end < len(body) and body[cut_end] == ",":
            cut_end += 1
        while cut_end < len(body) and body[cut_end] in " \t":
            cut_end += 1
        if cut_end < len(body) and body[cut_end] == "\n":
            cut_end += 1
        # And the indentation that preceded the field name.
        while cut_start > last and body[cut_start - 1] in " \t":
            cut_start -= 1
        out.append(body[last:cut_start])
        last = cut_end
    out.append(body[last:])
    return raw[:start] + "".join(out) + raw[end:]


def is_wellformed(body):
    """Is BODY a valid sequence of ``field = value`` pairs?

    Sources contain typos — a comma followed by a stray ``=``, an extra brace —
    that BibTeX tolerates but that make parsebib, and therefore citar, give up
    on the whole file. Such entries are repaired rather than propagated.
    """
    return parse_fields(body, tolerant=False) is not None


def repair_body(body):
    """Rebuild a body from its parsable fields only."""
    fields = parse_fields(body, tolerant=True) or []
    width = max((len(name) for name, _ in fields), default=0)
    return "\n" + "".join(
        f"  {name.rjust(width)} = {value},\n" for name, value in fields
    )


def title_signature(raw_title):
    """A comparable signature: no accents, no LaTeX, no punctuation."""
    text = unicodedata.normalize("NFKD", raw_title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Spacing commands carry no text; other commands wrap text worth keeping.
    text = re.sub(r"\\(?:hspace|vspace|kern|hskip)\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)
    text = re.sub(r"\\.", "", text, flags=re.DOTALL)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def same_work(signatures):
    """Same work if every title is a prefix of the longest one.

    Catches the common case where one source records a subtitle and another
    does not, without treating two genuinely different papers as one.
    """
    if not signatures:
        return True
    longest = max(signatures, key=len)
    return all(longest.startswith(s) for s in signatures)


def latex_clean(text):
    """Strip LaTeX markup before sending a field to a web API.

    French and German names are full of it — ``\\'e``, ``{\\"o}``, ``\\v{s}`` —
    and sending it raw makes the query fail in a way indistinguishable from
    "no such record".
    """
    text = re.sub(r"\\[a-zA-Z]+", " ", text or "")
    text = re.sub(r"\\.", "", text)
    text = re.sub(r"[{}$\\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def score(entry):
    """Sort key for choosing between variants of the same key: richest first.

    ENTRY is ``(type, key, raw, body, origin)``.

    NOTE: this ranks variants *found* in different files. It must never be used
    to decide whether a correction supersedes what is already stored — two
    entries differing only in a value tie here, and the tie would be broken by
    origin, which is arbitrary. Corrections go through an explicit
    authoritative flag instead.
    """
    _type, _key, raw, body, origin = entry
    rich = sum(1 for field in RICH_FIELDS if get_field(body, field))
    return (-count_fields(body), -rich, -len(raw), origin)


def entries_by_key(text, origin):
    """Index a bibliography by lowercase key."""
    return {
        key.lower(): (entry_type, key, raw, body, origin)
        for entry_type, key, raw, body in iter_entries(text)
    }


# --- building entries ----------------------------------------------------
#
# Key construction and rendering belong here rather than in a source module:
# every source produces the same kind of entry, and a record fetched from
# zbMATH must land on the same key as the same paper fetched from CrossRef.
# Two keys for one paper is a mistake no later deduplication can undo.

# Words never used to build a citation key. Both languages, because a corpus
# mixes them.
KEY_STOPWORDS = {
    "the",
    "a",
    "an",
    "on",
    "of",
    "for",
    "and",
    "in",
    "to",
    "with",
    "une",
    "un",
    "le",
    "la",
    "les",
    "des",
    "sur",
    "de",
    "du",
}

_ACCENTS = (
    ("éèêë", "e"),
    ("àâä", "a"),
    ("ç", "c"),
    ("öô", "o"),
    ("üûù", "u"),
    ("îï", "i"),
    ("ø", "o"),
    ("ñ", "n"),
)


def slug(text):
    """Reduce TEXT to lowercase ASCII letters and digits."""
    text = (text or "").lower()
    for accented, plain in _ACCENTS:
        for char in accented:
            text = text.replace(char, plain)
    return re.sub(r"[^a-z0-9]", "", text)


# Nobiliary particles: part of the surname, not of the given names.
PARTICLES = {
    "van",
    "von",
    "de",
    "del",
    "della",
    "der",
    "den",
    "di",
    "da",
    "dos",
    "du",
    "la",
    "le",
    "ten",
    "ter",
    "vander",
}


def surname(author):
    """Extract the surname from one author field.

    BibTeX allows both ``"Giné, Evarist"`` and ``"Evarist Giné"``, and a
    library accumulated over decades contains both — 151 entries out of 2438
    in the corpus this was built for. Taking everything before the comma works
    for the first form and silently produces ``evaristgine`` for the second.
    """
    author = (author or "").strip()
    if "," in author:
        return author.split(",")[0].strip()
    words = author.split()
    if not words:
        return ""
    # "Aad van der Vaart" -> "van der Vaart": the surname starts at the first
    # particle, which is never a given name.
    for i, word in enumerate(words):
        if word.lower().strip(".") in PARTICLES:
            return " ".join(words[i:])
    return words[-1]


def title_words(title, count=1):
    """The first COUNT significant words of TITLE, slugged.

    Naming a record and recognising one both begin by asking a title for its
    opening words. They want different numbers of them, and there is no reason
    for them to disagree about which words those are.
    """
    words = []
    for raw in re.findall(r"[A-Za-zÀ-ÿ]+", title or ""):
        word = slug(raw)
        if word and word not in KEY_STOPWORDS:
            words.append(word)
            if len(words) == count:
                break
    return tuple(words)


def citation_key(authors, year, title):
    """Build ``author_word_year``.

    This mirrors the dominant convention of Zotero exports, so that records
    fetched from any source land under the key an existing library already
    uses.

    AUTHORS is a list of author fields, in either BibTeX name order.
    """
    last = slug(surname(authors[0])) if authors else ""
    words = title_words(title, 1)
    return f"{last or 'anon'}_{words[0] if words else 'untitled'}_{year or 'nd'}"


# Order in which fields are written. Anything unlisted follows, sorted, so a
# new field from a new source never silently disappears.
FIELD_ORDER = (
    "author",
    "editor",
    "title",
    "booktitle",
    "journal",
    "shortjournal",
    "series",
    "volume",
    "number",
    "pages",
    "year",
    "publisher",
    "address",
    "edition",
    "doi",
    "eprint",
    "eprinttype",
    "isbn",
    "issn",
    "zmnumber",
    "mrnumber",
    "mrclass",
    "keywords",
    "abstract",
    "note",
    "url",
)


def render_entry(entry_type, key, fields):
    """Render ``@type{key, ...}`` from a mapping of field names to values.

    Empty values are dropped: a field present but empty is worse than absent,
    since it reads as absent while blocking a later fill.
    """
    present = [
        (name, str(value).strip())
        for name, value in fields.items()
        if str(value).strip()
    ]
    if not present:
        return f"@{entry_type}{{{key},\n}}\n"

    known = [(n, v) for n, v in present if n in FIELD_ORDER]
    known.sort(key=lambda nv: FIELD_ORDER.index(nv[0]))
    extra = sorted(nv for nv in present if nv[0] not in FIELD_ORDER)
    ordered = known + extra

    width = max(len(name) for name, _ in ordered)
    body = "".join(f"  {name.ljust(width)} = {{{value}}},\n" for name, value in ordered)
    return f"@{entry_type}{{{key},\n{body}}}\n"
