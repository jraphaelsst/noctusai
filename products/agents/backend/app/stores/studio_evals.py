"""Agent Studio — eval cases/runs/results store (contract §B2/§D4, slice
BE-KE), plus :class:`SupabaseEvalGate` — the Real implementation of
BE-DEF's ``EvalGate`` Protocol (contract §J2.1).

Three IO surfaces:

1. ``EvalStore`` — cases (CRUD) + runs (create/list/get/cancel/fail) +
   results (list, joined with the case's slug/titulo for the run-detail
   response) + a minimal ``VersionLookup``-shaped read of
   ``agents.agent_versions.compiled_hash`` (needed to stamp a new run and
   to 409 ``compile_required`` when it's NULL — contract §J2.2). Same
   "wave-1 slices never import each other's unfinished code" reasoning as
   ``app.stores.studio_knowledge.AgentLookup`` — see that module's
   docstring.
2. ``SupabaseEvalGate`` — contract §J2.1: BE-DEF defines ``GateRun`` +
   the ``EvalGate`` Protocol in ``app/studio/models.py`` (not present in
   this branch); this class satisfies that Protocol STRUCTURALLY (Python
   Protocols need no inheritance) and imports ``GateRun`` LAZILY, inside
   the one method that constructs it — so importing this module never
   touches ``app.studio.models``, and this branch's own test suite builds
   standalone. The import only actually executes once a caller (BE-DEF,
   post-merge) calls ``latest_concluded_run`` on a version that HAS a
   concluded run; the "no concluded run" branch returns ``None`` without
   ever reaching the import. BE-KE's own test for the "found" branch uses
   ``pytest.importorskip("app.studio.models")`` for exactly this reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import Conflict, NotFound

__all__ = [
    "CASE_SLUG_RE",
    "RUN_STATUSES",
    "RESULT_STATUSES",
    "ACTIVE_RUN_STATUSES",
    "EvalCaseInput",
    "EvalCaseRecord",
    "EvalRunRecord",
    "EvalResultRecord",
    "EvalResultWithCase",
    "VersionRef",
    "EvalStore",
    "FakeEvalStore",
    "SupabaseEvalStore",
    "get_eval_store",
    "SupabaseEvalGate",
    "get_eval_gate",
]

_SCHEMA = "agents"
_CASES_TABLE = "eval_cases"
_RUNS_TABLE = "eval_runs"
_RESULTS_TABLE = "eval_results"
_VERSIONS_TABLE = "agent_versions"

#: Contract §B2 `eval_runs.status` CHECK.
RUN_STATUSES = ("pendente", "executando", "concluida", "falhou", "cancelada")
#: Contract §B2 `eval_results.status` CHECK.
RESULT_STATUSES = ("pendente", "aprovado", "reprovado", "erro")
#: Statuses the "one run per version" partial unique index covers.
ACTIVE_RUN_STATUSES = ("pendente", "executando")

CASE_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

_UNSET: Any = object()


def _validate_slug(slug: str) -> None:
    if not CASE_SLUG_RE.match(slug):
        raise ValueError(f"slug must match ^[a-z0-9]+(-[a-z0-9]+)*$; got {slug!r}")


def _validate_criterios(criterios: dict[str, Any]) -> None:
    deve = criterios.get("deve") or []
    nao_deve = criterios.get("nao_deve") or []
    if not isinstance(deve, list) or not isinstance(nao_deve, list):
        raise ValueError("criterios.deve / criterios.nao_deve must be lists")
    if len(deve) + len(nao_deve) < 1:
        raise ValueError("criterios must contain at least one item across deve/nao_deve")


# ── dataclasses ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalCaseInput:
    slug: str
    titulo: str
    entrada: str
    criterios: dict[str, Any]
    contexto: str | None = None
    rubrica: str | None = None
    tags: tuple[str, ...] = ()
    ativo: bool = True


@dataclass(frozen=True)
class EvalCaseRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    slug: str
    titulo: str
    entrada: str
    contexto: str | None
    criterios: dict[str, Any]
    rubrica: str | None
    tags: tuple[str, ...]
    ativo: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvalRunRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    version_id: UUID
    compiled_hash: str
    status: str
    total: int
    aprovados: int
    score: float | None
    limiar: float
    started_by: UUID
    started_at: datetime | None
    finished_at: datetime | None
    erro: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvalResultRecord:
    id: UUID
    org_id: UUID
    run_id: UUID
    case_id: UUID
    status: str
    saida: str | None
    score: float | None
    veredito: Any | None
    notas_juiz: str | None
    duracao_ms: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EvalResultWithCase:
    result: EvalResultRecord
    case_slug: str
    case_titulo: str


@dataclass(frozen=True)
class VersionRef:
    id: UUID
    org_id: UUID
    agent_id: UUID
    compiled_hash: str | None
    status: str


# ── EvalStore ────────────────────────────────────────────────────────────


class EvalStore(Protocol):
    def list_cases(self, org_id: UUID, agent_id: UUID) -> list[EvalCaseRecord]: ...

    def get_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EvalCaseRecord:
        """Raises :class:`NotFound` for an unknown/foreign case id."""
        ...

    def create_case(self, org_id: UUID, agent_id: UUID, data: EvalCaseInput) -> EvalCaseRecord: ...

    def update_case(
        self, org_id: UUID, agent_id: UUID, case_id: UUID, *,
        titulo: str | Any = _UNSET, entrada: str | Any = _UNSET, contexto: str | None | Any = _UNSET,
        criterios: dict[str, Any] | Any = _UNSET, rubrica: str | None | Any = _UNSET,
        tags: tuple[str, ...] | Any = _UNSET, ativo: bool | Any = _UNSET,
    ) -> EvalCaseRecord: ...

    def delete_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> None: ...

    def get_version_ref(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> VersionRef:
        """Minimal read of `agents.agent_versions` — raises :class:`NotFound`
        when the version doesn't exist for this (org, agent)."""
        ...

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
    ) -> EvalRunRecord:
        """Resolves the case set (``case_ids`` if given, else every active
        case for the agent), raises :class:`NotFound` if an explicit id
        doesn't belong to the agent, raises :class:`ValueError` if the
        resolved set is empty, raises :class:`Conflict` if a
        pendente/executando run already exists for ``version_id``."""
        ...

    def list_runs(self, org_id: UUID, agent_id: UUID, version_id: UUID | None = None) -> list[EvalRunRecord]: ...

    def get_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        """Raises :class:`NotFound` for an unknown/foreign run id."""
        ...

    def list_results_with_cases(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[EvalResultWithCase]: ...

    def mark_run_failed(self, org_id: UUID, run_id: UUID, *, erro: str) -> EvalRunRecord:
        """Used when scheduling itself fails (contract §J2.2 fail-closed
        503 path) — flips a freshly-created `pendente` run to `falhou` so
        it never blocks the one-active-run-per-version slot forever."""
        ...

    def cancel_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        """Raises :class:`Conflict` if the run isn't currently
        pendente/executando."""
        ...


class FakeEvalStore:
    """In-memory :class:`EvalStore`."""

    def __init__(self) -> None:
        self._cases: dict[UUID, dict[str, Any]] = {}
        self._runs: dict[UUID, dict[str, Any]] = {}
        self._results: dict[UUID, list[dict[str, Any]]] = {}
        # Test seam — real versions live in BE-DEF's store; the Fake here
        # lets router tests seed a version's compiled_hash directly.
        self._versions: dict[UUID, dict[str, Any]] = {}

    # -- test seam for the version lookup ------------------------------

    def seed_version(self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str | None, status: str = "rascunho") -> None:
        self._versions[version_id] = {
            "id": version_id, "org_id": org_id, "agent_id": agent_id,
            "compiled_hash": compiled_hash, "status": status,
        }

    def get_version_ref(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> VersionRef:
        row = self._versions.get(version_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"version {version_id} not found for agent {agent_id}")
        return VersionRef(**row)

    # -- cases ------------------------------------------------------------

    def _own_cases(self, org_id: UUID, agent_id: UUID):
        return [r for r in self._cases.values() if r["org_id"] == org_id and r["agent_id"] == agent_id]

    def list_cases(self, org_id: UUID, agent_id: UUID) -> list[EvalCaseRecord]:
        rows = sorted(self._own_cases(org_id, agent_id), key=lambda r: r["created_at"])
        return [self._case_record(r) for r in rows]

    def get_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EvalCaseRecord:
        row = self._cases.get(case_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        return self._case_record(row)

    def create_case(self, org_id: UUID, agent_id: UUID, data: EvalCaseInput) -> EvalCaseRecord:
        _validate_slug(data.slug)
        _validate_criterios(data.criterios)
        for row in self._own_cases(org_id, agent_id):
            if row["slug"] == data.slug:
                raise ValueError(f"slug {data.slug!r} already exists for this agent")
        now = utcnow()
        row = {
            "id": uuid4(), "org_id": org_id, "agent_id": agent_id, "slug": data.slug, "titulo": data.titulo,
            "entrada": data.entrada, "contexto": data.contexto, "criterios": dict(data.criterios),
            "rubrica": data.rubrica, "tags": tuple(data.tags), "ativo": data.ativo,
            "created_at": now, "updated_at": now,
        }
        self._cases[row["id"]] = row
        return self._case_record(row)

    def update_case(
        self, org_id: UUID, agent_id: UUID, case_id: UUID, *,
        titulo: Any = _UNSET, entrada: Any = _UNSET, contexto: Any = _UNSET, criterios: Any = _UNSET,
        rubrica: Any = _UNSET, tags: Any = _UNSET, ativo: Any = _UNSET,
    ) -> EvalCaseRecord:
        row = self._cases.get(case_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        if titulo is not _UNSET:
            row["titulo"] = titulo
        if entrada is not _UNSET:
            row["entrada"] = entrada
        if contexto is not _UNSET:
            row["contexto"] = contexto
        if criterios is not _UNSET:
            _validate_criterios(criterios)
            row["criterios"] = dict(criterios)
        if rubrica is not _UNSET:
            row["rubrica"] = rubrica
        if tags is not _UNSET:
            row["tags"] = tuple(tags)
        if ativo is not _UNSET:
            row["ativo"] = ativo
        row["updated_at"] = utcnow()
        return self._case_record(row)

    def delete_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> None:
        row = self._cases.get(case_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        del self._cases[case_id]

    # -- runs ---------------------------------------------------------

    def _own_runs(self, org_id: UUID, agent_id: UUID):
        return [r for r in self._runs.values() if r["org_id"] == org_id and r["agent_id"] == agent_id]

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
    ) -> EvalRunRecord:
        for row in self._own_runs(org_id, agent_id):
            if row["version_id"] == version_id and row["status"] in ACTIVE_RUN_STATUSES:
                raise Conflict(f"a run is already in progress for version {version_id}")

        if case_ids is None:
            resolved = [c["id"] for c in self._own_cases(org_id, agent_id) if c["ativo"]]
        else:
            resolved = []
            for cid in case_ids:
                row = self._cases.get(cid)
                if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
                    raise NotFound(f"eval case {cid} not found for agent {agent_id}")
                resolved.append(cid)
        if not resolved:
            raise ValueError("no eval cases to run")

        now = utcnow()
        row = {
            "id": uuid4(), "org_id": org_id, "agent_id": agent_id, "version_id": version_id,
            "compiled_hash": compiled_hash, "status": "pendente", "total": len(resolved), "aprovados": 0,
            "score": None, "limiar": limiar, "started_by": started_by, "started_at": now,
            "finished_at": None, "erro": None, "created_at": now, "updated_at": now,
        }
        self._runs[row["id"]] = row
        self._results[row["id"]] = [
            {
                "id": uuid4(), "org_id": org_id, "run_id": row["id"], "case_id": cid, "status": "pendente",
                "saida": None, "score": None, "veredito": None, "notas_juiz": None, "duracao_ms": None,
                "created_at": now, "updated_at": now,
            }
            for cid in resolved
        ]
        return self._run_record(row)

    def list_runs(self, org_id: UUID, agent_id: UUID, version_id: UUID | None = None) -> list[EvalRunRecord]:
        rows = self._own_runs(org_id, agent_id)
        if version_id is not None:
            rows = [r for r in rows if r["version_id"] == version_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [self._run_record(r) for r in rows]

    def get_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        row = self._runs.get(run_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"eval run {run_id} not found for agent {agent_id}")
        return self._run_record(row)

    def list_results_with_cases(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[EvalResultWithCase]:
        self.get_run(org_id, agent_id, run_id)
        out = []
        for row in self._results.get(run_id, []):
            case = self._cases.get(row["case_id"])
            out.append(EvalResultWithCase(
                result=self._result_record(row),
                case_slug=case["slug"] if case else "",
                case_titulo=case["titulo"] if case else "",
            ))
        return out

    def mark_run_failed(self, org_id: UUID, run_id: UUID, *, erro: str) -> EvalRunRecord:
        row = self._runs.get(run_id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"eval run {run_id} not found")
        row["status"] = "falhou"
        row["erro"] = erro
        row["finished_at"] = utcnow()
        row["updated_at"] = utcnow()
        return self._run_record(row)

    def cancel_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        row = self._runs.get(run_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"eval run {run_id} not found for agent {agent_id}")
        if row["status"] not in ACTIVE_RUN_STATUSES:
            raise Conflict(f"run {run_id} is not in a cancellable state ({row['status']})")
        row["status"] = "cancelada"
        row["finished_at"] = utcnow()
        row["updated_at"] = utcnow()
        return self._run_record(row)

    # -- record builders ------------------------------------------------

    @staticmethod
    def _case_record(row: dict[str, Any]) -> EvalCaseRecord:
        return EvalCaseRecord(**row)

    @staticmethod
    def _run_record(row: dict[str, Any]) -> EvalRunRecord:
        return EvalRunRecord(**row)

    @staticmethod
    def _result_record(row: dict[str, Any]) -> EvalResultRecord:
        return EvalResultRecord(**row)


class SupabaseEvalStore:
    """Real :class:`EvalStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _cases(self):
        return self._client.schema(_SCHEMA).table(_CASES_TABLE)

    def _runs(self):
        return self._client.schema(_SCHEMA).table(_RUNS_TABLE)

    def _results(self):
        return self._client.schema(_SCHEMA).table(_RESULTS_TABLE)

    def _versions(self):
        return self._client.schema(_SCHEMA).table(_VERSIONS_TABLE)

    def get_version_ref(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> VersionRef:
        resp = (
            self._versions().select("id, org_id, agent_id, compiled_hash, status")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(version_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"version {version_id} not found for agent {agent_id}")
        row = rows[0]
        return VersionRef(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            compiled_hash=row.get("compiled_hash"), status=row["status"],
        )

    # -- cases ------------------------------------------------------------

    def list_cases(self, org_id: UUID, agent_id: UUID) -> list[EvalCaseRecord]:
        resp = (
            self._cases().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .order("created_at")
            .execute()
        )
        return [self._case_record(r) for r in (resp.data or [])]

    def get_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EvalCaseRecord:
        resp = (
            self._cases().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(case_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        return self._case_record(rows[0])

    def create_case(self, org_id: UUID, agent_id: UUID, data: EvalCaseInput) -> EvalCaseRecord:
        _validate_slug(data.slug)
        _validate_criterios(data.criterios)
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "slug": data.slug, "titulo": data.titulo,
            "entrada": data.entrada, "contexto": data.contexto, "criterios": dict(data.criterios),
            "rubrica": data.rubrica, "tags": list(data.tags), "ativo": data.ativo,
        }
        resp = self._cases().insert(payload).execute()
        rows = resp.data or []
        if not rows:
            raise ValueError(f"slug {data.slug!r} already exists for this agent")
        return self._case_record(rows[0])

    def update_case(
        self, org_id: UUID, agent_id: UUID, case_id: UUID, *,
        titulo: Any = _UNSET, entrada: Any = _UNSET, contexto: Any = _UNSET, criterios: Any = _UNSET,
        rubrica: Any = _UNSET, tags: Any = _UNSET, ativo: Any = _UNSET,
    ) -> EvalCaseRecord:
        updates: dict[str, Any] = {"updated_at": utcnow_iso()}
        if titulo is not _UNSET:
            updates["titulo"] = titulo
        if entrada is not _UNSET:
            updates["entrada"] = entrada
        if contexto is not _UNSET:
            updates["contexto"] = contexto
        if criterios is not _UNSET:
            _validate_criterios(criterios)
            updates["criterios"] = dict(criterios)
        if rubrica is not _UNSET:
            updates["rubrica"] = rubrica
        if tags is not _UNSET:
            updates["tags"] = list(tags)
        if ativo is not _UNSET:
            updates["ativo"] = ativo
        resp = (
            self._cases().update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(case_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        return self._case_record(rows[0])

    def delete_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> None:
        resp = (
            self._cases().delete()
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(case_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")

    # -- runs ---------------------------------------------------------

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
    ) -> EvalRunRecord:
        active = (
            self._runs().select("id", count="exact")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id))
            .in_("status", list(ACTIVE_RUN_STATUSES))
            .execute()
        )
        if (active.count or 0) > 0:
            raise Conflict(f"a run is already in progress for version {version_id}")

        if case_ids is None:
            resp = (
                self._cases().select("id")
                .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("ativo", True)
                .execute()
            )
            resolved = [UUID(str(r["id"])) for r in (resp.data or [])]
        else:
            resolved = []
            for cid in case_ids:
                self.get_case(org_id, agent_id, cid)  # raises NotFound if foreign/missing
                resolved.append(cid)
        if not resolved:
            raise ValueError("no eval cases to run")

        now_iso = utcnow_iso()
        run_payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "version_id": str(version_id),
            "compiled_hash": compiled_hash, "status": "pendente", "total": len(resolved), "aprovados": 0,
            "score": None, "limiar": limiar, "started_by": str(started_by), "started_at": now_iso,
        }
        resp = self._runs().insert(run_payload).execute()
        rows = resp.data or []
        if not rows:
            raise Conflict(f"a run is already in progress for version {version_id}")
        run = self._run_record(rows[0])

        results_payload = [
            {
                "org_id": str(org_id), "run_id": str(run.id), "case_id": str(cid), "status": "pendente",
            }
            for cid in resolved
        ]
        self._results().insert(results_payload).execute()
        return run

    def list_runs(self, org_id: UUID, agent_id: UUID, version_id: UUID | None = None) -> list[EvalRunRecord]:
        query = (
            self._runs().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
        )
        if version_id is not None:
            query = query.eq("version_id", str(version_id))
        resp = query.order("created_at", desc=True).execute()
        return [self._run_record(r) for r in (resp.data or [])]

    def get_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        resp = (
            self._runs().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(run_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found for agent {agent_id}")
        return self._run_record(rows[0])

    def list_results_with_cases(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[EvalResultWithCase]:
        self.get_run(org_id, agent_id, run_id)
        resp = self._results().select("*").eq("org_id", str(org_id)).eq("run_id", str(run_id)).execute()
        results = [self._result_record(r) for r in (resp.data or [])]
        out: list[EvalResultWithCase] = []
        for result in results:
            try:
                case = self.get_case(org_id, agent_id, result.case_id)
                slug, titulo = case.slug, case.titulo
            except NotFound:
                slug, titulo = "", ""
            out.append(EvalResultWithCase(result=result, case_slug=slug, case_titulo=titulo))
        return out

    def mark_run_failed(self, org_id: UUID, run_id: UUID, *, erro: str) -> EvalRunRecord:
        resp = (
            self._runs().update({
                "status": "falhou", "erro": erro, "finished_at": utcnow_iso(), "updated_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("id", str(run_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found")
        return self._run_record(rows[0])

    def cancel_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        current = self.get_run(org_id, agent_id, run_id)
        if current.status not in ACTIVE_RUN_STATUSES:
            raise Conflict(f"run {run_id} is not in a cancellable state ({current.status})")
        resp = (
            self._runs().update({
                "status": "cancelada", "finished_at": utcnow_iso(), "updated_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(run_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found for agent {agent_id}")
        return self._run_record(rows[0])

    # -- record builders ------------------------------------------------

    @staticmethod
    def _case_record(row: dict[str, Any]) -> EvalCaseRecord:
        return EvalCaseRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            slug=row["slug"], titulo=row["titulo"], entrada=row["entrada"], contexto=row.get("contexto"),
            criterios=row.get("criterios") or {}, rubrica=row.get("rubrica"),
            tags=tuple(row.get("tags") or ()), ativo=bool(row.get("ativo", False)),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _run_record(row: dict[str, Any]) -> EvalRunRecord:
        return EvalRunRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            version_id=UUID(str(row["version_id"])), compiled_hash=row["compiled_hash"], status=row["status"],
            total=int(row.get("total") or 0), aprovados=int(row.get("aprovados") or 0),
            score=float(row["score"]) if row.get("score") is not None else None,
            limiar=float(row["limiar"]), started_by=UUID(str(row["started_by"])),
            started_at=row.get("started_at"), finished_at=row.get("finished_at"), erro=row.get("erro"),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _result_record(row: dict[str, Any]) -> EvalResultRecord:
        return EvalResultRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), run_id=UUID(str(row["run_id"])),
            case_id=UUID(str(row["case_id"])), status=row["status"], saida=row.get("saida"),
            score=float(row["score"]) if row.get("score") is not None else None,
            veredito=row.get("veredito"), notas_juiz=row.get("notas_juiz"),
            duracao_ms=row.get("duracao_ms"), created_at=row["created_at"], updated_at=row["updated_at"],
        )


def get_eval_store(settings: Any) -> EvalStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeEvalStore()
    from app.database import get_admin_client

    return SupabaseEvalStore(get_admin_client())


# ── SupabaseEvalGate — the Real side of BE-DEF's `EvalGate` Protocol ─────


class SupabaseEvalGate:
    """Contract §J2.1 Real implementation. See module docstring for the
    lazy-import rationale."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def latest_concluded_run(self, org_id: UUID, version_id: UUID):
        resp = (
            self._client.schema(_SCHEMA).table(_RUNS_TABLE)
            .select("id, score, limiar, compiled_hash, status")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)).eq("status", "concluida")
            .order("finished_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        from app.studio.models import GateRun  # lazy — see module docstring

        return GateRun(
            id=UUID(str(row["id"])),
            score=float(row["score"]) if row.get("score") is not None else None,
            limiar=float(row["limiar"]),
            compiled_hash=row["compiled_hash"],
            status=row["status"],
        )


def get_eval_gate(settings: Any) -> SupabaseEvalGate | None:
    """``None`` when no Supabase service-role key is configured — callers
    (BE-RT's production dependency binding) fall back to BE-DEF's
    ``FakeEvalGate`` in that case, mirroring every other Real/Fake factory
    in this product."""
    if not getattr(settings, "supabase_service_role_key", None):
        return None
    from app.database import get_admin_client

    return SupabaseEvalGate(get_admin_client())
