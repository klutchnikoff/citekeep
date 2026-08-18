# What citekeep is not

citekeep manages the **flow of bibliographic records**, and nothing else. This
page exists so that you can tell quickly whether it is for you.

## It is not

- **a Zotero replacement.** No library UI, no browser connector, no groups.
- **a PDF manager.** It does not download, rename, store or open PDFs.
- **a note-taking system.** It stores no notes and imposes no note format.
- **a graphical application.** A command line and an editor integration.
- **a hosted collaboration platform.** Nothing is uploaded anywhere.
- **a reference formatter.** Your `.bst` or biblatex style does that.

## What plays those roles instead

| For | Use |
|---|---|
| navigation, PDF links, reading notes | Emacs and Citar, reading the library directly |
| collaboration | git and the project's ordinary `.bib` |
| external records | zbMATH and CrossRef, queried on demand |
| the library itself | a plain file under your control |

citekeep sits between them and keeps the records moving correctly. Each of
those tools is better at its job than a bibliography manager that also tried
to do it.

## No project registry

There is no notion of a registered project, no lifecycle, no archive step. A
project is simply a TeX directory and its `.bib`, and citekeep acts on it only
when invoked from there.

When an article is finished, nothing is marked or migrated: you stop
synchronising it. The library supports current and future work without
requiring you to rewrite historical projects.

## Is it for you?

Probably, if you keep a personal `.bib`, write LaTeX with co-authors over git,
and have tried and abandoned a reference manager because it wanted to own your
files.

Probably not, if you want a graphical library with a PDF reader attached, or
if your collaboration happens in Overleaf with a shared bibliography nobody
owns in particular.
