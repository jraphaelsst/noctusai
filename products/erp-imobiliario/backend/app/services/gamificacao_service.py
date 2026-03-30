"""
Gamification service — point rules, badge logic, and leaderboard helpers.
"""
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Sao Paulo timezone offset (UTC-3)
SP_OFFSET = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Point rules: action -> points
# ---------------------------------------------------------------------------
PONTOS_POR_ACAO = {
    "novo_cliente": 10,
    "visita_realizada": 15,
    "proposta_enviada": 20,
    "venda_fechada": 100,
    "meta_cumprida": 50,
}

# ---------------------------------------------------------------------------
# Badge definitions
# ---------------------------------------------------------------------------
BADGES = [
    {
        "tipo": "primeiro_passo",
        "nome": "Primeiro Passo",
        "descricao": "Cadastrou o primeiro cliente",
        "icone": "footprints",
        "condicao": lambda stats: stats.get("total_clientes", 0) >= 1,
    },
    {
        "tipo": "corretor_bronze",
        "nome": "Corretor Bronze",
        "descricao": "Acumulou 100 pontos",
        "icone": "medal",
        "condicao": lambda stats: stats.get("total_pontos", 0) >= 100,
    },
    {
        "tipo": "corretor_prata",
        "nome": "Corretor Prata",
        "descricao": "Acumulou 500 pontos",
        "icone": "medal",
        "condicao": lambda stats: stats.get("total_pontos", 0) >= 500,
    },
    {
        "tipo": "corretor_ouro",
        "nome": "Corretor Ouro",
        "descricao": "Acumulou 1000 pontos",
        "icone": "trophy",
        "condicao": lambda stats: stats.get("total_pontos", 0) >= 1000,
    },
    {
        "tipo": "maratonista",
        "nome": "Maratonista",
        "descricao": "Realizou 10 visitas em uma semana",
        "icone": "running",
        "condicao": lambda stats: stats.get("visitas_semana", 0) >= 10,
    },
    {
        "tipo": "fechador",
        "nome": "Fechador",
        "descricao": "Fechou 5 vendas no total",
        "icone": "handshake",
        "condicao": lambda stats: stats.get("total_vendas", 0) >= 5,
    },
]


def get_pontos_para_acao(acao: str) -> int:
    """Get the point value for a given action. Returns 0 if action not recognized."""
    return PONTOS_POR_ACAO.get(acao, 0)


def registrar_pontos(
    user_id: str,
    acao: str,
    supabase,
    referencia_id: Optional[str] = None,
    referencia_tipo: Optional[str] = None,
) -> dict:
    """
    Register points for an action and check for new badges.
    Returns {pontos, acao, novas_conquistas: [...]}.
    """
    pontos = get_pontos_para_acao(acao)
    if pontos <= 0:
        return {"pontos": 0, "acao": acao, "novas_conquistas": []}

    # Insert point record
    supabase.table("pontuacoes").insert({
        "user_id": user_id,
        "acao": acao,
        "pontos": pontos,
        "referencia_id": referencia_id,
        "referencia_tipo": referencia_tipo,
    }).execute()

    # Check for new badges
    novas_conquistas = check_and_award_badges(user_id, supabase)

    return {
        "pontos": pontos,
        "acao": acao,
        "novas_conquistas": novas_conquistas,
    }


def check_and_award_badges(user_id: str, supabase) -> list[dict]:
    """
    Check all badge conditions and award new ones if criteria met.
    Returns list of newly awarded badge dicts.
    """
    # Get user stats
    stats = _get_user_stats(user_id, supabase)

    # Get existing badges
    existing_result = supabase.table("conquistas").select("tipo").eq(
        "user_id", user_id
    ).execute()
    existing_tipos = {c["tipo"] for c in (existing_result.data or [])}

    novas = []
    for badge in BADGES:
        if badge["tipo"] in existing_tipos:
            continue
        if badge["condicao"](stats):
            novas.append({
                "user_id": user_id,
                "tipo": badge["tipo"],
                "nome": badge["nome"],
                "descricao": badge["descricao"],
                "icone": badge["icone"],
            })

    if novas:
        supabase.table("conquistas").insert(novas).execute()

    return novas


def _get_user_stats(user_id: str, supabase) -> dict:
    """Aggregate user stats for badge evaluation."""
    # Total points
    pontos_result = supabase.table("pontuacoes").select("pontos").eq(
        "user_id", user_id
    ).execute()
    total_pontos = sum(p.get("pontos", 0) for p in (pontos_result.data or []))

    # Total clients registered
    clientes_result = supabase.table("pontuacoes").select("id").eq(
        "user_id", user_id
    ).eq("acao", "novo_cliente").execute()
    total_clientes = len(clientes_result.data or [])

    # Total sales
    vendas_result = supabase.table("pontuacoes").select("id").eq(
        "user_id", user_id
    ).eq("acao", "venda_fechada").execute()
    total_vendas = len(vendas_result.data or [])

    # Visits this week
    now_sp = datetime.now(SP_OFFSET)
    week_start = (now_sp - timedelta(days=now_sp.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    visitas_result = supabase.table("pontuacoes").select("id").eq(
        "user_id", user_id
    ).eq("acao", "visita_realizada").gte(
        "created_at", week_start.isoformat()
    ).execute()
    visitas_semana = len(visitas_result.data or [])

    return {
        "total_pontos": total_pontos,
        "total_clientes": total_clientes,
        "total_vendas": total_vendas,
        "visitas_semana": visitas_semana,
    }


def build_leaderboard(supabase, periodo: str = "geral") -> list[dict]:
    """
    Build a leaderboard sorted by total points.
    Periodo: 'semana', 'mes', 'geral'.
    Returns list of {user_id, total_pontos, rank}.
    """
    query = supabase.table("pontuacoes").select("user_id, pontos, created_at")

    if periodo == "semana":
        now_sp = datetime.now(SP_OFFSET)
        week_start = (now_sp - timedelta(days=now_sp.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        query = query.gte("created_at", week_start.isoformat())
    elif periodo == "mes":
        now_sp = datetime.now(SP_OFFSET)
        month_start = now_sp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query = query.gte("created_at", month_start.isoformat())

    result = query.execute()
    rows = result.data or []

    # Aggregate by user
    user_points: dict[str, int] = {}
    for row in rows:
        uid = row.get("user_id", "")
        user_points[uid] = user_points.get(uid, 0) + row.get("pontos", 0)

    # Sort by points descending
    sorted_users = sorted(user_points.items(), key=lambda x: x[1], reverse=True)

    leaderboard = []
    for rank, (uid, pts) in enumerate(sorted_users, 1):
        leaderboard.append({
            "user_id": uid,
            "total_pontos": pts,
            "rank": rank,
        })

    return leaderboard
