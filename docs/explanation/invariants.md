# Design invariants

This page records the product invariants. They are deliberately more stable
than the current command names: the command line and editor interfaces may
evolve, but they must preserve this model.

It is the contract a contributor works against, and the answer to “why does it
behave like that?” when the other pages only say that it does.

## Authority

- `master.bib` is the bibliographic source of truth.
- A value already present in the master is never silently replaced by a local
  or remotely fetched value.
- A local value for a field absent from the master is an enrichment proposal.
- Contradictory values require an explicit decision.
- A field decision has exactly two meanings: keep the master value and restore
  it locally, or promote the reviewed local value to the master.  Applying a
  decision recomputes the materialised view from the resulting master.

## Project bibliographies

A project `.bib` is a materialised view of the master.  It may temporarily
contain new records or additional fields which have not been accepted into the
master yet.

Citation keys introduced by collaborators are part of the project's public
interface and are not rewritten automatically.  When such a key differs from
the canonical master key, the local entry records the relationship as:

```bibtex
  ckmasterkey = {canonical_master_key},
```

`ckmasterkey` is citekeep metadata.  It stays local, is never donated to the
master, and is removed only by an explicit project-key migration.

Because the alias is embedded in the materialised `.bib`, deleting that file
also deletes the information needed to reconstruct foreign citation keys.  We
accept this trade-off: collaborative project bibliographies are versioned
project files, not disposable build artefacts.

The same caveat applies to BibTeX filters and editor scripts: tools which drop
unknown fields can silently remove `ckmasterkey`.  A project workflow using
citekeep must configure such tools to preserve that field.  Without it, a
later sync can still recover identity from bibliographic evidence, but cannot
reconstruct the alias-to-master relationship with certainty.

## Synchronisation

A project sync is planned as one operation:

1. identify local records and their canonical master records;
2. plan unambiguous additions and enrichments to the master;
3. compute the future master state;
4. materialise cited records back into the project, retaining local keys and
   project-only metadata;
5. refuse the entire plan while any identity or field conflict is unresolved.

Planning is cumulative.  Each accepted change is visible to the records that
follow it, so two incoming proposals can contradict each other rather than
silently winning according to file order.

## Finding and inserting a citation

The editor searches in this order:

1. the project `.bib`;
2. the master, excluding works already represented locally;
3. an explicit action which searches configured online sources.

Choosing a local record inserts its local key.  Choosing a master record first
materialises it in the project.  A fetched record is compared with both local
and master records before anything is written.

## Verifying a local record

From a local BibTeX entry, online sources can be used to:

- fill missing fields (the safe default);
- accept selected field changes;
- replace bibliographic metadata explicitly.

All modes preserve the local citation key, `ckmasterkey`, and configured
project-only metadata.  A fetched value contradicting the master is a proposed
master correction and requires review.

## Storage safety

- Transformations preserve all unrelated bytes, including comments,
  `@string`, `@preamble`, and text between entries.
- Reads distinguish an empty file from an inaccessible or missing file.
- Writes are atomic, preserve file permissions, and check that their input has
  not changed since planning.
- Editor integrations never overwrite unsaved buffers.

## Maintenance outside the writing loop

Duplicate review and bulk citation-key migration are not editor insertion
operations.  They remain explicit CLI maintenance workflows:

- duplicate candidates first produce a hold-first, editable review file;
- only reviewed keep/drop pairs are merged, while survivor keys remain stable;
- a merge lacking title or identifier evidence needs a second confirmation;
- migrating existing keys is a separate operation which reports its complete
  mapping, because references outside the inspected file cannot safely be
  guessed or rewritten.
