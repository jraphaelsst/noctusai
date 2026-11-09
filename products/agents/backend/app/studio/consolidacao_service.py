"""Eval consolidation orchestration: pick the cases a run needs, record what a run proved, replay history (owner rule 2026-11-09).

The pure rules live in :mod:`app.studio.consolidacao`; this module reads/writes them through the
:class:`~app.stores.studio_eval_consolidacao.ConsolidacaoStore`. Both suites share it:

* **select** (:func:`selecionar`): a default run executes only the cases that are NOT ``consolidado``-and-unaffected;
  ``rodar_tudo`` runs everything. The skipped cases + why are persisted against the run (``eval_casos_pulados``).
* **record** (:func:`registrar_resultados`): after a run, each case's results move its state and every move is an
  append-only row in ``eval_case_transicoes`` (run id, part hashes, reason).
* **backfill** (:func:`reconstruir`): replay finished runs oldest-first per case. DRY-RUN unless ``aplicar``.

Not counted as evidence: a cheaper-iteration judge run (``modelo_geracao`` set -- another model answered) and a ``fake``-driver
mechanism run. An ``erro`` execution is neutral (nothing was measured about the agent).
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.stores.studio_eval_consolidacao import CasoMeta, ConsolidacaoStore
from app.studio.consolidacao import (
    Aplicacao, ConfigConsolidacao, EstadoCaso, Transicao, aplicar_resultado, decidir_selecao, estado_inicial,
    inferir_depende_de, resultado_de_status, resumir_estados, sugerir_criticidade,
)

logger = logging.getLogger(__name__)

__all__ = ["Selecao", "selecionar", "confirmar_selecao", "registrar_resultados", "reconstruir", "RelatorioBackfill"]


@dataclass
class Selecao:
    rodar: list[UUID]
    pulados: list[dict[str, Any]] = field(default_factory=list)
    a_persistir: list[tuple[CasoMeta, Aplicacao]] = field(default_factory=list)
    rodar_tudo: bool = False

    @property
    def algo_pulado(self) -> bool:
        return bool(self.pulados)


def selecionar(
    store: ConsolidacaoStore, *, org_id: UUID, agent_id: UUID, suite: str, ativos: Sequence[UUID],
    partes: Mapping[str, str] | None, hash_atual: str | None, rodar_tudo: bool,
) -> Selecao:
    """Which of the ``ativos`` (active case ids of ``suite``) a run must execute. Never raises on missing state: no state = ``em_validacao``."""
    if rodar_tudo:
        return Selecao(rodar=list(ativos), rodar_tudo=True)
    cfg = store.config()
    meta = store.list_meta(org_id, agent_id, suite)
    estados = store.get_estados(org_id, agent_id)
    sel = Selecao(rodar=[])
    for cid in ativos:
        m = meta.get(cid) or CasoMeta(id=cid, suite=suite)
        rodar, ap = decidir_selecao(
            estados.get(cid), criticidade=m.criticidade, cfg=cfg, depende_de=m.depende_de, atuais=partes, hash_atual=hash_atual)
        if rodar:
            sel.rodar.append(cid)
            if ap is not None:
                sel.a_persistir.append((m, ap))
        else:
            est = estados[cid]
            sel.pulados.append({"case_id": cid, "estado": est.estado, "motivo": "consolidado_nao_afetado",
                                "sequencia": est.sequencia, "limite": est.limite})
    return sel


def confirmar_selecao(
    store: ConsolidacaoStore, sel: Selecao, *, org_id: UUID, agent_id: UUID, suite: str, run_id: UUID, run_tipo: str,
    partes: Mapping[str, str] | None, hash_atual: str | None,
) -> None:
    """Persist a booked run's selection: the part hashes it was started with, the skipped cases and the
    ``consolidado -> revalidar`` moves of the cases a change affected."""
    store.set_run_partes(org_id, run_id, run_tipo, dict(partes) if partes is not None else None, rodar_tudo=sel.rodar_tudo)
    for m, ap in sel.a_persistir:
        store.save_estado(org_id, agent_id, suite, _com_run(ap.estado, run_id), run_tipo=run_tipo)
        store.append_transicoes(
            org_id, agent_id, case_id=m.id, suite=suite, criticidade=m.criticidade, run_id=run_id, run_tipo=run_tipo,
            partes=dict(partes) if partes is not None else None, compiled_hash=hash_atual,
            transicoes=list(ap.transicoes), origem="selecao")
    if sel.pulados:
        store.registrar_pulados(org_id, agent_id, run_id, run_tipo, sel.pulados)


def _com_run(est: EstadoCaso, run_id: UUID) -> EstadoCaso:
    return EstadoCaso(est.case_id, est.estado, est.sequencia, est.limite, est.partes_referencia, est.hash_referencia, run_id)


def registrar_resultados(
    store: ConsolidacaoStore, *, org_id: UUID, agent_id: UUID, suite: str, run_id: UUID, run_tipo: str,
    hash_atual: str | None, partes: Mapping[str, str] | None, resultados: Iterable[tuple[UUID, Sequence[str]]],
) -> dict[str, int]:
    """Fold a finished run's per-case statuses (``aprovado``/``reprovado``/``erro``/...; several for a mechanism case, in
    execution order) into the case states. Returns ``{case_id_count, transicoes}`` for logging."""
    cfg = store.config()
    meta = store.list_meta(org_id, agent_id, suite)
    estados = store.get_estados(org_id, agent_id)
    n_casos = n_trans = 0
    for cid, statuses in resultados:
        m = meta.get(cid) or CasoMeta(id=cid, suite=suite)
        est = estados.get(cid) or estado_inicial(cid, m.criticidade, cfg)
        trans: list[Transicao] = []
        for status in statuses:
            ap = aplicar_resultado(
                est, resultado_de_status(status), criticidade=m.criticidade, cfg=cfg, atuais=partes, hash_atual=hash_atual,
                run_id=run_id, depende_de=m.depende_de, sem_partes="conservadora")
            est = ap.estado
            trans.extend(ap.transicoes)
        store.save_estado(org_id, agent_id, suite, est, run_tipo=run_tipo)
        if trans:
            store.append_transicoes(
                org_id, agent_id, case_id=cid, suite=suite, criticidade=m.criticidade, run_id=run_id, run_tipo=run_tipo,
                partes=dict(partes) if partes is not None else None, compiled_hash=hash_atual, transicoes=trans)
        n_casos += 1
        n_trans += len(trans)
    return {"casos": n_casos, "transicoes": n_trans}


# ── historical backfill ───────────────────────────────────────────────────────────────────────────────────────


@dataclass
class RelatorioBackfill:
    aplicado: bool
    politica_sem_partes: str
    usou_deps_propostas: bool
    runs_comportamento: int = 0
    runs_mecanismo: int = 0
    runs_com_partes: int = 0
    runs_sem_partes: int = 0
    casos_total: int = 0
    casos_ja_rastreados: int = 0
    estados: dict[str, int] = field(default_factory=dict)
    estados_por_suite: dict[str, dict[str, int]] = field(default_factory=dict)
    estados_por_criticidade: dict[str, dict[str, int]] = field(default_factory=dict)
    transicoes: int = 0
    criticidade_proposta: dict[str, int] = field(default_factory=dict)
    criticidade_proposta_casos: list[dict[str, str]] = field(default_factory=list)
    deps_inferidas: int = 0
    deps_sem_inferencia: list[str] = field(default_factory=list)
    casos_por_estado: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def reconstruir(
    store: ConsolidacaoStore, *, org_id: UUID, agent_id: UUID, partes_conhecidas: Iterable[str] = (),
    recomputar_partes: Callable[[UUID, str], dict[str, str] | None] | None = None,
    politica_sem_partes: str = "dono", usar_deps_propostas: bool = False, aplicar: bool = False,
    propor_criticidade: bool = True,
) -> RelatorioBackfill:
    """Replay ``eval_results`` / live ``eval_mecanismo_execucoes`` history oldest-first per case into current states.

    Per-part hashes of an old run: the run's stored ``partes`` when present, else ``recomputar_partes(version_id,
    compiled_hash)`` (the version recompiled; accepted ONLY when its hash equals the run's stamped one), else unknown. Where
    unknown, ``politica_sem_partes`` decides what a bare ``compiled_hash`` change means: ``"dono"`` (owner's rule) affects only
    a case with NO declared dependency; ``"conservadora"`` affects every case. Cases that already have a state row (tracked
    live) are left alone. DRY-RUN unless ``aplicar`` (then writes states, ``backfill`` transitions, criticality proposals and
    -- with ``usar_deps_propostas`` -- the inferred dependencies)."""
    cfg = store.config()
    meta = store.list_meta(org_id, agent_id)
    existentes = store.get_estados(org_id, agent_id)
    ja = set(existentes)
    rel = RelatorioBackfill(aplicado=aplicar, politica_sem_partes=politica_sem_partes, usou_deps_propostas=usar_deps_propostas)

    # criticality + dependency PROPOSALS (never silently authoritative: origem 'sugerida' / 'inferida')
    deps_prop: dict[UUID, tuple[str, ...]] = {}
    crit: dict[UUID, str] = {}
    for m in meta.values():
        if not m.ativo:
            continue
        c = m.criticidade
        if propor_criticidade and m.criticidade_origem == "padrao":
            c = sugerir_criticidade(m.tags)
            if c == "critico":
                rel.criticidade_proposta_casos.append({"slug": m.slug, "suite": m.suite})
        crit[m.id] = c
        if m.depende_de is None:
            deps, _ = inferir_depende_de(tags=m.tags, asserts=m.asserts, texto_caso=m.texto, partes_conhecidas=partes_conhecidas)
            if deps:
                deps_prop[m.id] = tuple(deps)
                rel.deps_inferidas += 1
            else:
                rel.deps_sem_inferencia.append(f"{m.suite}:{m.slug}")
    rel.criticidade_proposta = {k: sum(1 for v in crit.values() if v == k) for k in ("normal", "critico")}

    # events, oldest first
    runs: list[tuple[Any, str, dict[str, Any]]] = [
        (r["ts"], "comportamento", r) for r in store.historico_comportamento(org_id, agent_id)
    ] + [(r["ts"], "mecanismo", r) for r in store.historico_mecanismo(org_id, agent_id)]
    runs.sort(key=lambda x: (str(x[0]), x[1], str(x[2]["run_id"])))
    rel.runs_comportamento = sum(1 for _, t, _ in runs if t == "comportamento")
    rel.runs_mecanismo = sum(1 for _, t, _ in runs if t == "mecanismo")

    cache: dict[tuple[UUID, str], dict[str, str] | None] = {}
    estados: dict[UUID, EstadoCaso] = {}
    trans_por_caso: dict[UUID, list[tuple[UUID, str, dict[str, str] | None, str, list[Transicao]]]] = {}

    def _partes(r: dict[str, Any]) -> dict[str, str] | None:
        if r.get("partes"):
            return dict(r["partes"])
        if recomputar_partes is None:
            return None
        k = (r["version_id"], r["compiled_hash"])
        if k not in cache:
            cache[k] = recomputar_partes(*k)
        return cache[k]

    for _, tipo, r in runs:
        partes = _partes(r)
        rel.runs_com_partes += partes is not None
        rel.runs_sem_partes += partes is None
        itens = r["resultados"].items() if tipo == "comportamento" else r["execucoes"].items()
        for cid, val in itens:
            if cid in ja or cid not in meta:
                continue
            m = meta[cid]
            deps = m.depende_de if m.depende_de is not None else (deps_prop.get(cid) if usar_deps_propostas else None)
            est = estados.get(cid) or estado_inicial(cid, crit.get(cid, m.criticidade), cfg)
            statuses = [val] if tipo == "comportamento" else list(val)
            trans: list[Transicao] = []
            for st in statuses:
                ap = aplicar_resultado(
                    est, resultado_de_status(st), criticidade=crit.get(cid, m.criticidade), cfg=cfg, atuais=partes,
                    hash_atual=r["compiled_hash"], run_id=r["run_id"], depende_de=deps, sem_partes=politica_sem_partes)
                est = ap.estado
                trans.extend(ap.transicoes)
            estados[cid] = est
            if trans:
                trans_por_caso.setdefault(cid, []).append((r["run_id"], tipo, partes, r["compiled_hash"], trans))

    rel.casos_ja_rastreados = len(ja)
    ativos = [m for m in meta.values() if m.ativo]
    rel.casos_total = len(ativos)
    for m in ativos:
        e = estados.get(m.id) or existentes.get(m.id)
        ec = e.estado if e is not None else "em_validacao"
        rel.estados[ec] = rel.estados.get(ec, 0) + 1
        rel.estados_por_suite.setdefault(m.suite, {})[ec] = rel.estados_por_suite.get(m.suite, {}).get(ec, 0) + 1
        rel.estados_por_criticidade.setdefault(crit.get(m.id, m.criticidade), {})[ec] = (
            rel.estados_por_criticidade.get(crit.get(m.id, m.criticidade), {}).get(ec, 0) + 1)
        rel.casos_por_estado.setdefault(ec, []).append(f"{m.suite}:{m.slug}")
    rel.transicoes = sum(len(t) for ls in trans_por_caso.values() for *_, t in ls)

    if aplicar:
        for cid, est in estados.items():
            m = meta[cid]
            store.save_estado(org_id, agent_id, m.suite, est, run_tipo=None)
            for run_id, tipo, partes, h, trans in trans_por_caso.get(cid, []):
                store.append_transicoes(
                    org_id, agent_id, case_id=cid, suite=m.suite, criticidade=crit.get(cid, m.criticidade), run_id=run_id,
                    run_tipo=tipo, partes=partes, compiled_hash=h, transicoes=trans, origem="backfill")
        for cid, c in crit.items():
            if propor_criticidade and meta[cid].criticidade_origem == "padrao" and c == "critico":
                store.set_caso(org_id, agent_id, cid, criticidade=c, criticidade_origem="sugerida")
        if usar_deps_propostas:
            for cid, deps in deps_prop.items():
                store.set_caso(org_id, agent_id, cid, depende_de=list(deps), depende_de_origem="inferida")
    return rel
