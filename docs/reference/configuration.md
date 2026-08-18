# Configuration

## The library path

Resolved in this order, first match winning:

1. `--library PATH`
2. `$CITEKEEP_LIBRARY`
3. `library` in `~/.config/citekeep/config.toml`

```toml
library = "~/bibliography/master.bib"
```

`citekeep where` prints what was resolved.

## Environment

| Variable | Effect |
|---|---|
| `CITEKEEP_LIBRARY` | the library path |
| `CITEKEEP_MAILTO` | your address, sent to CrossRef to reach its faster pool |
| `CITEKEEP_NETWORK_TESTS` | set to run the test suite's live API tests |

## citekeep's own BibTeX fields

citekeep writes exactly one field of its own.

### `ckmasterkey`

```bibtex
  ckmasterkey = {smith_adaptive_2023},
```

Present in a project entry when its local citation key differs from the
canonical key in your library. It stays local: it is never donated to the
library, and it is removed only by an explicit key migration.

**Tools that drop unknown BibTeX fields will delete it.** Configure
formatters and export scripts to preserve it — see [Working with
co-authors](../guides/coauthors.md).

## What is preserved

Unrelated text survives byte for byte: comments, `@string`, `@preamble`,
brace-protected capitalisation, and your hand formatting. New library records
are appended rather than inserted, and sorting is a separate explicit
operation.

## Emacs variables

| Variable | Effect |
|---|---|
| `citekeep-executable` | path to the `citekeep` command |
| `citekeep-bib-file-function` | returns the project `.bib` for the current buffer |
| `citekeep-cite-command` | the macro to insert, e.g. `"citep"` |
| `citekeep-search-count` | how many online results to request |
| `citekeep-insert-citation-function` | set to `#'citekeep-citar-insert-citation` to add keys to an existing `\cite` |

`citekeep.el` declares a schema version and refuses to run against a command
that speaks a different one, rather than misreading its output. If you see
that error, the elisp and the Python come from different installations.
