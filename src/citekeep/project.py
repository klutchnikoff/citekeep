"""Keeping a project's bibliography in step with what it cites.

The downward half of the synchronisation. A document cites keys; its .bib
must hold exactly those entries, taken from the library. Nothing here decides
anything about the library — it only reads it.

Three things are worth reporting, and only the first is acted on:

- **missing** — cited, held by the library, absent from the project .bib.
  Copied in. This is the ordinary case and needs no supervision.
- **unknown** — cited and found nowhere. A citation that will not resolve at
  compile time; the sooner it is named, the cheaper.
- **unused** — in the project .bib and cited by nothing. Reported, never
  removed: a .bib may be shared between documents, or hold an entry someone
  is about to cite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from . import bib

# A comment runs to the end of the line, unless the percent sign is escaped.
COMMENT = re.compile(r"(?<!\\)%.*")

# Every citation command of natbib and biblatex shares the stem "cite":
# \citet, \citep, \citealp, \nocite, \parencite, \autocite, \footcite… The
# optional arguments of \citep[see][p.~5]{a,b} sit between command and keys.
CITE = re.compile(
    r"\\[a-zA-Z]*[Cc]ite[a-zA-Z]*\*?\s*"
    r"(?:\[[^]]*\]\s*)*\{([^{}]*)\}"
)

# Where a document declares its bibliography, in either dialect.
DECLARED = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^{}]*)\}")

SKIP = {".git", "_minted", "build", "out", "auto", "node_modules"}


class MaterializationPlan(NamedTuple):
    missing: tuple  # library records to copy in
    unknown: tuple  # (key, sorted files citing it)
    unused: tuple  # keys held by the project .bib that nothing cites


def strip_comments(text):
    """Remove LaTeX comments.

    A commented-out `\\citep` is not a citation; counting it would send us
    looking for an entry the document does not want.
    """
    return COMMENT.sub("", text)


def cited_keys(text):
    """Every citation key in one LaTeX source."""
    out = set()
    for group in CITE.findall(strip_comments(text)):
        for key in group.split(","):
            key = key.strip()
            if key:
                out.add(key)
    return out


def bibliographies(text):
    """The .bib files the document declares, without their extension."""
    out = []
    for group in DECLARED.findall(strip_comments(text)):
        for name in group.split(","):
            name = name.strip()
            if name and name not in out:
                out.append(name)
    return out


def sources(root):
    """The LaTeX sources of a project, build directories left aside."""
    root = Path(root).expanduser()
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob("*.tex")
        if not any(
            part in SKIP or part.startswith(".")
            for part in path.relative_to(root).parts[:-1]
        )
    )


def scan(root):
    """Return ``(cited, declared)`` for a project.

    CITED maps each key to the files citing it — a key that will not resolve
    is far easier to fix when you know where it is written.
    """
    cited, declared = {}, []
    for path in sources(root):
        text = bib.read_text(path)
        for key in cited_keys(text):
            cited.setdefault(key, set()).add(path)
        for name in bibliographies(text):
            candidate = path.parent / name
            if candidate.suffix != ".bib":
                candidate = candidate.with_suffix(".bib")
            if candidate not in declared:
                declared.append(candidate)
    return cited, declared


def plan_materialization(library, project, cited):
    """Work out what a project .bib is missing.

    LIBRARY and PROJECT are lists of `duplicates.Record`; CITED maps keys to
    the files citing them. Keys are compared as written: the library's are
    normalised, and a document citing an older key is told so rather than
    guessed at.
    """
    held = {record.key for record in project}
    available = {record.key: record for record in library}

    missing = tuple(
        available[key] for key in sorted(cited) if key not in held and key in available
    )
    unknown = tuple(
        (key, sorted(str(p) for p in cited[key]))
        for key in sorted(cited)
        if key not in held and key not in available
    )
    unused = tuple(sorted(held - set(cited)))
    return MaterializationPlan(missing, unknown, unused)


def apply_materialization(text, missing):
    """Return the project .bib with the missing entries appended.

    Appended rather than merged into a sorted whole: a project bibliography
    may be hand-ordered, or shared with a collaborator who did not ask for it
    to be rearranged. We do not reformat a file we do not own.
    """
    if not missing:
        return text
    body = "\n\n".join(record.raw for record in missing)
    if not text.strip():
        return body + "\n"
    return text.rstrip("\n") + "\n\n" + body + "\n"


def write_record(text, entry, key):
    """Put ENTRY into TEXT under KEY.  Return ``(new text, what happened)``.

    KEY is the name the library uses, which need not be the one the record
    arrived with: a work the library already holds keeps its key, so that the
    citation written in the document resolves on both sides.

    When the key is already there the record completes it rather than
    replacing it — the same asymmetry as everywhere else, since what is
    already recorded was chosen and what is arriving was merely found.
    """
    entry = bib.ENTRY_HEAD.sub(
        lambda m: f"@{m.group(1)}{{{key},", entry.strip(), count=1
    )
    _type, _key, _raw, body = next(bib.iter_entries(entry))

    for _t, existing_key, raw, _b in bib.iter_entries(text):
        if existing_key == key:
            merged = bib.merge_into(raw, [body])
            if merged == raw:
                return text, "unchanged"
            return text.replace(raw, merged, 1), "completed"

    if not text.strip():
        return entry + "\n", "added"
    return text.rstrip("\n") + "\n\n" + entry + "\n", "added"
