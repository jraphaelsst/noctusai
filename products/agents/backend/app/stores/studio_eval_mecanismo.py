"""Store for the mechanism-eval suite (Julia v2 A-EVAL, migration 038): the active ``mecanismo`` cases of an
agent, the per-run outcomes pass^k is computed from, and the requisite the publish gate reads.

Protocol + Fake + Supabase + factory, like every seed IO seam here. Tables are service-role only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.studio.eval_mecanismo import (
    Caso,
    MecanismoGateRun,
    MecanismoRequisito,
    SuiteResultado,
)

__all__ = ["MecanismoStore", "FakeMecanismoStore", "SupabaseMecanismoStore", "get_mecanismo_store"]

_SCHEMA = "agents"


@dataclass(frozen=True)
class AgenteFlags:
    exige_mecanismo: bool = False
    comportamento_bloqueia: bool = False


class MecanismoStore(Protocol):
    def list_active_cases(self, org_id: UUID, agent_id: UUID) -> list[Caso]: ...

    def agent_flags(self, org_id: UUID, agent_id: UUID) -> AgenteFlags: ...

    def start_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, driver: str,
        limite_usd: float | None, started_by: UUID, total_casos: int,
    ) -> UUID: ...

    def finish_run(self, org_id: UUID, run_id: UUID, resultado: SuiteResultado, *, driver: str) -> None: ...

    def fail_run(self, org_id: UUID, run_id: UUID, *, erro: str) -> None: ...

    def latest_live_run(self, org_id: UUID, version_id: UUID) -> MecanismoGateRun | None: ...

    def requisito(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> MecanismoRequisito: ...

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        """Every run still ``executando`` that started before ``started_before`` becomes ``falhou`` with ``erro``
        (its runner task died with the process); frees the one-run-per-version slot. Returns how many."""
        ...

    def get_run(self, org_id: UUID, run_id: UUID) -> dict[str, Any] | None:
        """One run row (any status) as plain data, org-scoped; ``None`` when absent."""
        ...

    def list_execucoes(self, org_id: UUID, run_id: UUID) -> list[dict[str, Any]]: ...

    def latest_run(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> MecanismoGateRun | None:
        """The newest FINISHED run (any driver) of the version for exactly this compiled hash."""
        ...


def _compose(store: Any, org_id: UUID, agent_id: UUID, version_id: UUID) -> MecanismoRequisito:
    casos = store.list_active_cases(org_id, agent_id)
    flags = store.agent_flags(org_id, agent_id)
    return MecanismoRequisito(
        exigido=flags.exige_mecanismo or bool(casos),
        casos_ativos=len(casos),
        comportamento_bloqueia=flags.comportamento_bloqueia,
        run=store.latest_live_run(org_id, version_id),
    )


def _caso(row: Any) -> Caso:
    return Caso(id=row.id, slug=row.slug, k=row.k, roteiro=row.roteiro or {}, asserts=row.asserts or {})


class FakeMecanismoStore:
    """In-memory store. Wraps a ``FakeEvalStore`` for the cases so tests seed cases in one place."""

    def __init__(self, evals: Any) -> None:
        self._evals = evals
        self.flags: dict[UUID, AgenteFlags] = {}
        self.runs: dict[UUID, dict[str, Any]] = {}
        self.execucoes: dict[UUID, list[dict[str, Any]]] = {}

    def list_active_cases(self, org_id: UUID, agent_id: UUID) -> list[Caso]:
        return [
            _caso(c) for c in self._evals.list_cases(org_id, agent_id) if c.ativo and c.suite == "mecanismo"
        ]

    def agent_flags(self, org_id: UUID, agent_id: UUID) -> AgenteFlags:
        return self.flags.get(agent_id, AgenteFlags())

    def start_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, driver: str,
        limite_usd: float | None, started_by: UUID, total_casos: int,
    ) -> UUID:
        if driver not in ("live", "fake"):
            raise ValueError("driver must be 'live' or 'fake'")
        if any(r["version_id"] == version_id and r["status"] == "executando" for r in self.runs.values()):
            raise StudioConflict("run_in_progress", "a mechanism run is already executing for this version")
        rid = uuid4()
        self.runs[rid] = {
            "id": rid, "org_id": org_id, "agent_id": agent_id, "version_id": version_id,
            "compiled_hash": compiled_hash, "driver": driver, "status": "executando",
            "total_casos": total_casos, "casos_aprovados": 0, "completa": False, "aprovado": False,
            "orcamento_excedido": False, "limite_usd": limite_usd, "custo_usd": None, "erro": None,
            "started_by": started_by, "started_at": utcnow(), "finished_at": None, "seq": len(self.runs),
        }
        self.execucoes[rid] = []
        return rid

    def finish_run(self, org_id: UUID, run_id: UUID, resultado: SuiteResultado, *, driver: str) -> None:
        row = self.runs.get(run_id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"mechanism run {run_id} not found")
        for cr in resultado.casos:
            for e in cr.execucoes:
                self.execucoes[run_id].append({
                    "case_id": cr.caso.id, "indice": e.indice, "status": e.status,
                    "falhas": [f.to_dict() for f in e.falhas], "ferramentas": list(e.ferramentas),
                    "custo_usd": e.custo_usd, "duracao_ms": e.duracao_ms,
                })
        row.update(
            status="concluida", total_casos=len(resultado.casos), casos_aprovados=resultado.casos_aprovados,
            completa=resultado.completo, aprovado=resultado.aprovado,
            orcamento_excedido=resultado.orcamento_excedido, custo_usd=resultado.custo_usd,
            finished_at=utcnow(),
        )

    def fail_run(self, org_id: UUID, run_id: UUID, *, erro: str) -> None:
        row = self.runs.get(run_id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"mechanism run {run_id} not found")
        row.update(status="falhou", erro=erro, finished_at=utcnow())

    def latest_live_run(self, org_id: UUID, version_id: UUID) -> MecanismoGateRun | None:
        rows = [
            r for r in self.runs.values()
            if r["org_id"] == org_id and r["version_id"] == version_id
            and r["driver"] == "live" and r["status"] == "concluida"
        ]
        if not rows:
            return None
        r = max(rows, key=lambda x: x["seq"])
        return _gate_run(r)

    def requisito(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> MecanismoRequisito:
        return _compose(self, org_id, agent_id, version_id)

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        rows = [r for r in self.runs.values() if r["status"] == "executando" and r["started_at"] < started_before]
        for r in rows:
            r.update(status="falhou", erro=erro, finished_at=utcnow())
        return len(rows)

    def get_run(self, org_id: UUID, run_id: UUID) -> dict[str, Any] | None:
        r = self.runs.get(run_id)
        return dict(r) if r is not None and r["org_id"] == org_id else None

    def list_execucoes(self, org_id: UUID, run_id: UUID) -> list[dict[str, Any]]:
        return [dict(e) for e in self.execucoes.get(run_id, [])] if self.get_run(org_id, run_id) else []

    def latest_run(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> MecanismoGateRun | None:
        rows = [
            r for r in self.runs.values()
            if r["org_id"] == org_id and r["version_id"] == version_id and r["compiled_hash"] == compiled_hash
            and r["status"] == "concluida"
        ]
        return _gate_run(max(rows, key=lambda x: x["seq"])) if rows else None


def _gate_run(r: dict[str, Any]) -> MecanismoGateRun:
    return MecanismoGateRun(
        id=UUID(str(r["id"])), compiled_hash=r["compiled_hash"], status=r["status"], driver=r["driver"],
        completa=bool(r["completa"]), aprovado=bool(r["aprovado"]),
        orcamento_excedido=bool(r["orcamento_excedido"]), total_casos=int(r["total_casos"] or 0),
        casos_aprovados=int(r["casos_aprovados"] or 0),
    )


class SupabaseMecanismoStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def list_active_cases(self, org_id: UUID, agent_id: UUID) -> list[Caso]:
        # Bounded by construction: a mechanism suite is tens of cases; the page cap below is a tripwire,
        # not a silent truncation (more than the cap fails loud).
        resp = (
            self._t("eval_cases").select("id, slug, k, roteiro, asserts")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .eq("suite", "mecanismo").eq("ativo", True).order("created_at").limit(501).execute()
        )
        rows = resp.data or []
        if len(rows) > 500:
            raise RuntimeError("more than 500 active mecanismo cases: paginate before trusting the suite")
        return [
            Caso(id=UUID(str(r["id"])), slug=r["slug"], k=int(r["k"]), roteiro=r["roteiro"] or {}, asserts=r["asserts"] or {})
            for r in rows
        ]

    def agent_flags(self, org_id: UUID, agent_id: UUID) -> AgenteFlags:
        resp = (
            self._t("agents").select("exige_mecanismo, comportamento_bloqueia")
            .eq("org_id", str(org_id)).eq("id", str(agent_id)).limit(1).execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"agent {agent_id} not found")
        return AgenteFlags(bool(rows[0]["exige_mecanismo"]), bool(rows[0]["comportamento_bloqueia"]))

    def start_run(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, *, compiled_hash: str, driver: str,
        limite_usd: float | None, started_by: UUID, total_casos: int,
    ) -> UUID:
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "version_id": str(version_id),
            "compiled_hash": compiled_hash, "driver": driver, "status": "executando",
            "total_casos": total_casos, "limite_usd": limite_usd, "started_by": str(started_by),
        }
        resp = exec_query(self._t("eval_mecanismo_runs").insert(payload), unique_code="run_in_progress")
        rows = resp.data or []
        if not rows:
            raise RuntimeError("insert of mechanism run returned no row")
        return UUID(str(rows[0]["id"]))

    def finish_run(self, org_id: UUID, run_id: UUID, resultado: SuiteResultado, *, driver: str) -> None:
        execs = [
            {
                "org_id": str(org_id), "run_id": str(run_id), "case_id": str(cr.caso.id), "indice": e.indice,
                "status": e.status, "falhas": [f.to_dict() for f in e.falhas], "ferramentas": list(e.ferramentas),
                "custo_usd": e.custo_usd, "duracao_ms": e.duracao_ms,
            }
            for cr in resultado.casos for e in cr.execucoes
        ]
        # Chunked: a PostgREST body is bounded; a suite is small, but never assume.
        for i in range(0, len(execs), 200):
            exec_query(self._t("eval_mecanismo_execucoes").insert(execs[i : i + 200]))
        exec_query(
            self._t("eval_mecanismo_runs").update({
                "status": "concluida", "total_casos": len(resultado.casos),
                "casos_aprovados": resultado.casos_aprovados, "completa": resultado.completo,
                "aprovado": resultado.aprovado, "orcamento_excedido": resultado.orcamento_excedido,
                "custo_usd": resultado.custo_usd, "finished_at": utcnow_iso(),
            }).eq("org_id", str(org_id)).eq("id", str(run_id)).eq("status", "executando")
        )

    def fail_run(self, org_id: UUID, run_id: UUID, *, erro: str) -> None:
        exec_query(
            self._t("eval_mecanismo_runs").update({"status": "falhou", "erro": erro, "finished_at": utcnow_iso()})
            .eq("org_id", str(org_id)).eq("id", str(run_id)).eq("status", "executando")
        )

    def latest_live_run(self, org_id: UUID, version_id: UUID) -> MecanismoGateRun | None:
        resp = (
            self._t("eval_mecanismo_runs")
            .select("id, compiled_hash, status, driver, completa, aprovado, orcamento_excedido, total_casos, casos_aprovados")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id))
            .eq("driver", "live").eq("status", "concluida")
            .order("finished_at", desc=True).limit(1).execute()
        )
        rows = resp.data or []
        return _gate_run(rows[0]) if rows else None

    def requisito(self, org_id: UUID, agent_id: UUID, version_id: UUID) -> MecanismoRequisito:
        return _compose(self, org_id, agent_id, version_id)

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        resp = exec_query(
            self._t("eval_mecanismo_runs").update({"status": "falhou", "erro": erro, "finished_at": utcnow_iso()})
            .eq("status", "executando").lt("started_at", started_before.isoformat())
        )
        return len(resp.data or [])

    def get_run(self, org_id: UUID, run_id: UUID) -> dict[str, Any] | None:
        resp = (
            self._t("eval_mecanismo_runs").select("*").eq("org_id", str(org_id)).eq("id", str(run_id))
            .limit(1).execute()
        )
        rows = resp.data or []
        return dict(rows[0]) if rows else None

    def list_execucoes(self, org_id: UUID, run_id: UUID) -> list[dict[str, Any]]:
        resp = (
            self._t("eval_mecanismo_execucoes").select("*").eq("org_id", str(org_id)).eq("run_id", str(run_id))
            .order("indice").limit(1000).execute()
        )
        return [dict(r) for r in (resp.data or [])]

    def latest_run(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> MecanismoGateRun | None:
        resp = (
            self._t("eval_mecanismo_runs")
            .select("id, compiled_hash, status, driver, completa, aprovado, orcamento_excedido, total_casos, casos_aprovados")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)).eq("compiled_hash", compiled_hash)
            .eq("status", "concluida").order("finished_at", desc=True).limit(1).execute()
        )
        rows = resp.data or []
        return _gate_run(rows[0]) if rows else None


def get_mecanismo_store(settings: Any) -> MecanismoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        from app.stores.studio_evals import FakeEvalStore

        return FakeMecanismoStore(FakeEvalStore())
    from app.database import get_admin_client

    return SupabaseMecanismoStore(get_admin_client())
