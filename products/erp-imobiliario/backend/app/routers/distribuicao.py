"""
Distribuicao (Lead Distribution) Router — Manages lead assignment
configuration and agent queues.

-- CREATE TABLE distribuicao_config (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL UNIQUE,
--   modo text NOT NULL DEFAULT 'manual' CHECK (modo IN ('manual', 'round_robin', 'por_regiao', 'por_especialidade')),
--   corretores_ativos uuid[] NOT NULL DEFAULT '{}',
--   proximo_corretor_idx int NOT NULL DEFAULT 0,
--   regras jsonb NOT NULL DEFAULT '{}',
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, get_org_id, log_action, first_or_none
from app.responses import success_response
from app.services.distribuicao_service import auto_assign, get_queue_info
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/distribuicao", tags=["Distribuição"])


# --------------- Schemas ---------------

class ConfigUpdate(StrictHttpModel):
    modo: Optional[Literal["manual", "round_robin", "por_regiao", "por_especialidade"]] = None
    corretores_ativos: Optional[List[str]] = None
    regras: Optional[Dict[str, Any]] = None


class AtribuirRequest(StrictHttpModel):
    cliente_id: str
    corretor_id: Optional[str] = Field(
        default=None,
        description="Se fornecido, atribui manualmente. Se omitido, usa auto-assign.",
    )


# --------------- Endpoints ---------------

@router.get("/config")
async def obter_config(auth = Depends(get_current_user)):
    """Get the distribution configuration for the current org."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("distribuicao_config").select("*").execute()

    if not result.data:
        # Return default config if none exists
        return success_response({
            "modo": "manual",
            "corretores_ativos": [],
            "proximo_corretor_idx": 0,
            "regras": {},
        })

    return success_response(result.data[0])


@router.patch("/config")
async def atualizar_config(body: ConfigUpdate, auth = Depends(get_current_user)):
    """Update the distribution configuration (mode, active agents, rules)."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Check if config exists
    existing = db.table("distribuicao_config").select("id").execute()

    if existing.data:
        result = db.table("distribuicao_config").update(data).eq(
            "id", existing.data[0]["id"]
        ).execute()
        row = first_or_none(result)
    else:
        # Create new config
        result = db.table("distribuicao_config").insert(data).execute()
        row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=500, detail="Erro ao atualizar configuração de distribuição")

    log_action(user.id, "editar", "distribuicao_config", row["id"],
               f"Atualizou configuração de distribuição: modo={data.get('modo', 'unchanged')}")

    return success_response(row)


@router.post("/atribuir")
async def atribuir_lead(body: AtribuirRequest, auth = Depends(get_current_user)):
    """
    Assign a lead to an agent.

    If `corretor_id` is provided, assigns manually.
    If omitted, uses the auto-assign logic based on the org's config.
    """
    user, token = auth
    db = get_user_client(token)

    if body.corretor_id:
        # Manual assignment
        result = db.table("clientes").update({
            "usuario_id": body.corretor_id,
        }).eq("id", body.cliente_id).execute()
        row = first_or_none(result)

        if not row:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        log_action(user.id, "atribuir", "cliente", body.cliente_id,
                   f"Atribuiu manualmente cliente {body.cliente_id} ao corretor {body.corretor_id}")

        return success_response({
            "atribuido": True,
            "corretor_id": body.corretor_id,
            "modo": "manual",
            "cliente": row,
        })

    # Auto-assign
    org_id = get_org_id(user)
    resultado = auto_assign(
        cliente_id=body.cliente_id,
        org_id=org_id,
        supabase=db,
    )

    if resultado.get("atribuido"):
        log_action(user.id, "atribuir", "cliente", body.cliente_id,
                   f"Auto-atribuiu cliente {body.cliente_id} ao corretor {resultado.get('corretor_id')}",
                   resultado)

    return success_response(resultado)


@router.get("/fila")
async def obter_fila(auth = Depends(get_current_user)):
    """
    Get current queue/next agent info for the org.
    Shows active agents and who is next in line.
    """
    user, token = auth
    db = get_user_client(token)

    config_res = db.table("distribuicao_config").select("*").execute()

    if not config_res.data:
        return success_response({
            "modo": "manual",
            "corretores_ativos": [],
            "proximo_corretor_id": None,
            "proximo_corretor_idx": 0,
        })

    config = config_res.data[0]
    info = get_queue_info(config, db)

    return success_response(info)
