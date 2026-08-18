# citekeep

**Clean a reference once. Reuse it in every LaTeX project.**

You write several papers at once, with different co-authors. Each has its own
`.bib`. The same reference gets typed again in each of them, a little
differently every time, and the one you cleaned up two years ago sits in a
folder you have since archived.

citekeep gives you one canonical library — a plain `.bib` file you own — and
materialises each project's bibliography from it without leaving your editor.
It searches the project first, then your library, then zbMATH, with CrossRef as
a fallback.

Three things follow from that:

- **Your co-authors need nothing.** The project keeps an ordinary,
  self-contained `.bib`, and their citation keys are never rewritten.
- **It works offline.** A reference met once stays searchable, and metadata
  corrected once is never repaired a second time.
- **It refuses rather than guesses.** When the evidence does not settle
  whether two records are one work, citekeep says so and writes nothing.

![citekeep searches the project, the personal library and zbMATH, then writes
the selected record into the project bibliography](https://raw.githubusercontent.com/klutchnikoff/citekeep/main/docs/assets/citekeep-demo.gif)

*Project (●) first. Personal library (○) next. zbMATH and CrossRef only when
needed.*

## What it is not

Not a Zotero replacement, a PDF manager, a note-taking system, or a hosted
collaboration platform. citekeep manages the flow of bibliographic records and
leaves the rest to tools that already do it well: Emacs and Citar for reading
notes and PDF links, git and an ordinary `.bib` for collaboration.

## Install

```bash
uv tool install citekeep
citekeep init --library ~/bibliography/master.bib
```

No runtime dependencies — everything is standard library. Requires Python 3.11.

If you already have a library, do not initialise a second one: point citekeep
at the existing file instead.

## Documentation

**[citekeep.readthedocs.io](https://citekeep.readthedocs.io/)** — a tutorial
for the first project, guides for the day-to-day, the command and API
reference, and the reasoning behind the design.

## Licence

MIT.
