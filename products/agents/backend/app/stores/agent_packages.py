"""Agent Packages stores — project sources (§G3) and learnings (§H2).

Backed by 017's ``agent_project_sources`` and ``agent_learnings`` (the
version-bound package tree lives on the definitions store: it is a child of a
version). Same Protocol + Fake + Real + factory shape as the other studio
stores; every write goes through ``app.stores._db_errors`` so a constraint
violation becomes a typed error, never a 500 that a Fake would have hidden.

Everything is org-scoped by ``org_id`` and agent-scoped by ``agent_id``. A
foreign id is :class:`NotFound` (never a "forbidden" that would leak
existence across orgs).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched

__all__ = [
    "LEARNING_REVIEW_STATUSES",
    "LEARNING_ROW_STATUSES",
    "LEARNING_TIPOS",
    "SOURCE_TIPOS",
    "AgentPackageStore",
    "FakeAgentPackageStore",
    "LearningInput",
    "LearningRecord",
    "ProjectSourceRecord",
    "SupabaseAgentPackageStore",
    "get_agent_package_store",
    "learning_row_sha",
]

_SCHEMA = "agents"

#: 017 CHECK sets (kept in step with the migration; the build tool's
#: ``LEARNING_TIPOS`` / ``LEARNING_STATUSES`` are the same values).
SOURCE_TIPOS = ("doc", "codigo", "quadro")
LEARNING_TIPOS = ("pitfall", "armadilha", "practice", "pratica", "prática", "decision", "decisao", "decisão")
LEARNING_ROW_STATUSES = ("new", "novo", "absorbed", "absorvido", "promoted", "promovido")
LEARNING_REVIEW_STATUSES = ("novo", "aceito", "descartado", "promovido")


def learning_row_sha(data: str, texto: str) -> str:
    """§H1 row identity — sha256 over (date, learning text), whitespace-
    normalised. The SAME formula as ``agent_package_build.row_sha`` (the
    consumer computes it too, so both sides agree on what "the same row" is)."""

    def norm(s: str) -> str:
        return " ".join(s.split())

    return hashlib.sha256(f"{norm(data)}\n{norm(texto)}".encode("utf-8")).hexdigest()


# ── records ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectSourceRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    project_slug: str
    path: str
    sha256: str
    tipo: str
    document_id: UUID | None
    synced_at: datetime


@dataclass(frozen=True)
class LearningInput:
    data: str
    tipo: str
    texto: str
    evidencia: str = ""
    row_status: str = "novo"


@dataclass(frozen=True)
class LearningRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    project_slug: str
    row_sha: str
    data: str
    tipo: str
    texto: str
    evidencia: str
    row_status: str
    status: str
    review_note: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime


def _validate_learning(item: LearningInput) -> None:
    if item.tipo not in LEARNING_TIPOS:
        raise ValueError(f"tipo must be one of {LEARNING_TIPOS}; got {item.tipo!r}")
    if item.row_status not in LEARNING_ROW_STATUSES:
        raise ValueError(f"status must be one of {LEARNING_ROW_STATUSES}; got {item.row_status!r}")
    if not (1 <= len(item.data) <= 40):
        raise ValueError("data must be 1..40 characters")
    if not (1 <= len(item.texto) <= 8000):
        raise ValueError("texto must be 1..8000 characters")
    if len(item.evidencia) > 4000:
        raise ValueError("evidencia exceeds 4000 characters")


def _validate_review(status: str, note: str | None) -> None:
    if status not in LEARNING_REVIEW_STATUSES:
        raise ValueError(f"status must be one of {LEARNING_REVIEW_STATUSES}; got {status!r}")
    if note is not None and len(note) > 2000:
        raise ValueError("review_note exceeds 2000 characters")


# ── Protocol ────────────────────────────────────────────────────────────────


class AgentPackageStore(Protocol):
    # project sources (§G3)
    def list_sources(self, org_id: UUID, agent_id: UUID, project_slug: str | None = None) -> list[ProjectSourceRecord]:
        """All sources of the agent (one project when ``project_slug``), ordered by path."""
        ...
    def upsert_source(
        self, org_id: UUID, agent_id: UUID, project_slug: str, *, path: str, sha256: str, tipo: str,
        document_id: UUID | None,
    ) -> ProjectSourceRecord:
        """Upsert by ``(agent, project, path)``; bumps ``synced_at``."""
        ...
    def delete_sources(self, org_id: UUID, agent_id: UUID, project_slug: str, paths: list[str]) -> int:
        """Remove the ledger rows for ``paths``; returns how many were removed."""
        ...

    # learnings (§H2)
    def insert_learnings(
        self, org_id: UUID, agent_id: UUID, project_slug: str, items: list[LearningInput]
    ) -> tuple[list[LearningRecord], int]:
        """Insert the rows whose ``row_sha`` is new for this agent; returns
        ``(inserted, duplicates)`` — a re-push inserts nothing."""
        ...
    def list_learnings(
        self, org_id: UUID, agent_id: UUID, *, project_slug: str | None = None, status: str | None = None,
    ) -> list[LearningRecord]:
        """Newest first."""
        ...
    def get_learning(self, org_id: UUID, agent_id: UUID, learning_id: UUID) -> LearningRecord:
        """Raises :class:`NotFound` for an unknown / foreign id."""
        ...
    def review_learning(
        self, org_id: UUID, agent_id: UUID, learning_id: UUID, *, status: str, note: str | None, reviewer: UUID | None,
    ) -> LearningRecord: ...


# ── Fake ────────────────────────────────────────────────────────────────────


class FakeAgentPackageStore:
    """In-memory :class:`AgentPackageStore` emulating 017: the
    ``(agent, project, path)`` and ``(agent, row_sha)`` uniques, the CHECK
    sets, and the write-once content of a learning."""

    def __init__(self) -> None:
        self._sources: dict[tuple[UUID, str, str], ProjectSourceRecord] = {}
        self._learnings: dict[UUID, LearningRecord] = {}

    # sources
    def list_sources(self, org_id: UUID, agent_id: UUID, project_slug: str | None = None) -> list[ProjectSourceRecord]:
        rows = [
            r for r in self._sources.values()
            if r.org_id == org_id and r.agent_id == agent_id
            and (project_slug is None or r.project_slug == project_slug)
        ]
        return sorted(rows, key=lambda r: (r.project_slug, r.path))

    def upsert_source(
        self, org_id: UUID, agent_id: UUID, project_slug: str, *, path: str, sha256: str, tipo: str,
        document_id: UUID | None,
    ) -> ProjectSourceRecord:
        if tipo not in SOURCE_TIPOS:
            raise ValueError(f"tipo must be one of {SOURCE_TIPOS}; got {tipo!r}")
        key = (agent_id, project_slug, path)
        prev = self._sources.get(key)
        rec = ProjectSourceRecord(
            id=prev.id if prev else uuid4(), org_id=org_id, agent_id=agent_id, project_slug=project_slug,
            path=path, sha256=sha256, tipo=tipo, document_id=document_id, synced_at=utcnow(),
        )
        self._sources[key] = rec
        return rec

    def delete_sources(self, org_id: UUID, agent_id: UUID, project_slug: str, paths: list[str]) -> int:
        removed = 0
        for path in paths:
            rec = self._sources.get((agent_id, project_slug, path))
            if rec is not None and rec.org_id == org_id:
                del self._sources[(agent_id, project_slug, path)]
                removed += 1
        return removed

    # learnings
    def insert_learnings(
        self, org_id: UUID, agent_id: UUID, project_slug: str, items: list[LearningInput]
    ) -> tuple[list[LearningRecord], int]:
        for item in items:
            _validate_learning(item)
        have = {r.row_sha for r in self._learnings.values() if r.agent_id == agent_id}
        inserted: list[LearningRecord] = []
        duplicates = 0
        for item in items:
            sha = learning_row_sha(item.data, item.texto)
            if sha in have:
                duplicates += 1
                continue
            have.add(sha)
            rec = LearningRecord(
                id=uuid4(), org_id=org_id, agent_id=agent_id, project_slug=project_slug, row_sha=sha,
                data=item.data, tipo=item.tipo, texto=item.texto, evidencia=item.evidencia,
                row_status=item.row_status, status="novo", review_note=None, reviewed_by=None,
                reviewed_at=None, created_at=utcnow(),
            )
            self._learnings[rec.id] = rec
            inserted.append(rec)
        return inserted, duplicates

    def list_learnings(
        self, org_id: UUID, agent_id: UUID, *, project_slug: str | None = None, status: str | None = None,
    ) -> list[LearningRecord]:
        rows = [
            r for r in self._learnings.values()
            if r.org_id == org_id and r.agent_id == agent_id
            and (project_slug is None or r.project_slug == project_slug)
            and (status is None or r.status == status)
        ]
        return sorted(rows, key=lambda r: (r.created_at, str(r.id)), reverse=True)

    def get_learning(self, org_id: UUID, agent_id: UUID, learning_id: UUID) -> LearningRecord:
        rec = self._learnings.get(learning_id)
        if rec is None or rec.org_id != org_id or rec.agent_id != agent_id:
            raise NotFound(f"learning {learning_id} not found")
        return rec

    def review_learning(
        self, org_id: UUID, agent_id: UUID, learning_id: UUID, *, status: str, note: str | None, reviewer: UUID | None,
    ) -> LearningRecord:
        _validate_review(status, note)
        rec = self.get_learning(org_id, agent_id, learning_id)
        rec = replace(rec, status=status, review_note=note, reviewed_by=reviewer, reviewed_at=utcnow())
        self._learnings[rec.id] = rec
        return rec


# ── Real ────────────────────────────────────────────────────────────────────


def _uuid_or_none(v: Any) -> UUID | None:
    return UUID(str(v)) if v else None


class SupabaseAgentPackageStore:
    """Real :class:`AgentPackageStore` — Postgres via the admin client.

    Bare table names through ``client.schema("agents").table(...)`` — never
    ``"agents.x"`` (``KB § PATTERNS/backend/postgrest-schema-targeting.md``)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def _paged(self, build, *, label: str) -> list[dict[str, Any]]:
        def fetch(start: int, end: int):
            return build().order("id").range(start, end).execute().data

        return list(iter_paged_rows(fetch, label=label))

    @staticmethod
    def _source(row: dict[str, Any]) -> ProjectSourceRecord:
        return ProjectSourceRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            project_slug=row["project_slug"], path=row["path"], sha256=row["sha256"], tipo=row["tipo"],
            document_id=_uuid_or_none(row.get("document_id")), synced_at=row["synced_at"],
        )

    @staticmethod
    def _learning(row: dict[str, Any]) -> LearningRecord:
        return LearningRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            project_slug=row["project_slug"], row_sha=row["row_sha"], data=row["data"], tipo=row["tipo"],
            texto=row["texto"], evidencia=row.get("evidencia") or "", row_status=row.get("row_status") or "novo",
            status=row["status"], review_note=row.get("review_note"),
            reviewed_by=_uuid_or_none(row.get("reviewed_by")), reviewed_at=row.get("reviewed_at"),
            created_at=row["created_at"],
        )

    # sources
    def list_sources(self, org_id: UUID, agent_id: UUID, project_slug: str | None = None) -> list[ProjectSourceRecord]:
        def build():
            q = self._t("agent_project_sources").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            return q.eq("project_slug", project_slug) if project_slug else q

        rows = self._paged(build, label=f"agent_project_sources agent_id={agent_id}")
        return sorted((self._source(r) for r in rows), key=lambda r: (r.project_slug, r.path))

    def upsert_source(
        self, org_id: UUID, agent_id: UUID, project_slug: str, *, path: str, sha256: str, tipo: str,
        document_id: UUID | None,
    ) -> ProjectSourceRecord:
        if tipo not in SOURCE_TIPOS:
            raise ValueError(f"tipo must be one of {SOURCE_TIPOS}; got {tipo!r}")
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "project_slug": project_slug, "path": path,
            "sha256": sha256, "tipo": tipo, "document_id": str(document_id) if document_id else None,
            "synced_at": utcnow_iso(),
        }
        resp = exec_query(self._t("agent_project_sources").upsert(payload, on_conflict="agent_id,project_slug,path"))
        rows = resp.data or []
        if not rows:
            raise RuntimeError(f"agent_project_sources upsert returned no row for {path!r}")
        return self._source(rows[0])

    def delete_sources(self, org_id: UUID, agent_id: UUID, project_slug: str, paths: list[str]) -> int:
        removed = 0
        for chunk in batched(list(paths), 50):
            resp = exec_query(
                self._t("agent_project_sources").delete()
                .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("project_slug", project_slug)
                .in_("path", chunk)
            )
            removed += len(resp.data or [])
        return removed

    # learnings
    def insert_learnings(
        self, org_id: UUID, agent_id: UUID, project_slug: str, items: list[LearningInput]
    ) -> tuple[list[LearningRecord], int]:
        for item in items:
            _validate_learning(item)
        # De-duplicate inside the batch first (a payload may repeat a row).
        by_sha: dict[str, LearningInput] = {}
        for item in items:
            by_sha.setdefault(learning_row_sha(item.data, item.texto), item)
        inserted: list[LearningRecord] = []
        for chunk in batched(list(by_sha.items()), 100):
            payload = [
                {
                    "org_id": str(org_id), "agent_id": str(agent_id), "project_slug": project_slug,
                    "row_sha": sha, "data": it.data, "tipo": it.tipo, "texto": it.texto,
                    "evidencia": it.evidencia, "row_status": it.row_status,
                }
                for sha, it in chunk
            ]
            # ON CONFLICT (agent_id, row_sha) DO NOTHING — race-safe, and the
            # response carries ONLY the rows that were actually inserted.
            resp = exec_query(
                self._t("agent_learnings").upsert(payload, on_conflict="agent_id,row_sha", ignore_duplicates=True)
            )
            inserted.extend(self._learning(r) for r in (resp.data or []))
        return inserted, len(items) - len(inserted)

    def list_learnings(
        self, org_id: UUID, agent_id: UUID, *, project_slug: str | None = None, status: str | None = None,
    ) -> list[LearningRecord]:
        def build():
            q = self._t("agent_learnings").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            if project_slug:
                q = q.eq("project_slug", project_slug)
            if status:
                q = q.eq("status", status)
            return q

        rows = self._paged(build, label=f"agent_learnings agent_id={agent_id}")
        return sorted((self._learning(r) for r in rows), key=lambda r: (r.created_at, str(r.id)), reverse=True)

    def get_learning(self, org_id: UUID, agent_id: UUID, learning_id: UUID) -> LearningRecord:
        resp = (
            self._t("agent_learnings").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .eq("id", str(learning_id)).limit(1).execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"learning {learning_id} not found")
        return self._learning(rows[0])

    def review_learning(
        self, org_id: UUID, agent_id: UUID, learning_id: UUID, *, status: str, note: str | None, reviewer: UUID | None,
    ) -> LearningRecord:
        _validate_review(status, note)
        resp = exec_query(
            self._t("agent_learnings").update({
                "status": status, "review_note": note,
                "reviewed_by": str(reviewer) if reviewer else None, "reviewed_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(learning_id))
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"learning {learning_id} not found")
        return self._learning(rows[0])


def get_agent_package_store(settings: Any) -> AgentPackageStore:
    """Real when a Supabase service-role key is configured, Fake otherwise —
    same signal as :func:`app.stores.studio_definitions.get_studio_definition_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeAgentPackageStore()
    from app.database import get_admin_client

    return SupabaseAgentPackageStore(get_admin_client())
