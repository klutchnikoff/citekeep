# Resolving conflicts

A synchronisation refuses as a whole while anything is unresolved. Nothing is
written — not even the parts that were fine. This is deliberate: a partly
applied sync is a state nobody can reason about afterwards.

There are exactly two kinds of conflict.

## Identity: are these one work?

Two records look alike and the evidence does not settle it — a paper and its
erratum, two papers by one author in one year, a preprint retitled before
publication. See [Deciding what counts as one
work](../explanation/identity.md) for what citekeep compares.

Collect them in a review file and answer each one:

```
same LOCAL_KEY [MASTER_KEY]
distinct LOCAL_KEY
skip LOCAL_KEY
```

- **`same`** — one work. The optional master key disambiguates when the local
  record resembles several library records.
- **`distinct`** — two works. The local one enters the library in its own
  right.
- **`skip`** — decide later. The record is left alone this time.

Then:

```bash
citekeep sync --project . --resolve FILE --apply
```

## Fields: which value is right?

The record is agreed, but a reviewed local value contradicts the library. The
plan shows both and stops.

A field decision has exactly two meanings:

```bash
citekeep sync --project . --keep-master Smi23:year --apply
citekeep sync --project . --use-local Smi23:year --apply
```

- **`--keep-master`** — the library was right. Its value is restored in the
  project view.
- **`--use-local`** — the local value is a correction. It is promoted into the
  library, and the project view is recomputed from the result.

Note the asymmetry, which is the whole authority model: a value already in the
library is never silently replaced, but a field the library *lacks* is taken
as an enrichment without asking.

For several decisions at once, `--resolve-fields FILE` reads auditable lines:

```
master Smi23 year
local Smi23 doi
```

## Working through a large batch

Both flags take `--json`, which is the practical way to handle an import:

```bash
citekeep sync --project . --json > conflicts.json
```

Settle them, write the review files, and apply once. Planning is cumulative —
each accepted decision is visible to the records considered after it — so two
incoming proposals can contradict each other openly rather than one silently
winning by file order.
