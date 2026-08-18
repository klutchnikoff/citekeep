"""The small public application API used by CLIs and editor extensions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from . import bib, catalog, duplicates, project, sources, storage
from . import sync as synchronization
from . import verify as verification
from .model import (
    MaterializePlan,
    ProjectPlan,
    Record,
    RefreshPlan,
    SearchResults,
    SourceCandidate,
    VerificationReport,
)


@dataclass(frozen=True)
class Config:
    library: Path

    def __init__(self, library: str | Path) -> None:
        object.__setattr__(self, "library", Path(library).expanduser())


class Citekeep:
    """Configured access to one canonical BibTeX library."""

    def __init__(self, config: Config | str | Path) -> None:
        self.config = config if isinstance(config, Config) else Config(config)

    @classmethod
    def open(cls, library: str | Path) -> Citekeep:
        """Open the canonical library at `library`, expanding `~`.

        Nothing is read here. Every method reads the file afresh, so an edit
        made in a text editor between two calls is seen.
        """
        return cls(library)

    def master_records(self) -> list[Record]:
        """The records the library holds, in the order they appear in it."""
        text = bib.read_text(self.config.library)
        return duplicates.records(text, self.config.library.name)

    def search(
        self, query: str, project_bib: str | Path | None = None
    ) -> SearchResults:
        """Search the project and the library, without touching the network.

        Args:
            query: words matched against title, authors, journal, citation
                key, DOI and arXiv identifier. Every word must appear.
            project_bib: a project bibliography to search as well.

        Returns:
            Project hits first, since their keys are the ones valid in that
            document; library hits omit works the project already holds, so
            that nothing is offered twice.
        """
        local = []
        if project_bib and Path(project_bib).is_file():
            path = Path(project_bib)
            local = duplicates.records(bib.read_text(path), path.name)
        return catalog.search(self.master_records(), local, query)

    def search_online(
        self,
        query: str,
        limit: int = 10,
        source_modules: tuple = sources.DEFAULT,
    ) -> tuple[str, tuple[Record, ...]]:
        """Search the online sources, zbMATH first.

        Args:
            query: a DOI, an arXiv identifier, or free text.
            limit: how many results to ask the source for.
            source_modules: the sources to try, in order.

        Returns:
            The source that answered, and the records it returned. A source
            with nothing to say is passed over rather than reported as a
            failure.
        """
        source, entries = sources.lookup(query, count=limit, sources=source_modules)
        return source, tuple(
            record for text in entries for record in duplicates.records(text, source)
        )

    def verify(
        self,
        record: Record,
        source_modules: tuple = sources.DEFAULT,
    ) -> VerificationReport:
        """Ask every source about `record`, and report what they answer.

        Nothing is written: the caller arbitrates. One service failing does
        not hide the evidence of the others.
        """
        return verification.fetch_all(record, source_modules)

    def plan_refresh(
        self,
        record: Record,
        candidate: SourceCandidate,
        mode: str = "complete",
        fields: list[str] | None = None,
    ) -> RefreshPlan:
        """Plan an update of `record` from one verified candidate.

        Args:
            record: the record as currently held.
            candidate: a candidate returned by `verify`.
            mode: `complete` fills only the empty fields, `selected` takes
                the fields named in `fields`, `replace` takes the
                bibliographic metadata whole.
            fields: the fields to take, when `mode` is `selected`.

        Raises:
            ValueError: the candidate identity is not trusted, or the mode
                is unknown.

        The local citation key and every project-only field survive all three
        modes; the plan is not applied here.
        """
        return verification.plan_refresh(record, candidate, mode, fields)

    def plan_materialize(
        self, master_key: str, project_bib: str | Path
    ) -> MaterializePlan:
        """Plan copying one library record into a project bibliography.

        Raises:
            KeyError: no record in the library carries `master_key`.
        """
        records = {record.key: record for record in self.master_records()}
        if master_key not in records:
            raise KeyError(master_key)
        path = Path(project_bib).expanduser()
        local = bib.read_text(path) if path.is_file() else ""
        return catalog.materialize(local, records[master_key])

    def plan_project(
        self,
        root: str | Path,
        project_bib: str | Path | None = None,
        field_resolutions: dict | None = None,
        identity_resolutions: dict | None = None,
    ) -> ProjectPlan:
        """Plan one complete synchronisation of the project under `root`.

        Reads the `\\cite` commands in the project's TeX files and pairs them
        with the library both ways: records the document needs are copied
        down, records only the project holds are offered up.

        Args:
            root: the project directory.
            project_bib: its bibliography, when the document declares none
                or declares several.
            field_resolutions: decisions on fields where a reviewed local
                value contradicts the library.
            identity_resolutions: decisions on records whose identity the
                evidence does not settle.

        Raises:
            ValueError: no bibliography is declared, several are, or the one
                given is the library itself.

        The plan records a digest of both files, so that `apply` can refuse
        to act on a file that has changed since. Nothing is written here.
        """
        cited, declared = project.scan(root)
        if project_bib:
            local_path = Path(project_bib).expanduser()
        elif len(declared) == 1:
            local_path = declared[0]
        elif not declared:
            raise ValueError("no project bibliography declared")
        else:
            raise ValueError("several project bibliographies declared")

        master_path = self.config.library
        if master_path.resolve() == local_path.resolve():
            raise ValueError("the project bibliography cannot be the master library")
        master_text = bib.read_text(master_path)
        existed = local_path.is_file()
        local_text = bib.read_text(local_path) if existed else ""
        plan = synchronization.plan(
            master_text,
            local_text,
            cited,
            field_resolutions=field_resolutions,
            identity_resolutions=identity_resolutions,
            master_origin=master_path.name,
            local_origin=local_path.name,
        )
        return replace(
            plan,
            master_file=str(master_path),
            local_file=str(local_path),
            master_digest=storage.digest(master_path),
            local_digest=storage.digest(local_path) if existed else None,
            local_existed=existed,
        )

    def apply(self, plan: ProjectPlan) -> ProjectPlan:
        """Write a plan to disk, atomically.

        Raises:
            ValueError: the plan carries unresolved conflicts, or was not
                built against files.
            storage.ConcurrentModification: the library or the project
                bibliography changed since the plan was made.

        Returns:
            The plan that was applied.
        """
        if plan.blocked:
            raise ValueError("cannot apply a project plan with conflicts")
        if not plan.master_file or not plan.local_file:
            raise ValueError("plan has no filesystem preconditions")
        master_path, local_path = Path(plan.master_file), Path(plan.local_file)
        if storage.digest(master_path) != plan.master_digest:
            raise storage.ConcurrentModification(
                f"{master_path}: changed since the operation was planned"
            )
        if plan.local_existed:
            if (
                not local_path.is_file()
                or storage.digest(local_path) != plan.local_digest
            ):
                raise storage.ConcurrentModification(
                    f"{local_path}: changed since the operation was planned"
                )
        elif local_path.exists():
            raise storage.ConcurrentModification(
                f"{local_path}: created since the operation was planned"
            )

        current_master = bib.read_text(master_path)
        if plan.master_text != current_master:
            storage.write_atomically(master_path, plan.master_text, plan.master_digest)
        current_local = bib.read_text(local_path) if local_path.is_file() else ""
        if plan.local_text != current_local:
            storage.write_atomically(local_path, plan.local_text, plan.local_digest)
        return plan
