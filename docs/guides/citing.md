# Citing while you write

This is the loop citekeep exists for. Everything the
[tutorial](../tutorial/first-project.md) did by hand happens here as one
gesture, without leaving the buffer.

## `citekeep-insert`

`M-x citekeep-insert` opens a single completion session that searches fuzzily
across the project and your library at once. Type words; the list narrows.

- `●` marks a record already materialised in the project.
- `○` marks one available from your library.
- `🌐` is the action that sends what you typed to an online search instead —
  bound to ++ctrl+return++.

Project records come first, because their keys are the ones valid in the
document you are writing.

Choosing a `●` record inserts its local key. Choosing a `○` record first
copies it into the project, then inserts the key. Choosing the online action
compares the fetched record against both files before anything is written.

You never have to know which of the three cases you are in — that is the point
of the single list.

## `citekeep-fetch`

Goes online directly, when you know the reference is not yours yet. Takes a
DOI, an arXiv identifier, or free words. If the chosen result resembles an
existing record without being identifiable safely, Emacs asks whether it is
the same work, a distinct work, or should be skipped. A distinct work receives
the next free `a`, `b`, … suffix from citekeep; the editor does not invent a
key itself.

## `citekeep-verify-entry`

With point in a BibTeX entry, checks it against zbMATH and CrossRef and offers
to:

- **complete** — fill only the fields you are missing (the safe default);
- **accept selected fields** — take specific corrections, one by one;
- **replace** — take the bibliographic metadata whole.

All three keep your citation key, `ckmasterkey`, and any project-only fields
you have configured. A fetched value that contradicts your library is treated
as a proposed correction *to the library*, and asks for review rather than
being applied quietly.

## `citekeep-sync`

Runs the full project synchronisation and presents field arbitration in the
editor when a verified local correction meets a different library value.
Cancelling leaves both files untouched.

Identity questions are asked in one of two ways, depending on how many there
are. **A single question** is asked outright, in the same words
`citekeep-fetch` uses. **Several** open `*citekeep resolve*`, where answers
can be compared and revised before any of them is applied:

| key | |
|---|---|
| `s` | same work — the library entry is completed from this one |
| `d` | distinct work — it enters under a key of its own |
| `k` | skip — an answer too: left out of this run, asked again next time |
| `u` | unset — takes the answer back; the question is unanswered again |
| `n` / `p` | go to the next / previous question |
| `g` | redraw the list |
| ++ctrl+c++ ++ctrl+c++ | apply every answer, then synchronise |
| `q` | quit; nothing is written |

Point picks the question, and applying refuses while any question is still
unanswered — which is what separates `k` from `u`.

## Bindings

citekeep installs no global bindings, on purpose: it does not know your
keymap. A Doom or Evil setup can do as it likes, for example:

```elisp
(map! :leader
      (:prefix ("n b" . "bibliography")
       :desc "Insert citation" "i" #'citekeep-insert
       :desc "Search online"   "f" #'citekeep-fetch
       :desc "Verify entry"    "v" #'citekeep-verify-entry
       :desc "Sync project"    "s" #'citekeep-sync
       :desc "Sync status"     "S" #'citekeep-status
       :desc "Open master"     "o" #'citekeep-open-library))
```

## Inserting into an existing `\cite`

By default citekeep inserts a complete citation macro. To let Citar and AUCTeX
add the key to a citation already under point instead:

```elisp
(setq citekeep-insert-citation-function #'citekeep-citar-insert-citation)
```

The adapter recognises both Emacs's built-in `latex-mode` and AUCTeX's
`LaTeX-mode`, Doom configurations included.

## Citar, PDFs and reading notes

citekeep does not organise PDFs or notes, and does not intend to. Citar can
read your library directly as its long-lived index, follow its PDF links and
connect records to notes; citekeep preserves the bibliographic and
project-only metadata while remaining responsible only for how records
circulate.

## Other editors

There is no VS Code or Neovim extension today. The [Python
API](../reference/api.md) is the supported way to build one, and the
`citekeep editor` command namespace carries the small stdin/JSON operations an
extension needs once the user has made a choice.
