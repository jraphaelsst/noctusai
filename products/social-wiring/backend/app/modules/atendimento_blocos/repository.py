"""Reads/writes for `atendimento_blocos` + the derived current block (maya-blocks CONTRACT §1.1 / §1.3).

Every function takes the `social_wiring`-scoped SERVICE-ROLE client (the 286 tables are RLS select-own-org +
service_role; writes go through the backend with an explicit org filter). Table names are bare -- the client
already carries its schema.

`supervisao_config` is READ here only (`supervisao`): the master switch of handoff recording and the
"not assumido within N hours" threshold. Its writes belong to the supervisao module.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from app.modules.atendimento_blocos.blocos import (
    BLOCOS,
    BLOCO_POR_NOME,
    BLOCO_SDR,
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PIPELINES_ATENDIMENTO,
    ConfigBloco,
    config_padrao,
    dono,
)

logger = logging.getLogger(__name__)

T_BLOCOS = "atendimento_blocos"
T_SUPERVISAO = "supervisao_config"
T_STAGES = "pipeline_stages"
T_ATENDIMENTOS = "atendimentos"
T_PROCESSOS = "processos_venda"

HORAS_PARA_ASSUMIR_PADRAO = 24


# ── configuration ───────────────────────────────────────────────────────────
def linhas_salvas(client: Any, org_id: UUID | str) -> dict[str, dict[str, Any]]:
    """The org's saved rows by bloco (at most 6 -- UNIQUE (org_id, bloco))."""
    rows = client.table(T_BLOCOS).select("*").eq("org_id", str(org_id)).limit(len(BLOCOS)).execute().data or []
    return {r["bloco"]: r for r in rows if r.get("bloco") in BLOCO_POR_NOME}


def _de_linha(row: dict[str, Any]) -> ConfigBloco:
    return ConfigBloco(
        bloco=row["bloco"], agent_key=row.get("agent_key"), ativo=row.get("ativo") is True,
        etapas=tuple(row.get("etapas") or ()), origem="org",
        updated_at=row.get("updated_at"), updated_by=str(row["updated_by"]) if row.get("updated_by") else None,
    )


def configuracao_efetiva(client: Any, org_id: UUID | str) -> dict[str, ConfigBloco]:
    """Every block: its saved row, else the code default (CONTRACT §1.2: a saved row replaces the default)."""
    salvas = linhas_salvas(client, org_id)
    return {b.bloco: _de_linha(salvas[b.bloco]) if b.bloco in salvas else config_padrao(b.bloco) for b in BLOCOS}


def config_do_bloco(client: Any, org_id: UUID | str, bloco: str) -> ConfigBloco:
    rows = (
        client.table(T_BLOCOS).select("*").eq("org_id", str(org_id)).eq("bloco", bloco).limit(1).execute().data or []
    )
    return _de_linha(rows[0]) if rows else config_padrao(bloco)


def gravar_linha(client: Any, org_id: UUID | str, bloco: str, *, agent_key: Optional[str], ativo: bool,
                 etapas: Iterable[str], updated_by: Optional[str]) -> None:
    """Upsert one block row. The pipeline comes from the closed list, never from a client."""
    client.table(T_BLOCOS).upsert(
        {
            "org_id": str(org_id), "bloco": bloco, "agent_key": agent_key, "ativo": bool(ativo),
            "pipeline": BLOCO_POR_NOME[bloco].pipeline, "etapas": list(etapas),
            "updated_by": str(updated_by) if updated_by else None,
        },
        on_conflict="org_id,bloco",
    ).execute()


def reduzir_etapas(client: Any, org_id: UUID | str, bloco: str, etapas: Iterable[str]) -> None:
    """Shrink a saved row's etapas (phase 1 of a save -- see `service.salvar`)."""
    client.table(T_BLOCOS).update({"etapas": list(etapas)}).eq("org_id", str(org_id)).eq("bloco", bloco).execute()


# ── supervisao (read-only here) ─────────────────────────────────────────────
def ler_supervisao(client: Any, org_id: UUID | str) -> dict[str, Any]:
    """`{supervisao_ativa, horas_para_assumir, updated_at, updated_by}`; an absent row is OFF with the default
    threshold. The ONE `supervisao_config` reader -- writes live in `app.modules.supervisao.service.salvar_config`."""
    rows = client.table(T_SUPERVISAO).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    row = rows[0] if rows else {}
    horas = row.get("horas_para_assumir")
    return {
        "supervisao_ativa": row.get("supervisao_ativa") is True,
        "horas_para_assumir": int(horas) if isinstance(horas, int) and 1 <= horas <= 168 else HORAS_PARA_ASSUMIR_PADRAO,
        "updated_at": row.get("updated_at"),
        "updated_by": row.get("updated_by"),
    }


# ── stages ──────────────────────────────────────────────────────────────────
def etapas_da_org(client: Any, org_id: UUID | str, *, incluir_inativas: bool = False) -> list[dict[str, Any]]:
    """The org's funil + processos_venda stages (a few dozen at most), ordered like the boards."""
    q = (
        client.table(T_STAGES).select("id, pipeline, slug, label, posicao, ativo").eq("org_id", str(org_id))
        .in_("pipeline", list(PIPELINES_ATENDIMENTO))
    )
    if not incluir_inativas:
        q = q.eq("ativo", True)
    rows = q.limit(1000).execute().data or []
    rows = [r for r in rows if r.get("pipeline") in PIPELINES_ATENDIMENTO]
    rows.sort(key=lambda r: (PIPELINES_ATENDIMENTO.index(r["pipeline"]), r.get("posicao") or 0, r.get("slug") or ""))
    return rows


def slug_da_etapa(client: Any, org_id: UUID | str, etapa_id: Any) -> Optional[str]:
    if not etapa_id:
        return None
    rows = (
        client.table(T_STAGES).select("id, slug").eq("org_id", str(org_id)).eq("id", str(etapa_id)).limit(1)
        .execute().data or []
    )
    return rows[0].get("slug") if rows else None


# ── the derived current block (CONTRACT §1.1) ───────────────────────────────
def card_do_lead(client: Any, org_id: UUID | str, lead_id: UUID | str) -> Optional[dict[str, Any]]:
    """The lead's live atendimento card (a folded `substituida_por` row is never the card)."""
    rows = (
        client.table(T_ATENDIMENTOS).select("id, lead_id, cliente_id, etapa_id, substituida_por")
        .eq("org_id", str(org_id)).eq("lead_id", str(lead_id)).limit(10).execute().data or []
    )
    vivos = [r for r in rows if not r.get("substituida_por")]
    return (vivos or [None])[0]


def processo_do_atendimento(client: Any, org_id: UUID | str, atendimento_id: UUID | str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_PROCESSOS).select("id, atendimento_id, etapa_id").eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def bloco_do_card(
    client: Any, org_id: UUID | str, atendimento: dict[str, Any], config: dict[str, ConfigBloco],
) -> Optional[str]:
    """processos_venda card (via the atendimento) wins over the funil card; a stage no block owns -> None."""
    processo = processo_do_atendimento(client, org_id, atendimento["id"])
    if processo is not None:
        bloco = dono(config, PIPELINE_PROCESSOS, slug_da_etapa(client, org_id, processo.get("etapa_id")))
        pipeline = PIPELINE_PROCESSOS
    else:
        bloco = dono(config, PIPELINE_FUNIL, slug_da_etapa(client, org_id, atendimento.get("etapa_id")))
        pipeline = PIPELINE_FUNIL
    if bloco is None:
        logger.info("atendimento_blocos: card %s on a %s stage no block owns (sem_bloco, org=%s)", atendimento["id"], pipeline, org_id)
    return bloco


def bloco_atual(
    client: Any, org_id: UUID | str, *, contato: Optional[dict[str, Any]] = None, lead_id: Any = None,
    config: Optional[dict[str, ConfigBloco]] = None,
) -> Optional[str]:
    """CONTRACT §1.1 -- the current block is DERIVED, never stored on the card.

    contato without lead_id -> "sdr"; a lead's processos_venda card -> its owner; else its funil card -> its owner;
    a lead with no card (spawn failed) -> None (`sem_card`, logged)."""
    lead = lead_id or (contato or {}).get("lead_id")
    if not lead:
        return BLOCO_SDR
    config = config or configuracao_efetiva(client, org_id)
    card = card_do_lead(client, org_id, lead)
    if card is None:
        logger.warning("atendimento_blocos: lead %s has no atendimento card (sem_card, org=%s)", lead, org_id)
        return None
    return bloco_do_card(client, org_id, card, config)


__all__ = [
    "HORAS_PARA_ASSUMIR_PADRAO", "T_BLOCOS", "T_SUPERVISAO", "bloco_atual", "bloco_do_card", "card_do_lead",
    "config_do_bloco", "configuracao_efetiva", "etapas_da_org", "gravar_linha", "ler_supervisao", "linhas_salvas",
    "processo_do_atendimento", "reduzir_etapas", "slug_da_etapa",
]
