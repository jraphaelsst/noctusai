"""
Distribuicao Service — Business logic for lead distribution.

Implements round-robin, region-based, and specialty-based
lead assignment strategies.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_next_agent(
    config: Dict[str, Any],
    supabase,
) -> Optional[str]:
    """
    Determine the next agent in a round-robin cycle.

    Uses `corretores_ativos` and `proximo_corretor_idx` from the config.
    Advances the index and persists it.

    Returns the agent UUID or None if no agents are active.
    """
    corretores = config.get("corretores_ativos") or []
    if not corretores:
        return None

    idx = config.get("proximo_corretor_idx", 0) % len(corretores)
    next_agent = corretores[idx]

    # Advance index
    new_idx = (idx + 1) % len(corretores)
    try:
        supabase.table("distribuicao_config").update({
            "proximo_corretor_idx": new_idx,
        }).eq("id", config["id"]).execute()
    except Exception as e:
        logger.warning(f"Failed to advance round-robin index: {e}")

    return next_agent


def auto_assign(
    cliente_id: str,
    org_id: str,
    supabase,
) -> Dict[str, Any]:
    """
    Auto-assign a lead to an agent based on the org's distribution config.

    Supported modes:
      - manual: no-op, returns info only
      - round_robin: assigns via rotating index
      - por_regiao: matches client region to agent rules
      - por_especialidade: matches client interest to agent rules

    Returns a dict with the assignment result.
    """
    # Fetch config
    config_res = supabase.table("distribuicao_config").select("*").eq(
        "org_id", org_id
    ).execute()

    if not config_res.data:
        return {
            "atribuido": False,
            "motivo": "Configuração de distribuição não encontrada",
        }

    config = config_res.data[0]
    modo = config.get("modo", "manual")

    if modo == "manual":
        return {
            "atribuido": False,
            "motivo": "Modo manual — atribua manualmente",
            "modo": "manual",
        }

    if modo == "round_robin":
        agent_id = get_next_agent(config, supabase)
        if not agent_id:
            return {
                "atribuido": False,
                "motivo": "Nenhum corretor ativo na configuração",
            }

        # Assign the client
        supabase.table("clientes").update({
            "usuario_id": agent_id,
        }).eq("id", cliente_id).execute()

        return {
            "atribuido": True,
            "corretor_id": agent_id,
            "modo": "round_robin",
        }

    if modo == "por_regiao":
        return _assign_by_region(cliente_id, config, supabase)

    if modo == "por_especialidade":
        return _assign_by_specialty(cliente_id, config, supabase)

    return {
        "atribuido": False,
        "motivo": f"Modo de distribuição desconhecido: {modo}",
    }


def _assign_by_region(
    cliente_id: str,
    config: Dict[str, Any],
    supabase,
) -> Dict[str, Any]:
    """
    Assign a lead based on region rules.

    The config's `regras` field should contain a mapping like:
    { "regioes": { "zona_sul": "agent-uuid", "zona_norte": "agent-uuid" } }
    """
    regras = config.get("regras") or {}
    regioes_map = regras.get("regioes", {})

    # Get the client's region info
    cliente_res = supabase.table("clientes").select(
        "id, interesse, observacoes"
    ).eq("id", cliente_id).single().execute()

    if not cliente_res.data:
        return {"atribuido": False, "motivo": "Cliente não encontrado"}

    cliente = cliente_res.data
    interesse = (cliente.get("interesse") or "").lower()

    # Try to match a region keyword
    for regiao, agent_id in regioes_map.items():
        if regiao.lower() in interesse:
            supabase.table("clientes").update({
                "usuario_id": agent_id,
            }).eq("id", cliente_id).execute()
            return {
                "atribuido": True,
                "corretor_id": agent_id,
                "modo": "por_regiao",
                "regiao": regiao,
            }

    # Fallback to round-robin if no region match
    agent_id = get_next_agent(config, supabase)
    if agent_id:
        supabase.table("clientes").update({
            "usuario_id": agent_id,
        }).eq("id", cliente_id).execute()
        return {
            "atribuido": True,
            "corretor_id": agent_id,
            "modo": "por_regiao",
            "regiao": "fallback_round_robin",
        }

    return {"atribuido": False, "motivo": "Sem corretor para a região"}


def _assign_by_specialty(
    cliente_id: str,
    config: Dict[str, Any],
    supabase,
) -> Dict[str, Any]:
    """
    Assign a lead based on agent specialties.

    The config's `regras` field should contain:
    { "especialidades": { "comercial": "agent-uuid", "residencial": "agent-uuid" } }
    """
    regras = config.get("regras") or {}
    especialidades_map = regras.get("especialidades", {})

    cliente_res = supabase.table("clientes").select(
        "id, interesse"
    ).eq("id", cliente_id).single().execute()

    if not cliente_res.data:
        return {"atribuido": False, "motivo": "Cliente não encontrado"}

    interesse = (cliente_res.data.get("interesse") or "").lower()

    for espec, agent_id in especialidades_map.items():
        if espec.lower() in interesse:
            supabase.table("clientes").update({
                "usuario_id": agent_id,
            }).eq("id", cliente_id).execute()
            return {
                "atribuido": True,
                "corretor_id": agent_id,
                "modo": "por_especialidade",
                "especialidade": espec,
            }

    # Fallback
    agent_id = get_next_agent(config, supabase)
    if agent_id:
        supabase.table("clientes").update({
            "usuario_id": agent_id,
        }).eq("id", cliente_id).execute()
        return {
            "atribuido": True,
            "corretor_id": agent_id,
            "modo": "por_especialidade",
            "especialidade": "fallback_round_robin",
        }

    return {"atribuido": False, "motivo": "Sem corretor para a especialidade"}


def get_queue_info(
    config: Dict[str, Any],
    supabase,
) -> Dict[str, Any]:
    """
    Return current queue state (active agents and who is next).
    """
    corretores = config.get("corretores_ativos") or []
    idx = config.get("proximo_corretor_idx", 0)

    if not corretores:
        return {
            "modo": config.get("modo", "manual"),
            "corretores_ativos": [],
            "proximo_corretor_id": None,
            "proximo_corretor_idx": 0,
        }

    # Fetch profile names for active agents
    profiles_res = supabase.table("profiles").select(
        "id, nome, email"
    ).in_("id", corretores).execute()
    profiles = {p["id"]: p for p in (profiles_res.data or [])}

    safe_idx = idx % len(corretores) if corretores else 0
    proximo = corretores[safe_idx] if corretores else None

    agents_info = []
    for i, cid in enumerate(corretores):
        prof = profiles.get(cid, {})
        agents_info.append({
            "id": cid,
            "nome": prof.get("nome", ""),
            "email": prof.get("email", ""),
            "is_next": i == safe_idx,
        })

    return {
        "modo": config.get("modo", "manual"),
        "corretores_ativos": agents_info,
        "proximo_corretor_id": proximo,
        "proximo_corretor_idx": safe_idx,
        "regras": config.get("regras", {}),
    }
