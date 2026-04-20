"""
Metas Configuração Service — per-org scoring configuration.

One row per org. Holds:
  - vgv_por_ponto — R$ per 1 bonus point (default 10_000)
  - peso_pontos / peso_vgv — weights in the unified score
  - metrica_ranking_padrao — 'pontos' | 'vgv' | 'unificado'

Unified score formula (computed client-side from these fields):
  score_unificado = pontos_atividade * peso_pontos
                  + (vgv / vgv_por_ponto) * peso_vgv

See products/erp-imobiliario/METAS-PLAN.md §5.4.
"""
from __future__ import annotations

from typing import Any

DEFAULT_CONFIG = {
    "vgv_por_ponto": 10000,
    "peso_pontos": 1.0,
    "peso_vgv": 1.0,
    "metrica_ranking_padrao": "unificado",
}

VALID_RANKINGS = {"pontos", "vgv", "unificado"}


def obter_configuracao(db, org_id: str) -> dict:
    """Return the org's config, or a default shape if none saved yet."""
    result = db.table("metas_configuracao").select("*").eq("org_id", org_id).limit(1).execute()
    if result.data:
        return result.data[0]
    # Virtual default — UI can show it; not persisted until owner saves
    return {"org_id": org_id, **DEFAULT_CONFIG}


def upsert_configuracao(db, *, org_id: str, vgv_por_ponto: float | None = None,
                        peso_pontos: float | None = None,
                        peso_vgv: float | None = None,
                        metrica_ranking_padrao: str | None = None) -> dict:
    """Upsert the scoring config for an org. Validates ranges + enum values."""
    if vgv_por_ponto is not None and vgv_por_ponto <= 0:
        raise ValueError("vgv_por_ponto deve ser > 0")
    if peso_pontos is not None and peso_pontos < 0:
        raise ValueError("peso_pontos deve ser >= 0")
    if peso_vgv is not None and peso_vgv < 0:
        raise ValueError("peso_vgv deve ser >= 0")
    if metrica_ranking_padrao is not None and metrica_ranking_padrao not in VALID_RANKINGS:
        raise ValueError(f"metrica_ranking_padrao inválida: {metrica_ranking_padrao}")

    payload: dict[str, Any] = {"org_id": org_id}
    if vgv_por_ponto is not None:
        payload["vgv_por_ponto"] = vgv_por_ponto
    if peso_pontos is not None:
        payload["peso_pontos"] = peso_pontos
    if peso_vgv is not None:
        payload["peso_vgv"] = peso_vgv
    if metrica_ranking_padrao is not None:
        payload["metrica_ranking_padrao"] = metrica_ranking_padrao

    result = db.table("metas_configuracao").upsert(payload, on_conflict="org_id").execute()
    if not result.data:
        raise RuntimeError("Falha ao salvar configuração de metas")
    return result.data[0]
