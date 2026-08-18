# Commands

Every command accepts `--library PATH` to override the configured library, and
`--json` for structured output. Commands used by editor extensions include
provenance and decisions in their JSON.

## `init`

```bash
citekeep init --library ~/bibliography/master.bib
```

Creates an empty library. Does nothing if the file exists.

## `where`

```bash
citekeep where
```

Prints the library path citekeep resolved, and how. The first thing to run
when a command acts on a file you did not expect.

## `emacs-path`

Prints where `citekeep.el` was installed by the wheel.

## `search`

```bash
citekeep search QUERY [--local FILE]
```

Searches offline. Every word of the query must appear in the title, authors,
journal, citation key, DOI or arXiv identifier.

With `--local`, the project `.bib` is searched first and listed first. Library
records for works the project already holds are omitted, so nothing is
offered twice.

## `fetch`

```bash
citekeep fetch QUERY [--count N] [--take KEY --into FILE]
```

Searches the online sources — zbMATH first, CrossRef as a fallback. The query
may be a DOI, an arXiv identifier, or free words.

Each result is reported with what it would mean for your library: already
there, an enrichment, or new under a stated key. `--take KEY --into FILE`
writes the chosen result into a project `.bib`, checking it against both files
first.

## `verify`

```bash
citekeep verify FILE --key KEY [--source zbmath|crossref]
                     [--replace | --field FIELD ...] [--apply]
```

Compares one entry with every source. Without `--apply`, reports only.

With `--apply`, the default is completion: only fields you lack are filled.
`--field` accepts named fields from the selected source; `--replace` takes the
bibliographic metadata whole. All modes keep the local citation key,
`ckmasterkey`, and configured project-only fields.

## `sync`

```bash
citekeep sync [--project DIR] [--bib FILE] [--apply]
              [--resolve FILE] [--resolve-fields FILE]
              [--keep-master LOCAL_KEY:FIELD] [--use-local LOCAL_KEY:FIELD]
```

Plans one complete synchronisation, both directions, and writes it only with
`--apply`.

`--project` takes a directory or a single `.tex`. `--bib` is needed only when
the document declares no bibliography or declares several. The resolution
flags are covered in [Resolving conflicts](../guides/conflicts.md).

Exits non-zero when a cited key is held nowhere.

## `duplicates`

```bash
citekeep duplicates [FILE] > review.txt
```

Writes a review file of candidate groups, every decision set to `hold`.
Defaults to the library.

## `dedupe`

```bash
citekeep dedupe [FILE] --resolve review.txt [--accept-suspect SURVIVOR:DONOR] [--apply]
```

Merges only reviewed `keep`/`drop` pairs. Surviving keys never change. A merge
without title or identifier evidence requires `--accept-suspect`.

## `migrate-keys`

```bash
citekeep migrate-keys [FILE] [--apply]
```

Renames existing keys in bulk and reports the complete mapping. An exceptional
operation — see [Occasional maintenance](../guides/maintenance.md).

## `editor`

An implementation protocol for editor extensions, not a second everyday CLI.
It carries the small stdin/JSON operations needed to materialise, add or
refresh one record after an interactive choice has been made. See the [Python
API](api.md).
