# Deciding what counts as one work

Everything citekeep does rests on one question: are these two records the same
work? Get it wrong in one direction and you accumulate silent duplicates; get
it wrong in the other and you destroy a distinct reference by merging it.

So citekeep uses four independent signals, because none is sufficient alone.

## The four signals

**DOI.** Decisive when present — and absent from about a third of a working
bibliography. Old papers, book chapters, technical reports and most preprints
have none.

**arXiv identifier.** The only thing a preprint shares with the paper it
became, once the title has been reworked and the year has moved. Most tools
miss this case entirely and end up holding both.

**Normalised key.** `surname_word_year`, built the same way from every source,
so the same paper fetched twice lands in the same place regardless of who
typed the original entry.

**First author and title.** For everything carrying no identifier at all.

## How they combine

Two records sharing *any* of these are compared. They are treated as one work
only if their titles agree **and** their identifiers do not contradict each
other.

That second condition matters more than it looks. Two records with different
DOIs are not one work, however similar their titles — that is exactly the
shape of a paper and its corrigendum.

## Evidence that separates

The four signals above can only bring records together. On their own, the
weakest resemblance outvotes the strongest contradiction — and the normalised
key is a *derived name*, not bibliographic evidence at all. Two 2020 papers by
one author whose titles both begin "Adaptive" would land on the same key, and
that alone was enough to demand an arbitration at every synchronisation, one
that answering could not settle because the keys were already distinct.

So identifiers are allowed to disagree, in this order:

1. **A shared arXiv identifier settles it: one work.** A preprint and the
   paper it became carry two different DOIs, and nothing else survives the
   retitling.
2. **Otherwise, different DOIs mean different works.** A paper and its
   erratum, an article and its translation, a supplement and what it
   supplements: each registers its own DOI.
3. **Unless everything descriptive agrees too.** One title and one authorship
   under two DOIs is a genuine puzzle — a duplicate registration, a journal
   version and a conference version — and a puzzle belongs to a person.

Titles are compared by the prefix rule, so a recorded subtitle and an omitted
one still agree. Author sets are compared by containment rather than equality:
a source that stops at "et al." holds a subset of the truth, not a
contradiction.

A refutation removes a **link**, not a record. Two entries the evidence
separates can still be drawn into one group by a third that resembles both,
and that group is a real question rather than an artefact.

Silence is not disagreement: a record carrying no DOI refutes nothing.

## The refusal

A record with no title cannot be vouched for by anything. When nothing
identifies a work and nothing describes it, citekeep does not guess: it
reports and writes nothing.

This is not defensive coding. It caught a real case: a search returned a test
record from a registry, with a valid-looking DOI and no title or author at
all. Under a rule that merged on identifier alone, it would have entered a
library as a real reference.

## Why it stops the whole sync

When an identity conflict is unresolved, the entire synchronisation is
refused — including the parts that were fine.

A partly applied sync leaves a state nobody can reason about later: some
records updated, some not, no record of where it stopped. Refusing whole means
the two files are always in a state you could have predicted.

The cost is that a large import stops often. [That is the intended
behaviour](../tutorial/scattered-files.md), and the decisions it asks for are
genuinely yours — no amount of evidence settles whether a supplement belongs
with its article.
