"""Agent Studio — eval cases/runs/results store (contract §B2/§D4, slice
BE-KE), plus :class:`SupabaseEvalGate` — the Real implementation of the
``EvalGate`` Protocol (contract §J2.1, ``app.studio.models``).

Two IO surfaces (seed Protocol + Fake + Real + factory each):

1. ``EvalStore`` — cases (CRUD) + runs (create/list/get/cancel/fail) +
   results (list, joined with the case's slug/titulo in ONE embedded
   select). Version/agent resolution is NOT this module's job — the
   router resolves both through BE-DEF's ``StudioDefinitionStore``.
2. ``EvalGate`` — :class:`SupabaseEvalGate` / ``FakeEvalGate`` via
   :func:`get_eval_gate`: the newest ``concluida`` AND ``completa`` run
   of a version (H1 — a later subset run never hides the complete one).

Hardening (wave-1 security review + compliance review): a run and its
pending results are created by ONE ``agents.create_eval_run`` call (L6 —
no orphan ``pendente`` run can block the slot); an explicit case list is
deduped and capped at :data:`~app.studio.models.RUN_CASE_IDS_MAX`; every
write goes through ``app.stores._db_errors`` — a duplicate slug is 409
``slug_taken``, a concurrent run 409 ``run_in_progress``, deleting a case
that has results 409 ``case_in_use`` (supabase-py RAISES on constraint
violations; it never returns empty rows). The Fake raises the same typed
errors from the same conditions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query, exec_rpc
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.studio.models import (
    EVAL_RUN_BUDGET_USD_MAX,
    EVAL_RUN_BUDGET_USD_MIN,
    EVAL_RUN_MODEL_ALLOWLIST,
    RUN_CASE_IDS_MAX,
    EvalGate,
    FakeEvalGate,
    GateRun,
)
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

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
    "EvalStore",
    "FakeEvalStore",
    "SupabaseEvalStore",
    "get_eval_store",
    "SupabaseEvalGate",
    "get_eval_gate",
    "normalize_case_ids",
]

_SCHEMA = "agents"
_CASES_TABLE = "eval_cases"
_RUNS_TABLE = "eval_runs"
_RESULTS_TABLE = "eval_results"

#: Contract §B2 `eval_runs.status` CHECK.
RUN_STATUSES = ("pendente", "executando", "concluida", "falhou", "cancelada")
#: Contract §B2 `eval_results.status` CHECK, extended by migration 014 with
#: `'pulado'` — a case the runner never started because the run's cost cap
#: (`eval_runs.limite_usd`, contract §L) was already reached.
RESULT_STATUSES = ("pendente", "aprovado", "reprovado", "erro", "pulado")
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


def _validate_modelo_geracao(modelo_geracao: str | None) -> None:
    if modelo_geracao is not None and modelo_geracao not in EVAL_RUN_MODEL_ALLOWLIST:
        raise ValueError(f"modelo_geracao must be one of {EVAL_RUN_MODEL_ALLOWLIST} or None; got {modelo_geracao!r}")


def _validate_limite_usd(limite_usd: float | None) -> None:
    if limite_usd is not None and not (EVAL_RUN_BUDGET_USD_MIN < limite_usd <= EVAL_RUN_BUDGET_USD_MAX):
        raise ValueError(
            f"limite_usd must be in ({EVAL_RUN_BUDGET_USD_MIN}, {EVAL_RUN_BUDGET_USD_MAX}] or None; "
            f"got {limite_usd!r}"
        )


def normalize_case_ids(case_ids: list[UUID] | None) -> list[UUID] | None:
    """L6: dedupe (first occurrence wins, order kept) and cap an explicit
    case list. ``None`` stays ``None`` — "every active case" (a COMPLETE run)."""
    if case_ids is None:
        return None
    seen: dict[UUID, None] = {}
    for cid in case_ids:
        seen.setdefault(cid, None)
    out = list(seen)
    if len(out) > RUN_CASE_IDS_MAX:
        raise ValueError(f"at most {RUN_CASE_IDS_MAX} distinct case_ids per run")
    return out


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
    #: H1: ``True`` only for a run over every active case at run time
    #: (``case_ids`` omitted) — the only kind the publish gate accepts.
    completa: bool = False
    #: Contract §L: ``None`` ⇒ the version's own model (the publish-gate-
    #: eligible shape); otherwise the cheaper-iteration override the runner
    #: used instead of ``spec.model`` — never satisfies the publish gate.
    modelo_geracao: str | None = None
    #: Contract §L: the run's cost cap in USD (``None`` ⇒ the caller didn't
    #: set one — the router stamps the settings default before create_run).
    limite_usd: float | None = None
    #: Contract §L: the run's accumulated cost (sum of every result's
    #: ``custo_usd``) — ``None`` until the runner has written at least one
    #: result.
    custo_usd: float | None = None


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
    #: Contract §L: generator + judge cost of THIS case, summed.
    custo_usd: float | None = None
    #: Contract §L: the generator turn's token counts (Claude Agent SDK
    #: ``ResultMessage.usage``) — ``None`` when the SDK never reported a
    #: ``ResultMessage`` for this case (logged, never silently defaulted).
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    tokens_cache_leitura: int | None = None


@dataclass(frozen=True)
class EvalResultWithCase:
    result: EvalResultRecord
    case_slug: str
    case_titulo: str


# ── EvalStore ────────────────────────────────────────────────────────────


class EvalStore(Protocol):
    def list_cases(self, org_id: UUID, agent_id: UUID) -> list[EvalCaseRecord]: ...

    def get_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EvalCaseRecord:
        """Raises :class:`NotFound` for an unknown/foreign case id."""
        ...

    def create_case(self, org_id: UUID, agent_id: UUID, data: EvalCaseInput) -> EvalCaseRecord:
        """Raises ``StudioConflict('slug_taken')`` for a duplicate slug."""
        ...

    def update_case(
        self, org_id: UUID, agent_id: UUID, case_id: UUID, *,
        titulo: str | Any = _UNSET, entrada: str | Any = _UNSET, contexto: str | None | Any = _UNSET,
        criterios: dict[str, Any] | Any = _UNSET, rubrica: str | None | Any = _UNSET,
        tags: tuple[str, ...] | Any = _UNSET, ativo: bool | Any = _UNSET,
    ) -> EvalCaseRecord: ...

    def delete_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> None:
        """Raises ``StudioConflict('case_in_use')`` when any run has a
        result for the case (FK) — deactivate it instead."""
        ...

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
        modelo_geracao: str | None = None, limite_usd: float | None = None,
    ) -> EvalRunRecord:
        """ONE transaction (``agents.create_eval_run``): resolves the case
        set (``case_ids`` deduped+capped, else every active case →
        ``completa=True``), inserts the run and its pending results. Raises
        :class:`NotFound` for a foreign case id, :class:`ValueError` for an
        empty set / too many ids / an invalid ``modelo_geracao``/
        ``limite_usd``, ``StudioConflict('run_in_progress')`` when a
        pendente/executando run already exists for ``version_id``."""
        ...

    def list_runs(self, org_id: UUID, agent_id: UUID, version_id: UUID | None = None) -> list[EvalRunRecord]: ...

    def get_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        """Raises :class:`NotFound` for an unknown/foreign run id."""
        ...

    def list_results_with_cases(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[EvalResultWithCase]:
        """One embedded read; a result whose case is missing is a broken
        invariant (FK) and raises — never a blank slug."""
        ...

    def mark_run_failed(self, org_id: UUID, run_id: UUID, *, erro: str) -> EvalRunRecord:
        """Used when scheduling itself fails (contract §J2.2 fail-closed
        503 path) — flips a freshly-created `pendente` run to `falhou` so
        it never blocks the one-active-run-per-version slot forever."""
        ...

    def cancel_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        """Raises ``StudioConflict('run_not_cancellable')`` if the run isn't
        currently pendente/executando."""
        ...


class FakeEvalStore:
    """In-memory :class:`EvalStore` — raises the same typed errors the Real
    store maps from the 013 constraints (unique slug, one active run per
    version, results FK on cases)."""

    def __init__(self) -> None:
        self._cases: dict[UUID, dict[str, Any]] = {}
        self._runs: dict[UUID, dict[str, Any]] = {}
        self._results: dict[UUID, list[dict[str, Any]]] = {}

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
        for row in self._cases.values():
            if row["agent_id"] == agent_id and row["slug"] == data.slug:
                # 013 UNIQUE (agent_id, slug)
                raise StudioConflict("slug_taken", f"slug {data.slug!r} already exists for this agent")
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
        if criterios is not _UNSET:
            _validate_criterios(criterios)
        if titulo is not _UNSET:
            row["titulo"] = titulo
        if entrada is not _UNSET:
            row["entrada"] = entrada
        if contexto is not _UNSET:
            row["contexto"] = contexto
        if criterios is not _UNSET:
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
        if any(r["case_id"] == case_id for results in self._results.values() for r in results):
            # 013 `eval_results.case_id` FK (no cascade).
            raise StudioConflict("case_in_use", f"eval case {case_id} has results — deactivate it instead")
        del self._cases[case_id]

    # -- runs ---------------------------------------------------------

    def _own_runs(self, org_id: UUID, agent_id: UUID):
        return [r for r in self._runs.values() if r["org_id"] == org_id and r["agent_id"] == agent_id]

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
        modelo_geracao: str | None = None, limite_usd: float | None = None,
    ) -> EvalRunRecord:
        _validate_modelo_geracao(modelo_geracao)
        _validate_limite_usd(limite_usd)
        explicit = normalize_case_ids(case_ids)
        if explicit is None:
            resolved = [
                c["id"] for c in sorted(self._own_cases(org_id, agent_id), key=lambda c: c["created_at"])
                if c["ativo"]
            ]
        else:
            resolved = []
            for cid in explicit:
                row = self._cases.get(cid)
                if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
                    raise NotFound(f"eval case {cid} not found for agent {agent_id}")
                resolved.append(cid)
        if not resolved:
            raise ValueError("no eval cases to run")
        for row in self._runs.values():
            if row["version_id"] == version_id and row["status"] in ACTIVE_RUN_STATUSES:
                # 013 eval_runs_one_active_per_version_idx
                raise StudioConflict("run_in_progress", f"a run is already in progress for version {version_id}")

        now = utcnow()
        row = {
            "id": uuid4(), "org_id": org_id, "agent_id": agent_id, "version_id": version_id,
            "compiled_hash": compiled_hash, "status": "pendente", "total": len(resolved), "aprovados": 0,
            "score": None, "limiar": limiar, "started_by": started_by, "started_at": now,
            "finished_at": None, "erro": None, "created_at": now, "updated_at": now,
            "completa": explicit is None,
            "modelo_geracao": modelo_geracao, "limite_usd": limite_usd, "custo_usd": None,
        }
        self._runs[row["id"]] = row
        self._results[row["id"]] = [
            {
                "id": uuid4(), "org_id": org_id, "run_id": row["id"], "case_id": cid, "status": "pendente",
                "saida": None, "score": None, "veredito": None, "notas_juiz": None, "duracao_ms": None,
                "created_at": now, "updated_at": now,
                "custo_usd": None, "tokens_entrada": None, "tokens_saida": None, "tokens_cache_leitura": None,
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
            if case is None:
                raise RuntimeError(f"eval result {row['id']} references missing case {row['case_id']}")
            out.append(EvalResultWithCase(
                result=self._result_record(row), case_slug=case["slug"], case_titulo=case["titulo"],
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
            raise StudioConflict("run_not_cancellable", f"run {run_id} is not in a cancellable state ({row['status']})")
        row["status"] = "cancelada"
        row["finished_at"] = utcnow()
        row["updated_at"] = utcnow()
        return self._run_record(row)

    # -- test seam: the runner's writes (BE-RT owns the real runner) ------

    def finish_run(self, run_id: UUID, *, score: float, aprovados: int | None = None) -> EvalRunRecord:
        row = self._runs[run_id]
        row.update(status="concluida", score=score, finished_at=utcnow(), updated_at=utcnow())
        if aprovados is not None:
            row["aprovados"] = aprovados
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
    """Real :class:`EvalStore` — Postgres via the admin client. Bare table
    names (``KB § PATTERNS/backend/postgrest-schema-targeting.md``);
    unbounded reads page through ``iter_paged_rows``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def _paged(self, build, *, label: str, order: tuple[tuple[str, bool], ...]) -> list[dict[str, Any]]:
        def fetch(start: int, end: int):
            q = build()
            for col, desc in order:
                q = q.order(col, desc=desc)
            return q.order("id").range(start, end).execute().data

        return list(iter_paged_rows(fetch, label=label))

    # -- cases ------------------------------------------------------------

    def list_cases(self, org_id: UUID, agent_id: UUID) -> list[EvalCaseRecord]:
        rows = self._paged(
            lambda: self._t(_CASES_TABLE).select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label=f"eval_cases agent_id={agent_id}", order=(("created_at", False),),
        )
        return [self._case_record(r) for r in rows]

    def get_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EvalCaseRecord:
        resp = (
            self._t(_CASES_TABLE).select("*")
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
        resp = exec_query(self._t(_CASES_TABLE).insert(payload), unique_code="slug_taken")
        rows = resp.data or []
        if not rows:
            raise RuntimeError(f"insert of eval case {data.slug!r} returned no row")
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
        resp = exec_query(
            self._t(_CASES_TABLE).update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(case_id))
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")
        return self._case_record(rows[0])

    def delete_case(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> None:
        resp = exec_query(
            self._t(_CASES_TABLE).delete()
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(case_id)),
            fk_code="case_in_use",
        )
        if not (resp.data or []):
            raise NotFound(f"eval case {case_id} not found for agent {agent_id}")

    # -- runs ---------------------------------------------------------

    def create_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, limiar: float,
        case_ids: list[UUID] | None, started_by: UUID,
        modelo_geracao: str | None = None, limite_usd: float | None = None,
    ) -> EvalRunRecord:
        _validate_modelo_geracao(modelo_geracao)
        _validate_limite_usd(limite_usd)
        explicit = normalize_case_ids(case_ids)
        resp = exec_rpc(self._client, _SCHEMA, "create_eval_run", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_version_id": str(version_id),
            "p_compiled_hash": compiled_hash, "p_limiar": limiar,
            "p_case_ids": [str(c) for c in explicit] if explicit is not None else None,
            "p_started_by": str(started_by),
            "p_modelo_geracao": modelo_geracao, "p_limite_usd": limite_usd,
        }, unique_code="run_in_progress")
        run_id = resp.data
        if isinstance(run_id, list):
            run_id = run_id[0] if run_id else None
        if isinstance(run_id, dict):
            run_id = next(iter(run_id.values()), None)
        if not run_id:
            raise RuntimeError(f"create_eval_run returned no run id: {resp.data!r}")
        return self.get_run(org_id, agent_id, UUID(str(run_id)))

    def list_runs(self, org_id: UUID, agent_id: UUID, version_id: UUID | None = None) -> list[EvalRunRecord]:
        def build():
            q = self._t(_RUNS_TABLE).select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            return q.eq("version_id", str(version_id)) if version_id is not None else q

        rows = self._paged(build, label=f"eval_runs agent_id={agent_id}", order=(("created_at", True),))
        return [self._run_record(r) for r in rows]

    def get_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        resp = (
            self._t(_RUNS_TABLE).select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(run_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found for agent {agent_id}")
        return self._run_record(rows[0])

    def list_results_with_cases(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[EvalResultWithCase]:
        self.get_run(org_id, agent_id, run_id)
        rows = self._paged(
            lambda: self._t(_RESULTS_TABLE).select("*, eval_cases(slug, titulo)")
            .eq("org_id", str(org_id)).eq("run_id", str(run_id)),
            label=f"eval_results run_id={run_id}", order=(("created_at", False),),
        )
        out: list[EvalResultWithCase] = []
        for row in rows:
            case = row.get("eval_cases")
            if not case:
                raise RuntimeError(f"eval result {row.get('id')} came back without its case (FK broken?)")
            out.append(EvalResultWithCase(
                result=self._result_record(row), case_slug=case["slug"], case_titulo=case["titulo"],
            ))
        return out

    def mark_run_failed(self, org_id: UUID, run_id: UUID, *, erro: str) -> EvalRunRecord:
        resp = exec_query(
            self._t(_RUNS_TABLE).update({
                "status": "falhou", "erro": erro, "finished_at": utcnow_iso(), "updated_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("id", str(run_id))
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found")
        return self._run_record(rows[0])

    def cancel_run(self, org_id: UUID, agent_id: UUID, run_id: UUID) -> EvalRunRecord:
        current = self.get_run(org_id, agent_id, run_id)
        if current.status not in ACTIVE_RUN_STATUSES:
            raise StudioConflict("run_not_cancellable", f"run {run_id} is not in a cancellable state ({current.status})")
        resp = exec_query(
            self._t(_RUNS_TABLE).update({
                "status": "cancelada", "finished_at": utcnow_iso(), "updated_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(run_id))
            .in_("status", list(ACTIVE_RUN_STATUSES))
        )
        rows = resp.data or []
        if not rows:
            # Finished between the read and the write.
            raise StudioConflict("run_not_cancellable", f"run {run_id} is no longer in a cancellable state")
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
            completa=bool(row.get("completa", False)),
            modelo_geracao=row.get("modelo_geracao"),
            limite_usd=float(row["limite_usd"]) if row.get("limite_usd") is not None else None,
            custo_usd=float(row["custo_usd"]) if row.get("custo_usd") is not None else None,
        )

    @staticmethod
    def _result_record(row: dict[str, Any]) -> EvalResultRecord:
        return EvalResultRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), run_id=UUID(str(row["run_id"])),
            case_id=UUID(str(row["case_id"])), status=row["status"], saida=row.get("saida"),
            score=float(row["score"]) if row.get("score") is not None else None,
            veredito=row.get("veredito"), notas_juiz=row.get("notas_juiz"),
            duracao_ms=row.get("duracao_ms"), created_at=row["created_at"], updated_at=row["updated_at"],
            custo_usd=float(row["custo_usd"]) if row.get("custo_usd") is not None else None,
            tokens_entrada=row.get("tokens_entrada"), tokens_saida=row.get("tokens_saida"),
            tokens_cache_leitura=row.get("tokens_cache_leitura"),
        )


def get_eval_store(settings: Any) -> EvalStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeEvalStore()
    from app.database import get_admin_client

    return SupabaseEvalStore(get_admin_client())


# ── SupabaseEvalGate — the Real side of the `EvalGate` Protocol ──────────


class SupabaseEvalGate:
    """Contract §J2.1 Real implementation: the newest ``concluida`` run of
    the version that is ``completa`` (H1)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def latest_concluded_run(self, org_id: UUID, version_id: UUID) -> GateRun | None:
        resp = (
            self._client.schema(_SCHEMA).table(_RUNS_TABLE)
            .select("id, score, limiar, compiled_hash, status, completa, total")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id))
            .eq("status", "concluida").eq("completa", True)
            # Contract §L: a run started with a cheaper-iteration
            # `modelo_geracao` override never satisfies the publish gate —
            # only a run over the version's OWN model counts.
            .is_("modelo_geracao", "null")
            .order("finished_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        return GateRun(
            id=UUID(str(row["id"])),
            score=float(row["score"]) if row.get("score") is not None else None,
            limiar=float(row["limiar"]),
            compiled_hash=row["compiled_hash"],
            status=row["status"],
            completa=bool(row.get("completa", False)),
            total=int(row.get("total") or 0),
        )


def get_eval_gate(settings: Any) -> EvalGate:
    """Real when a Supabase service-role key is configured, the in-memory
    ``FakeEvalGate`` otherwise — same signal as every other factory here."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeEvalGate()
    from app.database import get_admin_client

    return SupabaseEvalGate(get_admin_client())
