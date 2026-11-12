"""Eval-case consolidation store (migration 072): thresholds, per-case state, the append-only transition history, the
"skipped because consolidated" ledger, the per-part hashes of a run, and the historical-run readers the backfill replays.

``Fake`` + ``Supabase`` + factory (seed rule). Service-role only (Platform IP, ``agents.eval_*``); the API in front is
platform-admin only. Every query is org-scoped.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.studio.consolidacao import DEFAULT_CONFIG, ConfigConsolidacao, EstadoCaso, Transicao
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

__all__ = [
    "CasoMeta", "ConsolidacaoStore", "FakeConsolidacaoStore", "SupabaseConsolidacaoStore", "get_consolidacao_store",
    "RUN_TIPOS",
]

_SCHEMA = "agents"
RUN_TIPOS = ("comportamento", "mecanismo")
_UNSET: Any = object()


@dataclass(frozen=True)
class CasoMeta:
    id: UUID
    slug: str = ""
    suite: str = "comportamento"
    ativo: bool = True
    tags: tuple[str, ...] = ()
    asserts: dict[str, Any] | None = None
    texto: str = ""  # entrada + critérios + rubrica (what the dependency heuristic reads)
    criticidade: str = "normal"
    criticidade_origem: str = "padrao"
    depende_de: tuple[str, ...] | None = None
    depende_de_origem: str | None = None


class ConsolidacaoStore(Protocol):
    def config(self) -> ConfigConsolidacao: ...
    def list_meta(self, org_id: UUID, agent_id: UUID, suite: str | None = None) -> dict[UUID, CasoMeta]: ...
    def get_estados(self, org_id: UUID, agent_id: UUID) -> dict[UUID, EstadoCaso]: ...
    def get_estado(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EstadoCaso | None: ...
    def save_estado(
        self, org_id: UUID, agent_id: UUID, suite: str, est: EstadoCaso, *, run_tipo: str | None, esperado_versao: int,
    ) -> bool:
        """Compare-and-swap: write ``est`` only if the stored row is still at ``esperado_versao`` (0 = no row yet). ``False`` =
        a parallel run moved it first; the caller re-reads and re-applies. Never a blind overwrite."""
        ...
    def marcar_run_completa(self, org_id: UUID, run_id: UUID, run_tipo: str) -> None: ...
    def append_transicoes(
        self, org_id: UUID, agent_id: UUID, *, case_id: UUID, suite: str, criticidade: str, run_id: UUID | None,
        run_tipo: str | None, partes: dict[str, str] | None, compiled_hash: str | None, transicoes: list[Transicao],
        origem: str = "run",
    ) -> None: ...
    def list_transicoes(self, org_id: UUID, agent_id: UUID, case_id: UUID | None = None, limit: int = 200) -> list[dict[str, Any]]: ...
    def registrar_pulados(self, org_id: UUID, agent_id: UUID, run_id: UUID, run_tipo: str, rows: list[dict[str, Any]]) -> None: ...
    def list_pulados(self, org_id: UUID, run_id: UUID, run_tipo: str) -> list[dict[str, Any]]: ...
    def set_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str, partes: dict[str, str] | None, *, rodar_tudo: bool) -> None: ...
    def get_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str) -> dict[str, str] | None: ...
    def set_caso(
        self, org_id: UUID, agent_id: UUID, case_id: UUID, *, criticidade: str | None = None,
        criticidade_origem: str | None = None, depende_de: Any = _UNSET, depende_de_origem: str | None = None,
    ) -> None: ...
    def historico_comportamento(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        """Finished judge runs of the version's own model, oldest first: ``{run_id, ts, compiled_hash, version_id, partes,
        resultados: {case_id: status}}``."""
        ...
    def historico_mecanismo(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        """Finished LIVE mechanism runs, oldest first: ``{run_id, ts, compiled_hash, version_id, partes,
        execucoes: {case_id: [status by indice]}}``."""
        ...


def _estado_de(row: dict[str, Any]) -> EstadoCaso:
    return EstadoCaso(
        case_id=UUID(str(row["case_id"])), estado=row["estado"], sequencia=int(row["sequencia"]), limite=int(row["limite"]),
        partes_referencia=row.get("partes_referencia"), hash_referencia=row.get("hash_referencia"),
        ultimo_run_id=UUID(str(row["ultimo_run_id"])) if row.get("ultimo_run_id") else None,
        versao=int(row.get("versao") or 1),
    )


def _transicao_row(
    org_id: UUID, agent_id: UUID, *, case_id: UUID, suite: str, criticidade: str, run_id: UUID | None,
    run_tipo: str | None, partes: dict[str, str] | None, compiled_hash: str | None, t: Transicao, origem: str,
) -> dict[str, Any]:
    return {
        "org_id": str(org_id), "agent_id": str(agent_id), "case_id": str(case_id), "suite": suite,
        "de_estado": t.de_estado, "para_estado": t.para_estado, "motivo": t.motivo,
        "run_id": str(run_id) if run_id else None, "run_tipo": run_tipo, "criticidade": criticidade,
        "sequencia_antes": t.sequencia_antes, "sequencia_depois": t.sequencia_depois, "limite": t.limite,
        "partes": partes, "partes_afetadas": list(t.partes_afetadas) or None, "compiled_hash": compiled_hash,
        "origem": origem, "detalhe": t.detalhe,
    }


class FakeConsolidacaoStore:
    def __init__(self, evals: Any = None) -> None:
        self._evals = evals
        self.cfg = ConfigConsolidacao(dict(DEFAULT_CONFIG))
        self.meta: dict[UUID, CasoMeta] = {}
        self.estados: dict[UUID, EstadoCaso] = {}
        self.estado_suite: dict[UUID, str] = {}
        self.transicoes: list[dict[str, Any]] = []
        self.pulados: list[dict[str, Any]] = []
        self.completas: list[tuple[str, UUID]] = []
        self.run_partes: dict[tuple[str, UUID], tuple[dict[str, str] | None, bool]] = {}
        self.hist_comportamento: list[dict[str, Any]] = []
        self.hist_mecanismo: list[dict[str, Any]] = []

    def config(self) -> ConfigConsolidacao:
        return self.cfg

    def list_meta(self, org_id: UUID, agent_id: UUID, suite: str | None = None) -> dict[UUID, CasoMeta]:
        out: dict[UUID, CasoMeta] = {}
        if self._evals is not None:
            for c in self._evals.list_cases(org_id, agent_id):
                m = self.meta.get(c.id)
                out[c.id] = CasoMeta(
                    id=c.id, slug=c.slug, suite=c.suite, ativo=c.ativo, tags=tuple(c.tags), asserts=c.asserts,
                    texto=" ".join([c.entrada, str(c.criterios), c.rubrica or ""]),
                    **({} if m is None else {
                        "criticidade": m.criticidade, "criticidade_origem": m.criticidade_origem,
                        "depende_de": m.depende_de, "depende_de_origem": m.depende_de_origem}),
                )
        if self._evals is None:  # without an eval store the meta rows ARE the cases; with one, other agents' rows are not ours
            for cid, m in self.meta.items():
                out.setdefault(cid, m)
        return {k: v for k, v in out.items() if suite is None or v.suite == suite}

    def get_estados(self, org_id: UUID, agent_id: UUID) -> dict[UUID, EstadoCaso]:
        return dict(self.estados)

    def get_estado(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EstadoCaso | None:
        return self.estados.get(case_id)

    def save_estado(
        self, org_id: UUID, agent_id: UUID, suite: str, est: EstadoCaso, *, run_tipo: str | None, esperado_versao: int,
    ) -> bool:
        atual = self.estados.get(est.case_id)
        if (atual.versao if atual else 0) != esperado_versao:
            return False
        self.estados[est.case_id] = replace(est, versao=esperado_versao + 1)
        self.estado_suite[est.case_id] = suite
        return True

    def marcar_run_completa(self, org_id: UUID, run_id: UUID, run_tipo: str) -> None:
        if self._evals is not None and run_tipo == "comportamento" and run_id in self._evals._runs:
            self._evals._runs[run_id]["completa"] = True
        self.completas.append((run_tipo, run_id))

    def append_transicoes(
        self, org_id: UUID, agent_id: UUID, *, case_id: UUID, suite: str, criticidade: str, run_id: UUID | None,
        run_tipo: str | None, partes: dict[str, str] | None, compiled_hash: str | None, transicoes: list[Transicao],
        origem: str = "run",
    ) -> None:
        for t in transicoes:
            self.transicoes.append({**_transicao_row(
                org_id, agent_id, case_id=case_id, suite=suite, criticidade=criticidade, run_id=run_id, run_tipo=run_tipo,
                partes=partes, compiled_hash=compiled_hash, t=t, origem=origem), "id": uuid4(), "created_at": utcnow()})

    def list_transicoes(self, org_id: UUID, agent_id: UUID, case_id: UUID | None = None, limit: int = 200) -> list[dict[str, Any]]:
        rows = [r for r in self.transicoes if str(r["agent_id"]) == str(agent_id) and (case_id is None or str(r["case_id"]) == str(case_id))]
        return list(reversed(rows))[:limit]

    def registrar_pulados(self, org_id: UUID, agent_id: UUID, run_id: UUID, run_tipo: str, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            self.pulados.append({**r, "run_id": run_id, "run_tipo": run_tipo, "agent_id": agent_id, "org_id": org_id})

    def list_pulados(self, org_id: UUID, run_id: UUID, run_tipo: str) -> list[dict[str, Any]]:
        return [r for r in self.pulados if r["run_id"] == run_id and r["run_tipo"] == run_tipo]

    def set_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str, partes: dict[str, str] | None, *, rodar_tudo: bool) -> None:
        self.run_partes[(run_tipo, run_id)] = (partes, rodar_tudo)

    def get_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str) -> dict[str, str] | None:
        return self.run_partes.get((run_tipo, run_id), (None, False))[0]

    def set_caso(self, org_id: UUID, agent_id: UUID, case_id: UUID, *, criticidade: str | None = None,
                 criticidade_origem: str | None = None, depende_de: Any = _UNSET, depende_de_origem: str | None = None) -> None:
        atual = self.meta.get(case_id) or CasoMeta(id=case_id)
        kw: dict[str, Any] = {}
        if criticidade is not None:
            kw.update(criticidade=criticidade, criticidade_origem=criticidade_origem or "definida")
        if depende_de is not _UNSET:
            kw.update(depende_de=None if depende_de is None else tuple(depende_de), depende_de_origem=depende_de_origem)
        self.meta[case_id] = replace(atual, **kw)

    def historico_comportamento(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        return list(self.hist_comportamento)

    def historico_mecanismo(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        return list(self.hist_mecanismo)


class SupabaseConsolidacaoStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def _paged(self, build, *, label: str, order: tuple[tuple[str, bool], ...], id_key: str = "id") -> list[dict[str, Any]]:
        def fetch(start: int, end: int):
            q = build()
            for col, desc in order:
                q = q.order(col, desc=desc)
            return q.order(id_key).range(start, end).execute().data

        return list(iter_paged_rows(fetch, label=label, id_key=id_key))

    def config(self) -> ConfigConsolidacao:
        rows = exec_query(self._t("eval_consolidacao_config").select("chave, valor")).data or []
        return ConfigConsolidacao({r["chave"]: int(r["valor"]) for r in rows})  # raises on a missing key: never a silent default

    def list_meta(self, org_id: UUID, agent_id: UUID, suite: str | None = None) -> dict[UUID, CasoMeta]:
        def build():
            q = (self._t("eval_cases")
                 .select("id, slug, suite, ativo, tags, asserts, entrada, criterios, rubrica, criticidade, criticidade_origem, depende_de, depende_de_origem")
                 .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)))
            return q.eq("suite", suite) if suite else q

        out: dict[UUID, CasoMeta] = {}
        for r in self._paged(build, label="eval_cases.consolidacao", order=(("created_at", False), ("id", False))):
            dep = r.get("depende_de")
            out[UUID(str(r["id"]))] = CasoMeta(
                id=UUID(str(r["id"])), slug=r["slug"], suite=r["suite"], ativo=bool(r["ativo"]), tags=tuple(r.get("tags") or ()),
                asserts=r.get("asserts"), texto=" ".join([r.get("entrada") or "", str(r.get("criterios") or ""), r.get("rubrica") or ""]),
                criticidade=r["criticidade"], criticidade_origem=r["criticidade_origem"],
                depende_de=None if dep is None else tuple(dep), depende_de_origem=r.get("depende_de_origem"),
            )
        return out

    def get_estados(self, org_id: UUID, agent_id: UUID) -> dict[UUID, EstadoCaso]:
        rows = self._paged(
            lambda: self._t("eval_case_estado").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label="eval_case_estado", order=(("case_id", False),), id_key="case_id")
        return {UUID(str(r["case_id"])): _estado_de(r) for r in rows}

    def get_estado(self, org_id: UUID, agent_id: UUID, case_id: UUID) -> EstadoCaso | None:
        rows = exec_query(self._t("eval_case_estado").select("*").eq("org_id", str(org_id)).eq("case_id", str(case_id)).limit(1)).data or []
        return _estado_de(rows[0]) if rows else None

    def save_estado(
        self, org_id: UUID, agent_id: UUID, suite: str, est: EstadoCaso, *, run_tipo: str | None, esperado_versao: int,
    ) -> bool:
        row = {
            "org_id": str(org_id), "agent_id": str(agent_id), "suite": suite,
            "estado": est.estado, "sequencia": est.sequencia, "limite": est.limite,
            "partes_referencia": dict(est.partes_referencia) if est.partes_referencia is not None else None,
            "hash_referencia": est.hash_referencia, "ultimo_run_id": str(est.ultimo_run_id) if est.ultimo_run_id else None,
            "ultimo_run_tipo": run_tipo, "versao": esperado_versao + 1,
        }
        if esperado_versao == 0:
            try:  # PK(case_id): a parallel run inserted first -> unique violation -> not saved
                exec_query(self._t("eval_case_estado").insert({**row, "case_id": str(est.case_id)}), unique_code="estado_concorrente")
            except StudioConflict:
                return False
            return True
        done = exec_query(
            self._t("eval_case_estado").update(row).eq("case_id", str(est.case_id)).eq("versao", esperado_versao)
        ).data or []
        return bool(done)

    def marcar_run_completa(self, org_id: UUID, run_id: UUID, run_tipo: str) -> None:
        exec_query(self._t(self._run_table(run_tipo)).update({"completa": True}).eq("org_id", str(org_id)).eq("id", str(run_id)))

    def append_transicoes(
        self, org_id: UUID, agent_id: UUID, *, case_id: UUID, suite: str, criticidade: str, run_id: UUID | None,
        run_tipo: str | None, partes: dict[str, str] | None, compiled_hash: str | None, transicoes: list[Transicao],
        origem: str = "run",
    ) -> None:
        rows = [_transicao_row(org_id, agent_id, case_id=case_id, suite=suite, criticidade=criticidade, run_id=run_id,
                               run_tipo=run_tipo, partes=partes, compiled_hash=compiled_hash, t=t, origem=origem)
                for t in transicoes]
        for i in range(0, len(rows), 200):
            exec_query(self._t("eval_case_transicoes").insert(rows[i : i + 200]))

    def list_transicoes(self, org_id: UUID, agent_id: UUID, case_id: UUID | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = (self._t("eval_case_transicoes").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id)))
        if case_id is not None:
            q = q.eq("case_id", str(case_id))
        return exec_query(q.order("created_at", desc=True).limit(limit)).data or []

    def registrar_pulados(self, org_id: UUID, agent_id: UUID, run_id: UUID, run_tipo: str, rows: list[dict[str, Any]]) -> None:
        payload = [{
            "org_id": str(org_id), "agent_id": str(agent_id), "run_id": str(run_id), "run_tipo": run_tipo,
            "case_id": str(r["case_id"]), "estado": r["estado"], "motivo": r["motivo"],
            "sequencia": r.get("sequencia", 0), "limite": r.get("limite", 1),
        } for r in rows]
        for i in range(0, len(payload), 200):
            exec_query(self._t("eval_casos_pulados").upsert(payload[i : i + 200], on_conflict="run_id,run_tipo,case_id"))

    def list_pulados(self, org_id: UUID, run_id: UUID, run_tipo: str) -> list[dict[str, Any]]:
        return exec_query(
            self._t("eval_casos_pulados").select("case_id, estado, motivo, sequencia, limite")
            .eq("org_id", str(org_id)).eq("run_id", str(run_id)).eq("run_tipo", run_tipo)).data or []

    def _run_table(self, run_tipo: str) -> str:
        if run_tipo not in RUN_TIPOS:
            raise ValueError(f"run_tipo inválido: {run_tipo!r}")
        return "eval_runs" if run_tipo == "comportamento" else "eval_mecanismo_runs"

    def set_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str, partes: dict[str, str] | None, *, rodar_tudo: bool) -> None:
        exec_query(self._t(self._run_table(run_tipo)).update({"partes": partes, "rodar_tudo": rodar_tudo})
                   .eq("org_id", str(org_id)).eq("id", str(run_id)))

    def get_run_partes(self, org_id: UUID, run_id: UUID, run_tipo: str) -> dict[str, str] | None:
        rows = exec_query(self._t(self._run_table(run_tipo)).select("partes").eq("org_id", str(org_id)).eq("id", str(run_id)).limit(1)).data or []
        if not rows:
            raise NotFound(f"run {run_id} not found")
        return rows[0].get("partes")

    def set_caso(self, org_id: UUID, agent_id: UUID, case_id: UUID, *, criticidade: str | None = None,
                 criticidade_origem: str | None = None, depende_de: Any = _UNSET, depende_de_origem: str | None = None) -> None:
        patch: dict[str, Any] = {}
        if criticidade is not None:
            patch.update(criticidade=criticidade, criticidade_origem=criticidade_origem or "definida")
        if depende_de is not _UNSET:
            patch.update(depende_de=None if depende_de is None else list(depende_de), depende_de_origem=depende_de_origem)
        if not patch:
            return
        rows = exec_query(self._t("eval_cases").update(patch).eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
                          .eq("id", str(case_id))).data or []
        if not rows:
            raise NotFound(f"case {case_id} not found")

    def historico_comportamento(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        runs = self._paged(
            lambda: (self._t("eval_runs").select("id, compiled_hash, version_id, partes, finished_at")
                     .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("status", "concluida")
                     .is_("modelo_geracao", "null")),
            label="eval_runs.historico", order=(("finished_at", False), ("id", False)))
        out = []
        for r in runs:
            res = self._paged(
                lambda r=r: self._t("eval_results").select("id, case_id, status").eq("run_id", r["id"]),
                label="eval_results.historico", order=(("case_id", False),))
            out.append({"run_id": UUID(str(r["id"])), "ts": r["finished_at"], "compiled_hash": r["compiled_hash"],
                        "version_id": UUID(str(r["version_id"])), "partes": r.get("partes"),
                        "resultados": {UUID(str(x["case_id"])): x["status"] for x in res}})
        return out

    def historico_mecanismo(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        runs = self._paged(
            lambda: (self._t("eval_mecanismo_runs").select("id, compiled_hash, version_id, partes, finished_at")
                     .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("status", "concluida").eq("driver", "live")),
            label="eval_mecanismo_runs.historico", order=(("finished_at", False), ("id", False)))
        out = []
        for r in runs:
            ex = self._paged(
                lambda r=r: self._t("eval_mecanismo_execucoes").select("id, case_id, indice, status").eq("run_id", r["id"]),
                label="eval_mecanismo_execucoes.historico", order=(("case_id", False), ("indice", False)))
            por_caso: dict[UUID, list[str]] = {}
            for x in ex:
                por_caso.setdefault(UUID(str(x["case_id"])), []).append(x["status"])
            out.append({"run_id": UUID(str(r["id"])), "ts": r["finished_at"], "compiled_hash": r["compiled_hash"],
                        "version_id": UUID(str(r["version_id"])), "partes": r.get("partes"), "execucoes": por_caso})
        return out


def get_consolidacao_store(settings: Any, evals: Any = None) -> ConsolidacaoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeConsolidacaoStore(evals)
    from app.database import get_admin_client

    return SupabaseConsolidacaoStore(get_admin_client())
