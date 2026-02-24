"""
Marketing automation service — campaign stats and interest-based alerts.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_campaign_stats(campanha_id: str, supabase) -> dict:
    """
    Aggregate send stats for a campaign.
    Returns counts by status (pendente, enviado, aberto, clicado, erro).
    """
    result = supabase.table("envios_email").select("status").eq(
        "campanha_id", campanha_id
    ).execute()

    rows = result.data or []
    stats = {
        "total": len(rows),
        "pendente": 0,
        "enviado": 0,
        "aberto": 0,
        "clicado": 0,
        "erro": 0,
    }
    for row in rows:
        s = row.get("status", "pendente")
        if s in stats:
            stats[s] += 1

    return stats


def process_alerts(org_id: str, supabase) -> list[dict[str, Any]]:
    """
    Match recently-added properties against client interests.
    Returns a list of {cliente_id, cliente_nome, imovel_id, motivo} dicts.

    Logic:
    - Fetch properties created in the last 7 days with status 'ativo'
    - Fetch clients with filled 'interesse' field
    - Match by interesse keywords vs property tipo_imovel, cidade, bairro
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Recent properties
    imoveis_result = supabase.table("ativos").select(
        "id, tipo_imovel, cidade, bairro, valor, titulo_anuncio, natureza"
    ).eq("natureza", "imovel").eq("status", "ativo").gte(
        "created_at", cutoff
    ).execute()
    imoveis = imoveis_result.data or []

    if not imoveis:
        return []

    # Clients with interests
    clientes_result = supabase.table("clientes").select(
        "id, nome, email, interesse, telefone"
    ).neq("interesse", "").execute()
    clientes = clientes_result.data or []

    if not clientes:
        return []

    matches = []
    for cliente in clientes:
        interesse = (cliente.get("interesse") or "").lower()
        if not interesse:
            continue

        keywords = [k.strip() for k in interesse.replace(",", " ").split() if k.strip()]

        for imovel in imoveis:
            searchable = " ".join([
                str(imovel.get("tipo_imovel") or ""),
                str(imovel.get("cidade") or ""),
                str(imovel.get("bairro") or ""),
                str(imovel.get("titulo_anuncio") or ""),
            ]).lower()

            matched_keywords = [kw for kw in keywords if kw in searchable]
            if matched_keywords:
                matches.append({
                    "cliente_id": cliente["id"],
                    "cliente_nome": cliente.get("nome", ""),
                    "cliente_email": cliente.get("email", ""),
                    "imovel_id": imovel["id"],
                    "imovel_titulo": imovel.get("titulo_anuncio") or f"{imovel.get('tipo_imovel', '')} em {imovel.get('cidade', '')}",
                    "motivo": f"Interesse compatível: {', '.join(matched_keywords)}",
                })

    logger.info(f"Alert processing found {len(matches)} matches for org {org_id}")
    return matches
