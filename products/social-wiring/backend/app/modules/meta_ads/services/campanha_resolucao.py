"""Which campanha does a Meta lead belong to? (CONTRACT sw-lead-to-contract §1.2)

A Meta lead carries the ids of the ad objects that produced it. An operator
registers those ids on a campanha (``campanha_veiculacoes``, ``canal='meta_ads'``,
``nivel`` says WHICH object ``ref_codigo`` names) and attaches the imóveis it
advertises (``campanha_imoveis``). Resolution is the MOST SPECIFIC hit first:

    ad_id → adset_id → campaign_id → form_id

The first level that points at a LIVE campanha (``deleted_at IS NULL``) with at
least one imóvel wins. No hit returns ``None`` — the caller falls back to the
form's ``REF`` answer, then to ``imovel_pendente``. Never a guess: an id that
matches nothing, or a campanha that has no imóveis, is "no hit", not "pick one".

Reads only. ``client`` is the ``social_wiring``-scoped client (the one
``ingest_meta_lead`` already holds).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

#: ``(nivel, meta_lead key)`` in resolution order — the contract's §1.2 list.
NIVEIS_EM_ORDEM: tuple[tuple[str, str], ...] = (
    ("ad", "ad_id"),
    ("adset", "adset_id"),
    ("campaign", "campaign_id"),
    ("form", "form_id"),
)

CANAL = "meta_ads"


def _t(client: Any, name: str):
    return client.table(name)


def _campanha_viva(client: Any, org_id: UUID, campanha_id: str) -> Optional[dict]:
    rows = (
        _t(client, "campanhas")
        .select("id,nome,deleted_at")
        .eq("org_id", str(org_id))
        .eq("id", str(campanha_id))
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _codigos_da_campanha(client: Any, org_id: UUID, campanha_id: str) -> list[str]:
    """The campanha's imóvel códigos (canonical), in a stable order."""
    ligacoes = (
        _t(client, "campanha_imoveis")
        .select("imovel_ref_id")
        .eq("org_id", str(org_id))
        .eq("campanha_id", str(campanha_id))
        .execute()
    ).data or []
    ref_ids = [str(r["imovel_ref_id"]) for r in ligacoes if r.get("imovel_ref_id")]
    if not ref_ids:
        return []
    registro = (
        _t(client, "imovel_registry")
        .select("id,codigo_canonical")
        .eq("org_id", str(org_id))
        .in_("id", ref_ids)
        .execute()
    ).data or []
    return sorted({str(r["codigo_canonical"]) for r in registro if r.get("codigo_canonical")})


def resolver_campanha(
    client: Any, org_id: UUID, meta_lead: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """``{campanha_id, nome, nivel, ref_codigo, codigos}`` or ``None``."""
    for nivel, chave in NIVEIS_EM_ORDEM:
        ref = meta_lead.get(chave)
        ref = str(ref).strip() if ref is not None else ""
        if not ref:
            continue
        veiculacoes = (
            _t(client, "campanha_veiculacoes")
            .select("campanha_id")
            .eq("org_id", str(org_id))
            .eq("canal", CANAL)
            .eq("nivel", nivel)
            .eq("ref_codigo", ref)
            .execute()
        ).data or []
        for v in veiculacoes:
            campanha = _campanha_viva(client, org_id, v["campanha_id"])
            if campanha is None:
                continue
            codigos = _codigos_da_campanha(client, org_id, campanha["id"])
            if not codigos:
                continue
            return {
                "campanha_id": str(campanha["id"]),
                "nome": campanha.get("nome"),
                "nivel": nivel,
                "ref_codigo": ref,
                "codigos": codigos,
            }
    return None


__all__ = ["NIVEIS_EM_ORDEM", "resolver_campanha"]
