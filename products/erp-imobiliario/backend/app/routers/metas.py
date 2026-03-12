"""
Metas CRUD Router — Goals/targets management.
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.metas_service import criar_metas_hoje
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas", tags=["Metas"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MetaCreate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=255)
    categoria: Literal[
        "captacao", "visitas", "contatos", "propostas", "fechamento",
        "captacao_imoveis", "captacao_compradores", "atualizacao_imoveis", "outro"
    ] = "captacao"
    categoria_custom: Optional[str] = Field(default=None, max_length=255)
    tipo: Literal["diaria", "semanal", "mensal", "anual"]
    meta_pretendida: int = Field(..., ge=1, description="Quantidade alvo deve ser >= 1")
    data_prazo: str  # Server handles timezone
    usuario_id: Optional[str] = None
    detalhes: Optional[str] = None
    criada_manualmente: bool = True
    meta_realizada: int = Field(default=0, ge=0)
    status: Literal["aberta", "concluida", "atrasada", "no_prazo", "vence_amanha"] = "no_prazo"
    tem_impedimento: bool = False
    motivo_impedimento: Optional[str] = None


class MetaUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=255)
    meta_realizada: Optional[int] = Field(default=None, ge=0)
    status: Optional[Literal["aberta", "concluida", "atrasada", "no_prazo", "vence_amanha"]] = None
    detalhes: Optional[str] = None
    tem_impedimento: Optional[bool] = None
    motivo_impedimento: Optional[str] = None
    finalizada_em: Optional[str] = None
    finalizada_no_prazo: Optional[bool] = None
    conclusao_prazo: Optional[str] = None
    categoria_custom: Optional[str] = None
    criada_manualmente: Optional[bool] = None
    nivel_performance: Optional[str] = None
    carry_in: Optional[int] = None
    carry_out: Optional[int] = None


class MetaConfigCreate(BaseModel):
    categoria: str
    categoria_custom: Optional[str] = None
    meta_pretendida: int = Field(..., ge=0)
    ativo: bool = True


class ScaffoldBody(BaseModel):
    tipo: Literal["diaria", "semanal", "mensal", "anual"]
    categoria: str
    data_ref: Optional[str] = None


class CalcularProporcionalBody(BaseModel):
    meta_mensal: int = Field(..., ge=0)
    tipo: Literal["diaria", "semanal", "mensal", "anual"]
    data_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Data-prazo endpoint (must be before /{meta_id} to avoid route conflict)
# ---------------------------------------------------------------------------

@router.get("/data-prazo")
async def data_prazo(
    tipo: Literal["diaria", "semanal", "mensal", "anual"] = Query("mensal"),
    authorization: Optional[str] = Header(None),
):
    """Return current São Paulo date and the period end date for the given tipo."""
    await get_current_user(authorization)
    admin = get_admin_client()

    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None

    prazo_result = admin.rpc("period_end_date", {"tipo_meta": tipo, "data_ref": data_hoje}).execute()
    data_prazo_val = prazo_result.data if prazo_result.data else data_hoje

    return success_response({"data_hoje": data_hoje, "data_prazo": data_prazo_val})


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@router.get("/config")
async def listar_config(authorization: Optional[str] = Header(None)):
    """List the authenticated user's metas_config entries."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = (
        db.table("metas_config")
        .select("*")
        .eq("usuario_id", user.id)
        .order("tipo", desc=False)
        .execute()
    )
    return success_response(result.data or [])


@router.post("/config")
async def upsert_config(body: MetaConfigCreate, authorization: Optional[str] = Header(None)):
    """Upsert a metas_config entry (always tipo='mensal')."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    payload = {
        "usuario_id": user.id,
        "tipo": "mensal",
        **body.model_dump(exclude_none=True),
        "ativo": body.ativo,
    }

    result = (
        db.table("metas_config")
        .upsert(payload)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao salvar configuração de meta")

    log_action(user.id, "editar", "config_meta", row.get("id", ""),
               f"Upsert config {body.categoria}")
    return success_response(row)


@router.delete("/config/{config_id}")
async def excluir_config(config_id: str, authorization: Optional[str] = Header(None)):
    """Delete a metas_config entry."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("metas_config").select("id").eq("id", config_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Configuração de meta não encontrada")

    db.table("metas_config").delete().eq("id", config_id).execute()
    log_action(user.id, "excluir", "config_meta", config_id, f"Excluiu config {config_id}")
    return ok_response("Configuração de meta excluída com sucesso")


# ---------------------------------------------------------------------------
# Concluir (conclude grouped meta)
# ---------------------------------------------------------------------------

@router.post("/{meta_id}/concluir")
async def concluir_meta(meta_id: str, authorization: Optional[str] = Header(None)):
    """Conclude a grouped meta via the concluir_meta_agrupada RPC."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.rpc("concluir_meta_agrupada", {"p_meta_id": meta_id}).execute()
    data = result.data

    if isinstance(data, dict) and not data.get("success", True):
        raise HTTPException(status_code=400, detail=data.get("error", "Erro ao concluir meta"))

    log_action(user.id, "editar", "meta", meta_id, "Concluiu meta agrupada")
    return success_response(data)


# ---------------------------------------------------------------------------
# Atualizar status (bulk overdue detection)
# ---------------------------------------------------------------------------

@router.post("/atualizar-status")
async def atualizar_status(authorization: Optional[str] = Header(None)):
    """Bulk update meta statuses (overdue detection)."""
    user, token = await get_current_user(authorization)
    admin = get_admin_client()

    # Get current São Paulo date
    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None

    if not data_hoje:
        raise HTTPException(status_code=500, detail="Erro ao obter data atual")

    db = get_user_client(token)

    # Find open metas with expired deadline
    overdue = (
        db.table("metas")
        .select("id")
        .eq("usuario_id", user.id)
        .in_("status", ["no_prazo", "vence_amanha", "aberta"])
        .lt("data_prazo", data_hoje)
        .execute()
    )

    ids = [m["id"] for m in (overdue.data or [])]
    updated = 0

    if ids:
        db.table("metas").update({"status": "atrasada"}).in_("id", ids).execute()
        updated = len(ids)

    log_action(user.id, "editar", "meta", "", f"Atualização em lote: {updated} metas atrasadas")
    return success_response({"metas_atualizadas": updated})


# ---------------------------------------------------------------------------
# Criar hoje (create today's metas from active configs)
# ---------------------------------------------------------------------------

@router.post("/criar-hoje")
async def criar_hoje(authorization: Optional[str] = Header(None)):
    """Create today's metas from active metas_config entries."""
    user, token = await get_current_user(authorization)
    admin = get_admin_client()
    db = get_user_client(token)

    # Current date
    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None
    if not data_hoje:
        raise HTTPException(status_code=500, detail="Erro ao obter data atual")

    created = criar_metas_hoje(user.id, data_hoje, db, admin)

    log_action(user.id, "criar", "meta", "", f"Criou {created} metas a partir de configs")
    return success_response({"message": f"{created} metas criadas com sucesso.", "metas_criadas": created})


# ---------------------------------------------------------------------------
# Scaffold (ensure scaffold meta exists)
# ---------------------------------------------------------------------------

@router.post("/scaffold")
async def scaffold(body: ScaffoldBody, authorization: Optional[str] = Header(None)):
    """Ensure a scaffold meta exists for the given tipo/categoria."""
    user, token = await get_current_user(authorization)
    admin = get_admin_client()
    db = get_user_client(token)

    # Resolve reference date
    data_ref = body.data_ref
    if not data_ref:
        date_result = admin.rpc("get_data_sp").execute()
        data_ref = date_result.data

    result = db.rpc("ensure_scaffold_meta", {
        "p_usuario_id": user.id,
        "p_tipo": body.tipo,
        "p_categoria": body.categoria,
        "p_data_ref": data_ref,
    }).execute()

    return success_response({"meta_id": result.data})


# ---------------------------------------------------------------------------
# Calcular proporcional
# ---------------------------------------------------------------------------

@router.post("/calcular-proporcional")
async def calcular_proporcional(body: CalcularProporcionalBody, authorization: Optional[str] = Header(None)):
    """Calculate proportional meta value based on remaining days in the period."""
    user, token = await get_current_user(authorization)
    admin = get_admin_client()

    # Resolve reference date
    data_ref = body.data_ref
    if not data_ref:
        date_result = admin.rpc("get_data_sp").execute()
        data_ref = date_result.data

    result = admin.rpc("calcular_meta_proporcional", {
        "p_meta_mensal": body.meta_mensal,
        "p_tipo": body.tipo,
        "p_data_ref": data_ref,
    }).execute()

    return success_response({"meta_proporcional": result.data})


# ---------------------------------------------------------------------------
# Metas hoje
# ---------------------------------------------------------------------------

@router.get("/hoje")
async def metas_hoje(authorization: Optional[str] = Header(None)):
    """Get current São Paulo date and today's metas."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Server-side date calculation (São Paulo timezone)
    admin = get_admin_client()
    date_result = admin.rpc("get_data_sp").execute()
    data_hoje = date_result.data if date_result.data else None

    query = db.table("metas").select("*").eq("usuario_id", user.id)
    if data_hoje:
        query = query.eq("data_prazo", data_hoje)

    result = query.execute()
    return success_response({"metas": result.data or [], "data_hoje": data_hoje})


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def listar_metas(
    corretor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Calculate pagination
    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("metas").select("id", count="exact")
    if corretor_id:
        count_query = count_query.eq("usuario_id", corretor_id)

    # Data query with pagination
    query = db.table("metas").select("*").order("data_prazo", desc=True)
    if corretor_id:
        query = query.eq("usuario_id", corretor_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(result.data or [])

    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_meta(body: MetaCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data.get("usuario_id"):
        data["usuario_id"] = user.id

    result = db.table("metas").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")

    log_action(user.id, "criar", "meta", row["id"],
               f"Criou meta {body.categoria}")
    return success_response(row)


@router.patch("/{meta_id}")
async def atualizar_meta(meta_id: str, body: MetaUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    result = db.table("metas").update(data).eq("id", meta_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    log_action(user.id, "editar", "meta", meta_id, f"Atualizou meta {meta_id}")
    return success_response(row)


@router.delete("/{meta_id}")
async def excluir_meta(meta_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("metas").select("id").eq("id", meta_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    db.table("metas").delete().eq("id", meta_id).execute()
    log_action(user.id, "excluir", "meta", meta_id, f"Excluiu meta {meta_id}")
    return ok_response("Meta excluída com sucesso")
