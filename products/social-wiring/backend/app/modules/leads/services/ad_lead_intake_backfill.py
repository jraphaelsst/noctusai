"""Backfill / retry of the ad-lead intake over EXISTING Meta leads (CONTRACT ad-lead-intake § 5).

One call = one BATCH (`limite` leads, ordered by `meta_ads_leads.id`), resumable by `cursor`; the caller (the
`noctus.sw.ad_lead_intake` MCP tool, or a human) loops until `proximo_cursor` is null. DRY-RUN by default: it classifies and
counts, writes nothing, calls Vista never. A real batch fetches each distinct code ONCE (shared cache) and the per-call Vista
pacing is the shared `vista` rate-limit bucket (`ImovelSyncService.buscar_detalhe`); `pausa_s` adds a pause between leads.

`modo`: `novos` (no intake row yet, or a retryable one -- the default) | `pendentes` (only the retryable rows) | `refazer`
(everything: re-compare against Vista). A Meta row with no mapped `leads` row is reported (`sem_lead`), not created here --
`backfill_meta_ads_leads` owns that.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional
from uuid import UUID

from app.modules.leads.services import ad_lead_intake_service as intake

logger = logging.getLogger(__name__)

MODOS = ("novos", "pendentes", "refazer")
LIMITE_PADRAO = 25
LIMITE_MAX = 100


def _t(client: Any, nome: str):
    return client.table(nome)


def _lote(client: Any, org_id: UUID, cursor: Optional[str], limite: int) -> list[dict]:
    q = _t(client, "meta_ads_leads").select("id,answers,codigo_imovel").eq("org_id", str(org_id))
    if cursor:
        q = q.gt("id", cursor)
    return list(q.order("id").limit(limite).execute().data or [])


def _lead_por_meta(client: Any, org_id: UUID, meta_ids: list[str]) -> dict[str, dict]:
    if not meta_ids:
        return {}
    rows = _t(client, "leads").select("id,meta_lead_id,codigo_imovel,imovel_ref_id").eq("org_id", str(org_id)).in_("meta_lead_id", meta_ids).execute().data or []
    return {str(r["meta_lead_id"]): r for r in rows}


def _intakes(client: Any, org_id: UUID, lead_ids: list[str]) -> dict[str, dict]:
    if not lead_ids:
        return {}
    rows = _t(client, intake.T_INTAKES).select("lead_id,status").eq("org_id", str(org_id)).in_("lead_id", lead_ids).execute().data or []
    return {str(r["lead_id"]): r for r in rows}


def backfill_intake(
    client: Any,
    org_id: UUID,
    *,
    dry_run: bool = True,
    limite: int = LIMITE_PADRAO,
    cursor: Optional[str] = None,
    modo: str = "novos",
    pausa_s: float = 0.0,
    adapter_factory: Any = None,
    sync_factory: Any = None,
) -> dict[str, Any]:
    if modo not in MODOS:
        raise ValueError(f"modo must be one of {MODOS}, got {modo!r}")
    limite = max(1, min(int(limite), LIMITE_MAX))
    rows = _lote(client, org_id, cursor, limite)
    leads = _lead_por_meta(client, org_id, [str(r["id"]) for r in rows])
    feitos = _intakes(client, org_id, [str(v["id"]) for v in leads.values()])
    relatorio: dict[str, Any] = {
        "dry_run": dry_run, "modo": modo, "lote": len(rows), "sem_lead": 0, "ja_feitos": 0, "a_processar": 0,
        "processados": 0, "por_status": {}, "falhas": [], "codigos_distintos": 0,
        "proximo_cursor": str(rows[-1]["id"]) if len(rows) == limite else None,
    }
    alvo: list[tuple[dict, dict]] = []
    for meta in rows:
        lead = leads.get(str(meta["id"]))
        if lead is None:
            relatorio["sem_lead"] += 1
            continue
        atual = (feitos.get(str(lead["id"])) or {}).get("status")
        repetivel = atual is None or atual in intake.ST_REPETIVEIS
        if modo == "pendentes":
            repetivel = atual in intake.ST_REPETIVEIS
        if modo != "refazer" and not repetivel:
            relatorio["ja_feitos"] += 1
            continue
        alvo.append((meta, lead))
    relatorio["a_processar"] = len(alvo)
    relatorio["codigos_distintos"] = len({(lead.get("codigo_imovel") or "").strip().upper() for _, lead in alvo} - {""})
    if dry_run:
        return relatorio

    cache: dict[str, Any] = {}
    for i, (meta, lead) in enumerate(alvo):
        try:
            res = intake.intake_imovel_do_lead(
                client, org_id, lead["id"], refresh_cache=cache, adapter_factory=adapter_factory, sync_factory=sync_factory
            )
        except Exception as exc:  # one bad lead never stops the batch; it is named in the report
            logger.error("ad-lead intake backfill: lead=%s failed", lead["id"], exc_info=True)
            relatorio["falhas"].append({"lead_id": str(lead["id"]), "meta_lead_id": str(meta["id"]), "erro": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        relatorio["processados"] += 1
        relatorio["por_status"][res["status"]] = relatorio["por_status"].get(res["status"], 0) + 1
        if pausa_s and i < len(alvo) - 1:
            time.sleep(pausa_s)
    logger.info("ad-lead intake backfill org=%s: %s", org_id, {k: v for k, v in relatorio.items() if k != "falhas"})
    return relatorio


def resumo(client: Any, org_id: UUID) -> dict[str, Any]:
    """Counts of `lead_imovel_intakes` by status + the pending corretor divergences (the dashboard of the intake)."""
    from app.services import table_reads

    intakes = table_reads.paged_rows(client, intake.T_INTAKES, org_id, select="id,status")
    divs = table_reads.paged_rows(client, intake.T_DIVERGENCIAS, org_id, select="id,status")
    por_status: dict[str, int] = {}
    for r in intakes:
        por_status[r["status"]] = por_status.get(r["status"], 0) + 1
    return {
        "intakes": por_status, "total": len(intakes),
        "divergencias_corretor_pendentes": sum(1 for d in divs if d["status"] == "pendente"),
    }


__all__ = ["backfill_intake", "resumo", "MODOS", "LIMITE_PADRAO", "LIMITE_MAX"]
