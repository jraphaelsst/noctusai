"""Chain gate: is an agent LAYER validated? (owner rule 2026-11-12, roadmap ``agent-templates-2026-11``)

"The base agent's evals are validated and the SDR does not run them; once the base is validated the whole chain
assumes it, and runs only the cases of its own scope."

Nothing new is stored. A layer's verdict is DERIVED from the consolidation state that already exists
(``eval_case_estados``, :mod:`app.studio.consolidacao`) judged against the layer's CURRENT content:

* every ACTIVE ``critico`` case of the layer's OWN suite is ``consolidado`` -- and not affected by a change since it was
  last measured. Affectedness is evaluated HERE, at read time, with the same pure rule a run applies
  (:func:`~app.studio.consolidacao.reconciliar_afetacao`); a run only persists the ``consolidado -> revalidar`` move when
  it is next booked, so reading the state row alone would call a stale layer validated.
* ``normal`` cases are REPORTED, never blocking: the publish gate already holds a layer to its judge score
  (``limiar``) and the mechanism suite's pass^k, which cover the normal cases in aggregate; per-case consolidation of a
  normal case is a cost optimisation (skip re-runs), not a safety proof. Mirroring that keeps one meaning per gate.
* a layer with NO active case is not validated (nothing was ever proved).

The "current content" of a layer is its EFFECTIVE compile (its own rows plus its own parents'), so a change to an
ancestor moves the part hashes of every descendant: the descendant's consolidated cases that depend on the changed part
(or declare no dependency -- the fail-safe) are affected and the descendant's own verdict drops until they re-consolidate.
That is the existing ``revalidar`` path (shorter streak), not a reset.

A child never runs an ancestor's cases: the run selection lists the agent's own cases only (pinned in
``tests/studio/ev/test_camada_validada.py``).

Pure core (:func:`veredicto_da_camada`) + one collector (:func:`coletar_camadas_base`) that walks the chain.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.studio.consolidacao import ConfigConsolidacao, EstadoCaso, reconciliar_afetacao

__all__ = ["VeredictoCamada", "veredicto_da_camada", "coletar_camadas_base", "base_nao_validada"]

#: cap on the case slugs a verdict names (keys only -- never case text)
_MAX_SLUGS = 25


@dataclass(frozen=True)
class VeredictoCamada:
    agent_key: str
    version_id: UUID | None  # None: the parent has no version at all
    versao: int | None
    status: str | None  # rascunho | ativa | ...
    validada: bool
    #: ``validada`` | ``sem_casos`` | ``criticos_pendentes`` | ``sem_medicao`` | ``sem_versao``
    motivo: str
    criticos_total: int
    criticos_consolidados: int
    criticos_pendentes: tuple[str, ...]  # slugs of the critical cases not (or no longer) consolidated
    normais_total: int
    normais_consolidados: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key, "version_id": str(self.version_id) if self.version_id else None, "versao": self.versao, "status": self.status,
            "validada": self.validada, "motivo": self.motivo, "criticos_total": self.criticos_total,
            "criticos_consolidados": self.criticos_consolidados, "criticos_pendentes": list(self.criticos_pendentes),
            "normais_total": self.normais_total, "normais_consolidados": self.normais_consolidados,
        }


def _consolidado_agora(
    est: EstadoCaso | None, meta: Any, cfg: ConfigConsolidacao, partes: Mapping[str, str] | None, hash_atual: str | None,
) -> bool:
    """``consolidado`` AND not affected by a change since it was last measured (read-only: nothing is persisted)."""
    if est is None or est.estado != "consolidado":
        return False
    ap = reconciliar_afetacao(
        est, criticidade=meta.criticidade, cfg=cfg, depende_de=meta.depende_de, atuais=partes, hash_atual=hash_atual)
    return ap.estado.estado == "consolidado"


def veredicto_da_camada(
    *, agent_key: str, version_id: UUID, versao: int | None, status: str | None, metas: Mapping[UUID, Any],
    estados: Mapping[UUID, EstadoCaso], cfg: ConfigConsolidacao, partes: Mapping[str, str] | None, hash_atual: str | None,
) -> VeredictoCamada:
    """Pure: the verdict of one layer from its OWN cases' metadata + consolidation states + the layer's current part hashes.

    ``partes`` / ``hash_atual`` of ``None`` (the compile is unmeasurable) can never validate: ``sem_medicao``."""
    ativos = [m for m in metas.values() if m.ativo]
    criticos = [m for m in ativos if m.criticidade == "critico"]
    normais = [m for m in ativos if m.criticidade != "critico"]
    ok_crit = [m for m in criticos if _consolidado_agora(estados.get(m.id), m, cfg, partes, hash_atual)]
    ok_norm = [m for m in normais if _consolidado_agora(estados.get(m.id), m, cfg, partes, hash_atual)]
    pendentes = tuple(sorted(m.slug or str(m.id) for m in criticos if m not in ok_crit))[:_MAX_SLUGS]
    if partes is None and hash_atual is None:
        validada, motivo = False, "sem_medicao"
    elif not ativos:
        validada, motivo = False, "sem_casos"
    elif len(ok_crit) < len(criticos):
        validada, motivo = False, "criticos_pendentes"
    else:
        validada, motivo = True, "validada"
    return VeredictoCamada(
        agent_key=agent_key, version_id=version_id, versao=versao, status=status, validada=validada, motivo=motivo,
        criticos_total=len(criticos), criticos_consolidados=len(ok_crit), criticos_pendentes=pendentes,
        normais_total=len(normais), normais_consolidados=len(ok_norm))


def coletar_camadas_base(*, store: Any, catalog: Any, consolidacao: Any, org_id: UUID, agent: Any, draft: Any) -> tuple[VeredictoCamada, ...]:
    """The verdict of every ANCESTOR of ``draft``'s version, root first (``()`` for an agent with no parent).

    Each ancestor is judged on the version the chain actually uses for ``draft`` (a child draft reads its parent's draft,
    a published child its pinned parent version), compiled with ITS OWN effective chain so the part hashes are the ones a
    run of that ancestor stamps."""
    from app.studio.bundles import compile_version
    from app.studio.camadas import efetivo

    ef = efetivo(store)
    cadeia = ef.cadeia(org_id, draft.id)[:-1]
    cfg = consolidacao.config()
    out: list[VeredictoCamada] = []
    if not cadeia and getattr(agent, "pai_agent_id", None) is not None:
        # the agent HAS a parent but the chain resolves none: the parent has neither a draft nor a published version, so
        # nothing about it was ever proved (never "no bases")
        pai = store.get_agent_by_id(agent.pai_agent_id)
        return (VeredictoCamada(pai.key, None, None, None, False, "sem_versao", 0, 0, (), 0, 0),)
    for o, vid in cadeia:
        v = store.get_version(o, vid)
        ag = store.get_agent_by_id(v.agent_id)
        c = compile_version(store, catalog, o, ag, v)
        out.append(veredicto_da_camada(
            agent_key=ag.key, version_id=v.id, versao=v.versao, status=v.status,
            metas=consolidacao.list_meta(o, ag.id), estados=consolidacao.get_estados(o, ag.id), cfg=cfg,
            partes=c.partes, hash_atual=c.hash))
    return tuple(out)


def base_nao_validada(camadas: tuple[VeredictoCamada, ...]) -> tuple[VeredictoCamada, ...]:
    """The ancestors that are NOT validated -- the one predicate the readiness item and the publish refusal share."""
    return tuple(c for c in camadas if not c.validada)
