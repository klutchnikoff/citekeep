# citekeep

**Clean a reference once. Reuse it in every LaTeX project.**

You write several papers at once, with different co-authors. Each has its own
`.bib`. The same reference gets typed again in each of them, a little
differently every time, and the one you cleaned up two years ago sits in a
folder you have since archived.

citekeep gives you one canonical library — a plain `.bib` file you own — and
materialises each project's bibliography from it. It searches the project
first, then your library, then zbMATH, with CrossRef as a fallback.

![citekeep searches the project, the personal library and zbMATH, then writes
the selected record into the project bibliography](assets/citekeep-demo.gif)

*Project (●) first. Personal library (○) next. zbMATH and CrossRef only when
needed.*

## Where you will actually use it

The command line is the engine, a diagnostic surface, and the home of rare
maintenance operations. **The daily loop belongs in your text editor**, which
wraps the command line and presents it as one integrated gesture: you ask for
a reference, and the right record is found, materialised if needed, and cited
under the key valid in the document you are writing — without leaving the
buffer.

The editor integration shipped today is for Emacs; see
[Citing while you write](guides/citing.md). Any editor can do the same through
the [Python API](reference/api.md) or the JSON protocol.

The [tutorial](tutorial/first-project.md) uses the command line, because it is
reproducible for everyone and shows what the editor is doing on your behalf.

## Three things that follow from the design

- **Your co-authors need nothing.** The project keeps an ordinary,
  self-contained `.bib`, and their citation keys are never rewritten. When a
  local key differs from the canonical one, the relationship is recorded in
  the entry itself — see [Working with co-authors](guides/coauthors.md).
- **It works offline.** A reference met once stays searchable on a train, and
  metadata corrected once is never repaired a second time.
- **It refuses rather than guesses.** When the evidence does not settle
  whether two records are one work, citekeep says so and writes nothing — see
  [Deciding what counts as one work](explanation/identity.md).

## Where to go next

| If you want to | Read |
|---|---|
| install it and synchronise a first project | [Install](install.md), then the [tutorial](tutorial/first-project.md) |
| bring years of scattered `.bib` files together | [Starting from scattered files](tutorial/scattered-files.md) |
| cite while writing, in Emacs | [Citing while you write](guides/citing.md) |
| settle a conflict citekeep reported | [Resolving conflicts](guides/conflicts.md) |
| look up a command or an option | [Commands](reference/cli.md) |
| understand why it is built this way | [Why keep a master](explanation/why-a-master.md) |
