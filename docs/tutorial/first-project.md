# Your first synchronised project

This walks the whole loop once, from the command line: create a library, take
in what a project already holds, fetch a reference from zbMATH, and put it
back into the project.

!!! note "The command line is not where you will live"

    citekeep's daily use happens in a text editor, which wraps these same
    commands and presents them as a single gesture — see
    [Citing while you write](../guides/citing.md). The tutorial uses the
    command line because it is reproducible on any machine, and because
    seeing the plumbing once makes the editor's behaviour obvious.

Assumes citekeep is [installed](../install.md).

## 1. Create the library

```bash
citekeep init --library ~/bibliography/master.bib
export CITEKEEP_LIBRARY=~/bibliography/master.bib
```

```
Created ~/bibliography/master.bib
```

It is an ordinary, nearly empty `.bib`. Nothing is hidden anywhere else: this
file is the whole state.

## 2. Look at a project before touching it

Take any directory with a `.tex` file and its `.bib`. Ask for a plan:

```bash
citekeep sync --project paper
```

```
paper/refs.bib: 1 to master, 0 master completions, 0 master corrections,
0 copied locally, 0 local updates, 0 conflicts, 0 unknown
Plan only: run sync --apply to write it.
```

Read that line as the two directions of one operation. **Up:** one record the
project holds is new to the library. **Down:** nothing needs copying back,
since the project already has what it cites. And `0 conflicts, 0 unknown` —
nothing needs you.

Nothing has been written. `sync` is a plan unless you say otherwise.

## 3. Apply it

```bash
citekeep sync --project paper --apply
```

```
Applied to ~/bibliography/master.bib and paper/refs.bib.
```

The record is now in your library, byte for byte as the project had it —
braces, accents and hand formatting included.

## 4. Fetch something you do not have

```bash
citekeep fetch 10.2307/2118559
```

```
zbmath: 1 result(s) for '10.2307/2118559'
  Wiles              1995  Modular elliptic curves and Fermat's Last Theorem
      wiles_modular_1995  —  not in the library — it would enter as wiles_modular_1995
```

Note what the second line tells you before anything is written: this work is
new, and the key it would take. A DOI, an arXiv identifier or free words all
work as the query.

To write it into the project:

```bash
citekeep fetch 10.2307/2118559 --take wiles_modular_1995 --into paper/refs.bib
```

```
added wiles_modular_1995 in refs.bib
```

## 5. Close the loop

Cite the new key in your `.tex`, then plan again:

```bash
citekeep sync --project paper
```

```
paper/refs.bib: 1 to master, 0 master completions, 0 master corrections,
0 copied locally, 0 local updates, 0 conflicts, 0 unknown
```

The fetched record is in the project but not yet in the library; this sync
offers it up. Apply, and the two are in step.

## 6. Search what you now know

```bash
citekeep search godel --local paper/refs.bib
```

```
Project:
  Gödel   1931  Über formal unentscheidbare Sätze der Principia Mathematic…  [godel_uber_1931]
```

The project is listed first, because its keys are the ones valid in that
document. The library section is empty here for a reason worth knowing: the
same work is in your library, but citekeep omits library records the project
already holds, so nothing is ever offered to you twice.

## What to read next

- [Citing while you write](../guides/citing.md) — the same loop, in Emacs,
  without leaving the buffer.
- [Starting from scattered files](scattered-files.md) — if you have years of
  project `.bib` files and no library yet.
- [Resolving conflicts](../guides/conflicts.md) — for the day `0 conflicts`
  is not `0`.
