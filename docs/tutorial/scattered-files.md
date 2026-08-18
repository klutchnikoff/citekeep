# Starting from scattered files

If you have no library yet but years of project `.bib` files, the library is
built by synchronising those projects one at a time.

```bash
citekeep init --library ~/bibliography/master.bib
export CITEKEEP_LIBRARY=~/bibliography/master.bib
```

**Oldest first.** Order matters: later corrections should meet earlier
entries, not the other way round. A record you fixed in 2023 should be the one
that survives its 2016 version.

```bash
citekeep sync --project OLD_PROJECT --bib OLD_PROJECT/refs.bib
```

Read the plan and its conflicts, then:

```bash
citekeep sync --project OLD_PROJECT --bib OLD_PROJECT/refs.bib --apply
```

`--bib` is needed only when the document declares no bibliography, or declares
several.

## Expect it to stop

Synchronising a decade of files surfaces every disagreement those files ever
contained, and citekeep refuses rather than guessing. This is not a
malfunction; it is the point. The first command is already a dry plan — add
`--json` to collect the conflicts in a structured form, settle them, and run
again.

[Resolving conflicts](../guides/conflicts.md) covers the two kinds you will
meet and the exact syntax for answering them.

## Some of that work is yours

Whether two 2014 papers by the same author are one work, whether a supplement
belongs with its article, which of two contradictory DOIs is right — no amount
of evidence decides these. You do.

What citekeep can do is narrow the pile to the cases that genuinely need you,
and then get out of the way. On a large import that is still a real afternoon
of work, but it is an afternoon spent on real questions rather than on
re-typing references.

## When the import is done

Run [`citekeep duplicates`](../guides/maintenance.md) once over the finished
library. Records that entered from different projects under different keys,
with no DOI to link them, will surface there rather than during a sync.
