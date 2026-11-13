"""Eval-loop store (migration 076): the loop (planned rounds, target, floor, budget, status, stop reason) and its rounds.

``Fake`` + ``Supabase`` + factory (seed rule). Service-role only (Platform IP, ``agents.eval_*``); the API in front is
platform-admin / evals-token only. Every query is org-scoped. Spend is never tracked here independently: a round's
``custo_usd`` is the run's own recorded cost, copied when the round closes (see ``app.studio.eval_loop_service``).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.studio.eval_loop import LoopDef, Parada, Rodada
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

__all__ = ["LoopRecord", "LoopStore", "FakeLoopStore", "SupabaseLoopStore", "get_loop_store"]

_SCHEMA = "agents"
RUN_TABLES = {"comportamento": "eval_runs", "mecanismo": "eval_mecanismo_runs"}


@dataclass(frozen=True)
class LoopRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    agente_chave: str
    suite: str
    rodadas_planejadas: int
    alvo: float
    piso: float
    orcamento_usd: float
    gasto_usd: float
    status: str
    motivo_parada: str | None
    detalhe_parada: dict[str, Any] | None
    started_by: UUID
    started_at: datetime | None
    stopped_at: datetime | None

    def definicao(self) -> LoopDef:
        return LoopDef(
            id=self.id, suite=self.suite, rodadas_planejadas=self.rodadas_planejadas, alvo=self.alvo, piso=self.piso,
            orcamento_usd=self.orcamento_usd, gasto_usd=self.gasto_usd, status=self.status, motivo_parada=self.motivo_parada)


class LoopStore(Protocol):
    def create_loop(
        self, org_id: UUID, agent_id: UUID, *, agente_chave: str, suite: str, rodadas_planejadas: int, alvo: float,
        piso: float, orcamento_usd: float, started_by: UUID,
    ) -> LoopRecord:
        """Raises :class:`StudioConflict` ``loop_ativo_existente`` when the (agent, suite) already has an active loop."""
        ...

    def get_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID) -> LoopRecord:
        """Raises :class:`NotFound`."""
        ...

    def list_loops(self, org_id: UUID, agent_id: UUID, *, status: str | None = None, suite: str | None = None) -> list[LoopRecord]: ...

    def list_rodadas(self, org_id: UUID, loop_id: UUID) -> list[Rodada]: ...

    def loops_ativos_do_usuario(self, started_by: UUID) -> list[LoopRecord]:
        """Every ACTIVE loop the user opened, across agents, suites and orgs (the one-loop-per-user rule)."""
        ...

    def registrar_recusa(
        self, *, org_id: UUID, started_by: UUID, codigo: str, agent_id: UUID | None, suite: str | None, loop_id: UUID | None,
        em_andamento_run: tuple[UUID, str] | None, em_andamento_loop: UUID | None,
    ) -> None:
        """Append one ``eval_recusas_eventos`` row: a start refused by the one-run-per-user rule."""
        ...

    def rodada_do_run(self, org_id: UUID, run_id: UUID, run_tipo: str) -> tuple[LoopRecord, Rodada] | None:
        """The loop + round a run belongs to; ``None`` = the run was started without a loop."""
        ...

    def abrir_rodada(
        self, org_id: UUID, loop_id: UUID, *, run_id: UUID, run_tipo: str, compiled_hash: str, partes: dict[str, str] | None,
    ) -> Rodada:
        """Book the next round (``seq`` = rounds + 1) for a run and mirror ``loop_id`` on the run row. Raises
        :class:`StudioConflict` ``rodada_em_andamento`` when a round of the loop is already open or the loop is not active."""
        ...

    def fechar_rodada(
        self, org_id: UUID, loop_id: UUID, run_id: UUID, run_tipo: str, *, status: str, score: float | None, custo_usd: float,
        falhas: list[str], melhorou: bool | None, overcall: bool, gasto_usd: float, parada: Parada | None,
    ) -> bool:
        """Close the round and (atomically with it, in that order) add its cost to the loop and apply the stop. Idempotent:
        ``False`` = the round was not open any more (another closer won); nothing is written twice."""
        ...

    def parar_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID, *, motivo: str, status: str, detalhe: dict[str, Any] | None) -> bool:
        """Stop an ACTIVE loop. ``False`` = it was not active."""
        ...


def _num(v: Any) -> float:
    return float(v) if v is not None else 0.0


def _loop_de(r: dict[str, Any]) -> LoopRecord:
    return LoopRecord(
        id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), agent_id=UUID(str(r["agent_id"])), agente_chave=r["agente_chave"],
        suite=r["suite"], rodadas_planejadas=int(r["rodadas_planejadas"]), alvo=_num(r["alvo"]), piso=_num(r["piso"]),
        orcamento_usd=_num(r["orcamento_usd"]), gasto_usd=_num(r["gasto_usd"]), status=r["status"],
        motivo_parada=r.get("motivo_parada"), detalhe_parada=r.get("detalhe_parada"), started_by=UUID(str(r["started_by"])),
        started_at=r.get("started_at"), stopped_at=r.get("stopped_at"))


def _rodada_de(r: dict[str, Any]) -> Rodada:
    return Rodada(
        seq=int(r["seq"]), run_id=UUID(str(r["run_id"])), run_tipo=r["run_tipo"], compiled_hash=r["compiled_hash"],
        status=r["status"], score=None if r.get("score") is None else float(r["score"]), custo_usd=_num(r.get("custo_usd")),
        falhas=tuple(r.get("falhas") or ()), melhorou=r.get("melhorou"), overcall=bool(r.get("overcall")),
        partes=r.get("partes"))


class FakeLoopStore:
    """In-memory store. ``runs`` (``(run_tipo, run_id) -> loop_id``) mirrors the ``loop_id`` column on the run tables."""

    def __init__(self) -> None:
        self.loops: dict[UUID, LoopRecord] = {}
        self.rodadas: dict[UUID, list[Rodada]] = {}
        self.runs: dict[tuple[str, UUID], UUID] = {}
        self.recusas: list[dict[str, Any]] = []

    def loops_ativos_do_usuario(self, started_by: UUID) -> list[LoopRecord]:
        return [l for l in self.loops.values() if l.started_by == started_by and l.status == "ativo"]

    def registrar_recusa(
        self, *, org_id: UUID, started_by: UUID, codigo: str, agent_id: UUID | None, suite: str | None, loop_id: UUID | None,
        em_andamento_run: tuple[UUID, str] | None, em_andamento_loop: UUID | None,
    ) -> None:
        self.recusas.append({
            "org_id": org_id, "started_by": started_by, "codigo": codigo, "agent_id": agent_id, "suite": suite, "loop_id": loop_id,
            "em_andamento_run": em_andamento_run, "em_andamento_loop": em_andamento_loop, "occurred_at": utcnow()})

    def create_loop(
        self, org_id: UUID, agent_id: UUID, *, agente_chave: str, suite: str, rodadas_planejadas: int, alvo: float,
        piso: float, orcamento_usd: float, started_by: UUID,
    ) -> LoopRecord:
        if self.loops_ativos_do_usuario(started_by):  # mirror of migration 087's guard_eval_um_por_usuario
            raise StudioConflict("loop_ativo_do_usuario", "O usuário já tem um loop ativo.")
        if any(l.agent_id == agent_id and l.suite == suite and l.status == "ativo" for l in self.loops.values()):
            raise StudioConflict("loop_ativo_existente", "O agente já tem um loop ativo nesta suíte.")
        rec = LoopRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, agente_chave=agente_chave, suite=suite,
            rodadas_planejadas=rodadas_planejadas, alvo=alvo, piso=piso, orcamento_usd=orcamento_usd, gasto_usd=0.0,
            status="ativo", motivo_parada=None, detalhe_parada=None, started_by=started_by, started_at=utcnow(), stopped_at=None)
        self.loops[rec.id] = rec
        self.rodadas[rec.id] = []
        return rec

    def get_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID) -> LoopRecord:
        rec = self.loops.get(loop_id)
        if rec is None or rec.org_id != org_id or rec.agent_id != agent_id:
            raise NotFound(f"loop {loop_id} not found")
        return rec

    def list_loops(self, org_id: UUID, agent_id: UUID, *, status: str | None = None, suite: str | None = None) -> list[LoopRecord]:
        rows = [l for l in self.loops.values() if l.org_id == org_id and l.agent_id == agent_id
                and (status is None or l.status == status) and (suite is None or l.suite == suite)]
        return sorted(rows, key=lambda l: l.started_at or utcnow(), reverse=True)

    def list_rodadas(self, org_id: UUID, loop_id: UUID) -> list[Rodada]:
        rec = self.loops.get(loop_id)
        return list(self.rodadas.get(loop_id, [])) if rec is not None and rec.org_id == org_id else []

    def rodada_do_run(self, org_id: UUID, run_id: UUID, run_tipo: str) -> tuple[LoopRecord, Rodada] | None:
        for lid, rs in self.rodadas.items():
            for r in rs:
                if r.run_id == run_id and r.run_tipo == run_tipo and self.loops[lid].org_id == org_id:
                    return self.loops[lid], r
        return None

    def abrir_rodada(
        self, org_id: UUID, loop_id: UUID, *, run_id: UUID, run_tipo: str, compiled_hash: str, partes: dict[str, str] | None,
    ) -> Rodada:
        rec = self.loops.get(loop_id)
        if rec is None or rec.org_id != org_id:
            raise NotFound(f"loop {loop_id} not found")
        rs = self.rodadas[loop_id]
        if rec.status != "ativo":
            raise StudioConflict("loop_encerrado", "O loop foi encerrado.")
        if any(r.aberta for r in rs):
            raise StudioConflict("rodada_em_andamento", "Já há uma rodada deste loop em andamento.")
        r = Rodada(seq=len(rs) + 1, run_id=run_id, run_tipo=run_tipo, compiled_hash=compiled_hash, partes=partes)
        rs.append(r)
        self.runs[(run_tipo, run_id)] = loop_id
        return r

    def fechar_rodada(
        self, org_id: UUID, loop_id: UUID, run_id: UUID, run_tipo: str, *, status: str, score: float | None, custo_usd: float,
        falhas: list[str], melhorou: bool | None, overcall: bool, gasto_usd: float, parada: Parada | None,
    ) -> bool:
        rs = self.rodadas.get(loop_id, [])
        for i, r in enumerate(rs):
            if r.run_id == run_id and r.run_tipo == run_tipo and r.aberta:
                rs[i] = replace(r, status=status, score=score, custo_usd=custo_usd, falhas=tuple(falhas),
                                melhorou=melhorou, overcall=overcall)
                rec = self.loops[loop_id]
                upd: dict[str, Any] = {"gasto_usd": gasto_usd}
                if parada is not None and rec.status == "ativo":
                    upd.update(status=parada.status, motivo_parada=parada.motivo, detalhe_parada=dict(parada.detalhe),
                               stopped_at=utcnow())
                self.loops[loop_id] = replace(rec, **upd)
                return True
        return False

    def parar_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID, *, motivo: str, status: str, detalhe: dict[str, Any] | None) -> bool:
        rec = self.get_loop(org_id, agent_id, loop_id)
        if rec.status != "ativo":
            return False
        self.loops[loop_id] = replace(rec, status=status, motivo_parada=motivo, detalhe_parada=detalhe, stopped_at=utcnow())
        return True


class SupabaseLoopStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def create_loop(
        self, org_id: UUID, agent_id: UUID, *, agente_chave: str, suite: str, rodadas_planejadas: int, alvo: float,
        piso: float, orcamento_usd: float, started_by: UUID,
    ) -> LoopRecord:
        row = {
            "org_id": str(org_id), "agent_id": str(agent_id), "agente_chave": agente_chave, "suite": suite,
            "rodadas_planejadas": rodadas_planejadas, "alvo": alvo, "piso": piso, "orcamento_usd": orcamento_usd,
            "started_by": str(started_by),
        }
        data = exec_query(self._t("eval_loops").insert(row), unique_code="loop_ativo_existente").data or []
        return _loop_de(data[0])

    def loops_ativos_do_usuario(self, started_by: UUID) -> list[LoopRecord]:
        rows = exec_query(self._t("eval_loops").select("*").eq("started_by", str(started_by)).eq("status", "ativo")
                          .order("started_at", desc=True).limit(50)).data or []
        return [_loop_de(r) for r in rows]

    def registrar_recusa(
        self, *, org_id: UUID, started_by: UUID, codigo: str, agent_id: UUID | None, suite: str | None, loop_id: UUID | None,
        em_andamento_run: tuple[UUID, str] | None, em_andamento_loop: UUID | None,
    ) -> None:
        exec_query(self._t("eval_recusas_eventos").insert({
            "org_id": str(org_id), "started_by": str(started_by), "codigo": codigo,
            "agent_id": None if agent_id is None else str(agent_id), "suite": suite,
            "loop_id": None if loop_id is None else str(loop_id),
            "em_andamento_run_id": None if em_andamento_run is None else str(em_andamento_run[0]),
            "em_andamento_run_tipo": None if em_andamento_run is None else em_andamento_run[1],
            "em_andamento_loop_id": None if em_andamento_loop is None else str(em_andamento_loop)}))

    def get_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID) -> LoopRecord:
        rows = exec_query(self._t("eval_loops").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
                          .eq("id", str(loop_id)).limit(1)).data or []
        if not rows:
            raise NotFound(f"loop {loop_id} not found")
        return _loop_de(rows[0])

    def list_loops(self, org_id: UUID, agent_id: UUID, *, status: str | None = None, suite: str | None = None) -> list[LoopRecord]:
        def fetch(start: int, end: int):
            q = self._t("eval_loops").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            if status:
                q = q.eq("status", status)
            if suite:
                q = q.eq("suite", suite)
            return q.order("started_at", desc=True).order("id").range(start, end).execute().data

        return [_loop_de(r) for r in iter_paged_rows(fetch, label="eval_loops")]

    def list_rodadas(self, org_id: UUID, loop_id: UUID) -> list[Rodada]:
        def fetch(start: int, end: int):
            return (self._t("eval_loop_rodadas").select("*").eq("org_id", str(org_id)).eq("loop_id", str(loop_id))
                    .order("seq").range(start, end).execute().data)

        return [_rodada_de(r) for r in iter_paged_rows(fetch, label="eval_loop_rodadas", id_key="seq")]

    def rodada_do_run(self, org_id: UUID, run_id: UUID, run_tipo: str) -> tuple[LoopRecord, Rodada] | None:
        rows = exec_query(self._t("eval_loop_rodadas").select("*").eq("org_id", str(org_id)).eq("run_id", str(run_id))
                          .eq("run_tipo", run_tipo).limit(1)).data or []
        if not rows:
            return None
        lrows = exec_query(self._t("eval_loops").select("*").eq("org_id", str(org_id)).eq("id", rows[0]["loop_id"]).limit(1)).data or []
        return (_loop_de(lrows[0]), _rodada_de(rows[0])) if lrows else None

    def abrir_rodada(
        self, org_id: UUID, loop_id: UUID, *, run_id: UUID, run_tipo: str, compiled_hash: str, partes: dict[str, str] | None,
    ) -> Rodada:
        lrows = exec_query(self._t("eval_loops").select("status").eq("org_id", str(org_id)).eq("id", str(loop_id)).limit(1)).data or []
        if not lrows:
            raise NotFound(f"loop {loop_id} not found")
        if lrows[0]["status"] != "ativo":
            raise StudioConflict("loop_encerrado", "O loop foi encerrado.")
        atuais = self.list_rodadas(org_id, loop_id)
        if any(r.aberta for r in atuais):
            raise StudioConflict("rodada_em_andamento", "Já há uma rodada deste loop em andamento.")
        row = {
            "org_id": str(org_id), "loop_id": str(loop_id), "seq": len(atuais) + 1, "run_id": str(run_id), "run_tipo": run_tipo,
            "compiled_hash": compiled_hash, "partes": partes,
        }
        # UNIQUE (loop_id, seq): two starts racing for the same seq -> the loser is a conflict, never a duplicate round
        data = exec_query(self._t("eval_loop_rodadas").insert(row), unique_code="rodada_em_andamento").data or []
        exec_query(self._t(RUN_TABLES[run_tipo]).update({"loop_id": str(loop_id)}).eq("org_id", str(org_id)).eq("id", str(run_id)))
        return _rodada_de(data[0])

    def fechar_rodada(
        self, org_id: UUID, loop_id: UUID, run_id: UUID, run_tipo: str, *, status: str, score: float | None, custo_usd: float,
        falhas: list[str], melhorou: bool | None, overcall: bool, gasto_usd: float, parada: Parada | None,
    ) -> bool:
        # the conditional UPDATE is the idempotency: only the closer that finds the round still `executando` proceeds
        done = exec_query(
            self._t("eval_loop_rodadas").update({
                "status": status, "score": score, "custo_usd": custo_usd, "falhas": falhas, "melhorou": melhorou,
                "overcall": overcall, "finished_at": utcnow_iso(),
            }).eq("org_id", str(org_id)).eq("loop_id", str(loop_id)).eq("run_id", str(run_id)).eq("run_tipo", run_tipo)
            .eq("status", "executando")).data or []
        if not done:
            return False
        patch: dict[str, Any] = {"gasto_usd": gasto_usd}
        if parada is not None:
            patch.update(status=parada.status, motivo_parada=parada.motivo, detalhe_parada=dict(parada.detalhe),
                         stopped_at=utcnow_iso())
            exec_query(self._t("eval_loops").update(patch).eq("org_id", str(org_id)).eq("id", str(loop_id)).eq("status", "ativo"))
        else:
            exec_query(self._t("eval_loops").update(patch).eq("org_id", str(org_id)).eq("id", str(loop_id)))
        return True

    def parar_loop(self, org_id: UUID, agent_id: UUID, loop_id: UUID, *, motivo: str, status: str, detalhe: dict[str, Any] | None) -> bool:
        done = exec_query(
            self._t("eval_loops").update({"status": status, "motivo_parada": motivo, "detalhe_parada": detalhe, "stopped_at": utcnow_iso()})
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(loop_id)).eq("status", "ativo")).data or []
        return bool(done)


def get_loop_store(settings: Any) -> LoopStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeLoopStore()
    from app.database import get_admin_client

    return SupabaseLoopStore(get_admin_client())
