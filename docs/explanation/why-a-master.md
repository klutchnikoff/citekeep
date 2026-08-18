# Why keep a master

The canonical library is not an implementation detail. It answers a different
question from the one a project `.bib` answers.

> The project `.bib` answers **“what does this document need to compile and
> share with its co-authors?”**
> The library answers **“what do I already know?”**

Online sources are the last resort, not a permanent dependency.

## Offline memory

References you have already met stay searchable on a train, on a plane, and
whenever zbMATH and CrossRef are down or slow. A bibliography that only works
with a connection is a bibliography you cannot rely on when you are actually
writing.

## Personal bibliographic memory

This is the one that compounds. Metadata you cleaned or corrected once is
reused in future work instead of being fetched and repaired again. The page
range you fixed by hand, the accented name you got right, the preprint you
linked to its published version — all of it survives the project it was done
in.

Without a library, every project starts from zero and every correction is
thrown away when the paper is finished.

## A stable editor index

Because it is one long-lived file, the library can be the index other tools
point at. Emacs and Citar use it to navigate references, follow PDF links and
connect records to reading notes — independently of any particular article.
A project `.bib` cannot play that role: it is scoped to one paper and
disappears from view when the paper is done.

This distinction remains useful in editors whose PDF and notes integration is
less complete than Citar's. The library still gives you offline search and
reuse of verified records.

## Why a plain file

The library is a `.bib` you own, in a directory you chose, under whatever
version control you already use. Not a database, not a hidden store, not a
service.

That choice has a cost — citekeep must parse and patch BibTeX carefully, and
[preserve every unrelated byte](invariants.md) — and one decisive benefit: on
the day citekeep stops being useful to you, you still have your bibliography,
in the format every LaTeX tool has read for forty years.
