"""Stable domain objects shared by the library, projects and front ends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from . import bib

CKMASTERKEY = "ckmasterkey"
CITEKEEP_FIELDS = frozenset({CKMASTERKEY})


class Record(NamedTuple):
    """One BibTeX entry together with the file or service it came from."""

    type: str
    key: str
    raw: str
    body: str
    origin: str

    @property
    def title(self):
        return " ".join(bib.get_field(self.body, "title").split())

    @property
    def year(self):
        return bib.year_of(self.body)

    @property
    def journal(self):
        return " ".join(bib.journal_of(self.body).split())

    @property
    def doi(self):
        return bib.get_field(self.body, "doi").strip().lower()

    @property
    def arxiv(self):
        # Imported lazily: duplicates owns identifier extraction, while the
        # general Record type must remain usable by that module.
        from .duplicates import arxiv_id

        return arxiv_id(self.body)

    @property
    def names(self):
        for field in ("author", "editor"):
            value = bib.get_field(self.body, field)
            if value.strip():
                return [n.strip() for n in value.split(" and ") if n.strip()]
        return []

    @property
    def signature(self):
        return bib.title_signature(self.title)

    @property
    def target(self):
        return bib.citation_key(self.names, self.year, self.title)

    @property
    def master_key(self):
        """Canonical key named by a materialised project entry, if any."""
        return bib.get_field(self.body, CKMASTERKEY).strip()


@dataclass(frozen=True)
class SearchHit:
    """One work offered to an editor completion interface."""

    origin: str  # local or master
    citation_key: str  # the key valid in the current document
    master_key: str | None
    record: Record
    score: int


@dataclass(frozen=True)
class SearchResults:
    local: tuple[SearchHit, ...]
    master: tuple[SearchHit, ...]


@dataclass(frozen=True)
class MaterializePlan:
    """A project-file change required before inserting a citation."""

    text: str
    citation_key: str
    action: str
    master_key: str


@dataclass(frozen=True)
class FieldConflict:
    """One bibliographic value on which a project view and master differ."""

    name: str
    master: str
    local: str


@dataclass(frozen=True)
class SyncConflict:
    local_key: str
    reason: str
    master_keys: tuple[str, ...] = ()
    fields: tuple[FieldConflict, ...] = ()
    incoming: Record | None = None
    existing: tuple[Record, ...] = ()
    answers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectPlan:
    """Future contents of the master and one materialised project view."""

    master_text: str
    local_text: str
    master_additions: tuple[str, ...]
    master_enrichments: tuple[str, ...]
    local_additions: tuple[str, ...]
    local_updates: tuple[str, ...]
    aliases_added: tuple[tuple[str, str], ...]
    unknown: tuple[tuple[str, tuple[str, ...]], ...]
    unused: tuple[str, ...]
    conflicts: tuple[SyncConflict, ...]
    master_corrections: tuple[tuple[str, str], ...] = ()
    local_skipped: tuple[str, ...] = ()
    master_file: str = ""
    local_file: str = ""
    master_digest: str = ""
    local_digest: str | None = None
    local_existed: bool = False

    @property
    def blocked(self):
        return bool(self.conflicts)

    @property
    def changed(self):
        return bool(
            self.master_additions
            or self.master_enrichments
            or self.master_corrections
            or self.local_additions
            or self.local_updates
        )


@dataclass(frozen=True)
class SourceCandidate:
    source: str
    record: Record
    trusted_identity: bool
    reason: str = ""


@dataclass(frozen=True)
class FieldEvidence:
    name: str
    local: str
    sources: tuple[tuple[str, str], ...]

    @property
    def agrees(self):
        values = {
            value.strip().lower() for _source, value in self.sources if value.strip()
        }
        return len(values) <= 1


@dataclass(frozen=True)
class VerificationReport:
    local: Record
    candidates: tuple[SourceCandidate, ...]
    fields: tuple[FieldEvidence, ...]


@dataclass(frozen=True)
class RefreshPlan:
    text: str
    key: str
    source: str
    mode: str
    fields: tuple[str, ...]
