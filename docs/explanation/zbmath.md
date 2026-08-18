# Why zbMATH first

citekeep queries zbMATH Open before CrossRef. This is a deliberate bias, not a
neutral ordering.

## What zbMATH has that CrossRef does not

**Human review.** zbMATH records are curated by mathematicians. Titles are
right, author names are disambiguated, and the metadata has been read by
someone.

**MSC classification.** Subject classification you can actually use.

**The arXiv identifier.** zbMATH records the link between a published paper
and its preprint. CrossRef generally does not — and that link is precisely
what lets citekeep recognise a preprint and its published version as one work.

## What happens outside mathematics

The search falls through to CrossRef on its own. A source with nothing to say
is passed over in silence rather than reported as a failure, so querying for a
biology paper simply gets you the CrossRef record without ceremony.

## The honest trade-off

This ordering makes citekeep good **for mathematicians** rather than mediocre
for everyone. If your field is far from mathematics, you will effectively be
using CrossRef with an extra query in front — a small cost in latency, no cost
in correctness.

An assumed position beats a lukewarm neutrality here. A tool that treated all
sources as interchangeable would have to drop the arXiv linking, which is one
of the few things citekeep does that other tools do not.

## CrossRef politeness

Set `CITEKEEP_MAILTO` to your address to reach CrossRef's faster pool. It is
their documented way of identifying considerate clients, and it costs you
nothing.
