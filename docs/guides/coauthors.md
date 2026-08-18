# Working with co-authors

Your co-authors do not need citekeep, do not need to know it exists, and do
not need to change anything. This guide explains what makes that possible.

## The project `.bib` stays ordinary

A project bibliography is a materialised view of your library, but it is also
just a `.bib` file. It compiles on its own, it goes in the repository, and
anyone can edit it by hand. Nothing citekeep-specific is required to use it.

## Their keys are never rewritten

Citation keys a collaborator introduced are part of the project's public
interface. Rewriting them would break their `\cite` commands and their
half-written paragraphs. citekeep never does it automatically.

So when a local key differs from the canonical key in your library, the
materialised entry records the relationship itself:

```bibtex
@article{Smi23,
  author      = {Smith, Jane},
  title       = {…},
  ckmasterkey = {smith_adaptive_2023},
}
```

`ckmasterkey` is citekeep metadata. It stays local, is never donated to the
library, and is removed only by an explicit key migration.

## One thing to watch

Because the alias lives in the materialised `.bib`, **a tool that drops
unknown BibTeX fields will silently remove it**. Bibliography formatters,
reference-manager exports and some editor scripts do exactly that. Configure
them to preserve `ckmasterkey`.

Without it, a later sync can still recover identity from bibliographic
evidence — DOI, arXiv identifier, title — but it cannot reconstruct the
alias-to-library relationship with certainty, and will ask you instead.

Deleting the project `.bib` has the same effect. citekeep treats collaborative
project bibliographies as versioned project files, not disposable build
artefacts, and this is the trade-off that follows.

## What a sync gives back to them

Records the document cites are copied down into the project `.bib`, so the
file your co-authors pull always compiles on its own. Keys cited but held
nowhere are named, with the file citing them, and the command exits non-zero —
a citation that will not resolve is worth learning about before the compiler
says so.

## When the paper is finished

Nothing to do. There is no project registry, no lifecycle, no archive step:
you simply stop synchronising it. The library supports current and future
work; it does not require you to go back and rewrite finished papers.
