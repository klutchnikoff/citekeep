"""Checking one local record against every configured online source."""

from __future__ import annotations

from . import bib, duplicates
from .model import (
    FieldEvidence,
    RefreshPlan,
    SourceCandidate,
    VerificationReport,
)
from .sources import DEFAULT, NoResult, SourceError, base


def _identity(local, fetched):
    """Return (trusted, reason) for a proposed replacement."""
    if local.doi and fetched.doi:
        if base.same_doi(local.doi, fetched.doi):
            if local.arxiv and fetched.arxiv and local.arxiv != fetched.arxiv:
                return False, "different arXiv identifiers"
            return True, "shared DOI"
        return False, "different DOIs"
    if local.arxiv and fetched.arxiv:
        if local.arxiv == fetched.arxiv:
            return True, "shared arXiv identifier"
        return False, "different arXiv identifiers"
    reason = duplicates.coherence([local, fetched])
    return reason is None, reason or "matching title and author"


def _values(record):
    values = {}
    for name, meaning, value in bib.donatable(record.body):
        values[meaning] = (name, value)
    return values


def report(local, fetched):
    """Build a field-by-field report from ``[(source, Record), ...]``."""
    candidates = []
    for source, record in fetched:
        trusted, reason = _identity(local, record)
        candidates.append(SourceCandidate(source, record, trusted, reason))

    local_values = _values(local)
    meanings = set(local_values)
    source_values = []
    for candidate in candidates:
        values = _values(candidate.record)
        source_values.append((candidate.source, values))
        meanings.update(values)

    evidence = []
    for meaning in sorted(meanings):
        local_value = local_values.get(meaning, (meaning, ""))[1]
        values = tuple(
            (source, fields[meaning][1])
            for source, fields in source_values
            if meaning in fields
        )
        if values and (
            any(value != local_value for _source, value in values) or not local_value
        ):
            evidence.append(FieldEvidence(meaning, local_value, values))
    return VerificationReport(local, tuple(candidates), tuple(evidence))


def fetch_all(local, source_modules=DEFAULT):
    """Ask every source about LOCAL and return a verification report.

    A service failure does not hide evidence from the other services.  If all
    services fail at transport level, their combined error is raised.
    """
    fetched, failures = [], []
    for module in source_modules:
        query = module.query_for_entry(local.body)
        if not query:
            continue
        try:
            entries = module.fetch(query, 1)
        except NoResult:
            continue
        except SourceError as error:
            failures.append(str(error))
            continue
        if entries:
            (record,) = duplicates.records(entries[0], module.NAME)
            fetched.append((module.NAME, record))
    if not fetched and failures:
        raise SourceError("; ".join(failures))
    return report(local, fetched)


def _source_fields(record):
    return {
        meaning: (name, value) for name, meaning, value in bib.donatable(record.body)
    }


def _preserved_fields(local):
    out = []
    for name, _raw in bib.parse_fields(local.body, tolerant=True) or []:
        lowered = name.lower()
        if lowered not in bib.IGNORED_FIELDS:
            continue
        value = bib.get_field(local.body, name).strip()
        if value:
            out.append((lowered, value))
    return out


def plan_refresh(local, candidate, mode="complete", fields=None):
    """Plan refreshing LOCAL from one trusted SourceCandidate.

    MODE is ``complete``, ``selected`` or ``replace``. The local citation key
    and all project-only metadata are preserved in every mode.
    """
    if not candidate.trusted_identity:
        raise ValueError(f"source record is uncertain: {candidate.reason}")
    if mode not in {"complete", "selected", "replace"}:
        raise ValueError(f"unknown refresh mode: {mode}")

    source = candidate.record
    source_fields = _source_fields(source)
    changed = []

    if mode == "complete":
        raw = bib.merge_into(local.raw, [source.body])
        before = {
            bib.canonical(name): bib.get_field(local.body, name).strip()
            for name, _value in (bib.parse_fields(local.body, tolerant=True) or [])
        }
        changed = [meaning for meaning in source_fields if not before.get(meaning)]
    elif mode == "selected":
        wanted = set(fields or ())
        unknown = wanted - set(source_fields)
        if unknown:
            raise ValueError("source has no field(s): " + ", ".join(sorted(unknown)))
        raw = local.raw
        local_names = {
            bib.canonical(name): name.lower()
            for name, _value in (bib.parse_fields(local.body, tolerant=True) or [])
        }
        additions = []
        for meaning in sorted(wanted):
            source_name, value = source_fields[meaning]
            if meaning in local_names:
                raw = bib.replace_field_value(raw, local_names[meaning], value)
            else:
                additions.append((source_name, value))
            changed.append(meaning)
        if additions:
            raw = bib.append_fields(raw, additions)
    else:
        raw = bib.ENTRY_HEAD.sub(f"@{source.type}{{{local.key},", source.raw, count=1)
        present = {
            name.lower()
            for name, _value in (
                bib.parse_fields(next(bib.iter_entries(raw))[3], tolerant=True) or []
            )
        }
        preserved = [
            (name, value)
            for name, value in _preserved_fields(local)
            if name not in present
        ]
        if preserved:
            raw = bib.append_fields(raw, preserved)
        changed = sorted(source_fields)

    return RefreshPlan(raw, local.key, candidate.source, mode, tuple(changed))


def as_dict(report_):
    return {
        "local": {
            "key": report_.local.key,
            "title": report_.local.title,
            "year": report_.local.year,
            "doi": report_.local.doi,
            "master_key": report_.local.master_key or None,
        },
        "candidates": [
            {
                "source": candidate.source,
                "trusted_identity": candidate.trusted_identity,
                "reason": candidate.reason,
                "record": {
                    "key": candidate.record.key,
                    "title": candidate.record.title,
                    "year": candidate.record.year,
                    "doi": candidate.record.doi,
                    "entry": candidate.record.raw,
                },
            }
            for candidate in report_.candidates
        ],
        "fields": [
            {
                "name": field.name,
                "local": field.local,
                "sources": [
                    {"source": source, "value": value}
                    for source, value in field.sources
                ],
                "agrees": field.agrees,
            }
            for field in report_.fields
        ],
    }
