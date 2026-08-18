# Python API

The supported entry point is intentionally small.

```python
from citekeep import Citekeep

app = Citekeep.open("~/bibliography/master.bib")
results = app.search("adaptive estimation", project_bib="refs.bib")
plan = app.plan_project(".")
app.apply(plan)
```

Parsing, fingerprint indexes and lossless text patches are implementation
modules rather than a compatibility promise. What follows is.

::: citekeep.app.Citekeep

## The editor protocol

The `citekeep editor …` command namespace is an implementation protocol for
editor extensions, not a second everyday CLI. It carries the small stdin/JSON
operations needed to materialise, add or refresh one record *after* an
interactive choice has been made — the choosing itself belongs to the editor.

Its JSON carries a `schema_version`. An extension should refuse to run against
a version it does not know, rather than misread the output; `citekeep.el` does
exactly that.

## Building an extension for another editor

There is no VS Code or Neovim extension today, and the API above is what one
would be built on. The shape that works, as learned from the Emacs one:

1. call `search` with what the user typed, and show project hits before
   library hits;
2. offer an explicit online action rather than searching the network
   implicitly;
3. call `plan_materialize` when a library record is chosen, and insert the key
   the plan reports — not the library's key, which may differ from the
   project's;
4. never write while the user has unsaved changes in the buffer you are about
   to touch.
