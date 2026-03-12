"""
Relatorios Service — Business logic for advanced reporting.

Provides agent ranking, funnel conversion, monthly activity aggregation,
and CSV export utilities.
"""
import csv
import io
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ordered funnel stages
ETAPAS_FUNIL = ["qualificacao", "visitas", "proposta", "negociacao", "fechado"]

ETAPAS_LABELS = {
    "qualificacao": "Qualificação",
    "visitas": "Visitas",
    "proposta": "Proposta",
    "negociacao": "Negociação",
    "fechado": "Fechado",
}


def ranking_corretores(
    org_id: str,
    supabase,
    periodo_dias: int = 30,
) -> List[Dict[str, Any]]:
    """
    Aggregate agent (corretor) performance for a given period.

    Returns a list of agents sorted by total sales value descending.
    Each entry includes:
      - profile info
      - total clients
      - clients fechados (won deals)
      - total estimated value of closed deals
      - total activities logged
    """
    # Fetch all agents (profiles) for the org via RLS
    profiles_res = supabase.table("profiles").select("id, nome, email").execute()
    profiles = {p["id"]: p for p in (profiles_res.data or [])}

    if not profiles:
        return []

    # Date cutoff for the reporting period
    cutoff = (date.today() - timedelta(days=periodo_dias)).isoformat()

    # Fetch clients created within the period, selecting only needed columns
    clientes_res = supabase.table("clientes").select(
        "usuario_id, etapa_atual, valor_estimado"
    ).gte("created_at", cutoff).execute()
    clientes = clientes_res.data or []

    # Fetch activities within the period, selecting only needed columns
    atividades_res = supabase.table("atividades").select(
        "usuario_id"
    ).gte("created_at", cutoff).execute()
    atividades = atividades_res.data or []

    # Aggregate per agent
    ranking: Dict[str, Dict[str, Any]] = {}
    for uid, prof in profiles.items():
        ranking[uid] = {
            "usuario_id": uid,
            "nome": prof.get("nome", ""),
            "email": prof.get("email", ""),
            "total_clientes": 0,
            "clientes_fechados": 0,
            "valor_total_fechados": 0.0,
            "total_atividades": 0,
        }

    for c in clientes:
        uid = c.get("usuario_id")
        if uid not in ranking:
            continue
        ranking[uid]["total_clientes"] += 1
        if c.get("etapa_atual") == "fechado":
            ranking[uid]["clientes_fechados"] += 1
            ranking[uid]["valor_total_fechados"] += float(c.get("valor_estimado") or 0)

    for a in atividades:
        uid = a.get("usuario_id")
        if uid in ranking:
            ranking[uid]["total_atividades"] += 1

    # Sort by closed deal value desc, then by closed count desc
    result = sorted(
        ranking.values(),
        key=lambda x: (x["valor_total_fechados"], x["clientes_fechados"]),
        reverse=True,
    )
    return result


def conversao_funil(
    org_id: str,
    supabase,
) -> List[Dict[str, Any]]:
    """
    Calculate conversion rates between funnel stages.

    Returns a list with one entry per stage including count and
    conversion rate to the next stage.
    """
    clientes_res = supabase.table("clientes").select(
        "id, etapa_atual"
    ).eq("arquivado", False).execute()
    clientes = clientes_res.data or []

    # Count per stage
    counts: Dict[str, int] = defaultdict(int)
    for c in clientes:
        etapa = c.get("etapa_atual", "qualificacao")
        counts[etapa] += 1

    result = []
    for i, etapa in enumerate(ETAPAS_FUNIL):
        count = counts.get(etapa, 0)
        # Conversion rate = next_stage_count / current_stage_count * 100
        if i < len(ETAPAS_FUNIL) - 1:
            next_count = counts.get(ETAPAS_FUNIL[i + 1], 0)
            taxa = round((next_count / count * 100), 1) if count > 0 else 0.0
        else:
            taxa = None  # last stage has no "next"

        result.append({
            "etapa": etapa,
            "label": ETAPAS_LABELS.get(etapa, etapa),
            "total": count,
            "taxa_conversao": taxa,
        })

    return result


def atividade_mensal(
    org_id: str,
    supabase,
    meses: int = 6,
) -> List[Dict[str, Any]]:
    """
    Monthly activity aggregation for the last N months.

    Returns one entry per month with:
      - month label
      - total activities
      - new clients
      - closed deals count
    """
    today = date.today()

    # Date cutoff: go back enough days to cover the requested months
    cutoff = (today - timedelta(days=meses * 31)).isoformat()

    # Fetch atividades within the period, selecting only needed columns
    atividades_res = supabase.table("atividades").select(
        "created_at"
    ).gte("created_at", cutoff).execute()
    atividades = atividades_res.data or []

    # Fetch clients within the period, selecting only needed columns
    clientes_res = supabase.table("clientes").select(
        "etapa_atual, created_at"
    ).gte("created_at", cutoff).execute()
    clientes = clientes_res.data or []

    # Build month buckets
    months = []
    for i in range(meses - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    result = []
    for y, m in months:
        prefix = f"{y}-{m:02d}"
        label = f"{m:02d}/{y}"

        ativ_count = sum(
            1 for a in atividades
            if str(a.get("created_at", ""))[:7] == prefix
        )
        novos_clientes = sum(
            1 for c in clientes
            if str(c.get("created_at", ""))[:7] == prefix
        )
        fechados = sum(
            1 for c in clientes
            if str(c.get("created_at", ""))[:7] == prefix
            and c.get("etapa_atual") == "fechado"
        )

        result.append({
            "mes": label,
            "periodo": prefix,
            "total_atividades": ativ_count,
            "novos_clientes": novos_clientes,
            "fechados": fechados,
        })

    return result


def generate_csv(data: List[Dict[str, Any]], headers: Optional[List[str]] = None) -> str:
    """
    Generate a CSV string from a list of dicts.

    If headers are not provided, the keys of the first dict are used.
    """
    if not data:
        return ""

    if headers is None:
        headers = list(data[0].keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    return output.getvalue()
