# Occasional maintenance

Two operations are deliberately command-line only, and deliberately not part
of the writing loop: they change many records at once, and they deserve your
full attention rather than a keystroke in passing.

## Merging duplicates

Duplicates accumulate when records enter from different projects under
different keys with nothing to link them. Find them:

```bash
citekeep duplicates > duplicate-review.txt
```

The file lists candidate groups with every decision set to `hold`. Nothing
happens until you replace each `hold` with one `keep` and the corresponding
`drop` lines. Holding is the default precisely so that an unreviewed file is
inert.

```bash
citekeep dedupe --resolve duplicate-review.txt --apply
```

Two safeguards are worth knowing:

- **The surviving key never changes.** A merge cannot break a `\cite` in a
  document you have already written.
- **A merge with no title or identifier evidence needs a second
  confirmation** — `--accept-suspect SURVIVOR:DONOR`. If citekeep cannot see
  why two records are the same work, your say-so alone is not enough to make
  it silent about it.

`duplicates` also accepts a file argument, if you want to inspect a project
`.bib` rather than the library.

## Migrating citation keys

Renaming existing keys in bulk is an exceptional repair or initial-import
operation, not routine synchronisation.

```bash
citekeep migrate-keys --json     # inspect the old → new mapping
citekeep migrate-keys --apply    # then, explicitly
```

Read the mapping before applying it. The keys it changes may be cited in
documents and in `ckmasterkey` links outside the file being migrated;
citekeep reports the full mapping and does **not** pretend those external
references are safe to rewrite implicitly.

!!! warning "This is not a request to rewrite finished projects"

    A normalised library and an old paper citing old keys coexist perfectly
    well: `sync` pairs a local record to its canonical one by content — DOI,
    arXiv identifier, normalised key, author and title — and materialises it
    under the *local* key. Old documents keep resolving without a single
    `.tex` being touched.

## Sorting the library

Sorting is an explicit formatting operation, never a side effect of a sync.
New records are appended, so that a sync's diff shows what a sync did and
nothing else.
