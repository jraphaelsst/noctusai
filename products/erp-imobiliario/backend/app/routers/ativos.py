"""
Ativos CRUD Router — Unified table for imóveis + permutas.
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ativos", tags=["Ativos"])


class AtivoCreate(BaseModel):
    natureza: Literal["imovel", "permuta_imovel", "permuta_automovel"]
    valor: float = Field(default=0, ge=0, description="Valor deve ser >= 0")
    status: str = "ativo"
    observacoes: Optional[str] = None
    tipo_imovel: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = Field(default=None, max_length=2)
    zona: Optional[str] = None
    condominio_id: Optional[str] = None
    condominio_nome: Optional[str] = None
    area_privativa: Optional[float] = Field(default=None, ge=0)
    area_total: Optional[float] = Field(default=None, ge=0)
    quartos: Optional[int] = Field(default=None, ge=0, le=50)
    suites: Optional[int] = Field(default=None, ge=0, le=50)
    banheiros: Optional[int] = Field(default=None, ge=0, le=50)
    vagas: Optional[int] = Field(default=None, ge=0, le=100)
    andar: Optional[int] = Field(default=None, ge=-5, le=200)
    ano_construcao: Optional[int] = Field(default=None, ge=1800, le=2100)
    ref: Optional[str] = None
    corretor: Optional[str] = None
    proprietario_id: Optional[str] = None
    aceita_permutas: bool = False
    finalidade: Optional[str] = "venda"
    iptu: Optional[float] = Field(default=None, ge=0)
    pronto_para_portais: bool = False
    titulo_anuncio: Optional[str] = None
    descricao_seo: Optional[str] = None
    fotos: Optional[list] = None
    plantas: Optional[list] = None
    palavras_chave: Optional[list] = None
    pontos_de_interesse: Optional[list] = None
    tour_virtual_url: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    interesses: Optional[list] = None
    tipo_veiculo: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    motor: Optional[str] = None
    ano: Optional[int] = Field(default=None, ge=1900, le=2100)
    quilometragem: Optional[int] = Field(default=None, ge=0)
    faixa_preco_min: Optional[float] = Field(default=None, ge=0)
    faixa_preco_max: Optional[float] = Field(default=None, ge=0)
    regiao_preferida: Optional[list] = None
    aceita_completar_diferenca: bool = False
    limite_complemento: Optional[float] = Field(default=None, ge=0)
    metragem_min: Optional[float] = Field(default=None, ge=0)
    metragem_max: Optional[float] = Field(default=None, ge=0)
    quartos_min: Optional[int] = Field(default=None, ge=0, le=50)
    vagas_min: Optional[int] = Field(default=None, ge=0, le=100)
    ano_min: Optional[int] = Field(default=None, ge=1900, le=2100)
    ano_max: Optional[int] = Field(default=None, ge=1900, le=2100)
    quilometragem_max: Optional[int] = Field(default=None, ge=0)


class AtivoUpdate(BaseModel):
    valor: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = None
    observacoes: Optional[str] = None
    tipo_imovel: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = Field(default=None, max_length=2)
    zona: Optional[str] = None
    condominio_id: Optional[str] = None
    condominio_nome: Optional[str] = None
    area_privativa: Optional[float] = Field(default=None, ge=0)
    area_total: Optional[float] = Field(default=None, ge=0)
    quartos: Optional[int] = Field(default=None, ge=0, le=50)
    suites: Optional[int] = Field(default=None, ge=0, le=50)
    banheiros: Optional[int] = Field(default=None, ge=0, le=50)
    vagas: Optional[int] = Field(default=None, ge=0, le=100)
    andar: Optional[int] = Field(default=None, ge=-5, le=200)
    ano_construcao: Optional[int] = Field(default=None, ge=1800, le=2100)
    ref: Optional[str] = None
    corretor: Optional[str] = None
    proprietario_id: Optional[str] = None
    aceita_permutas: Optional[bool] = None
    finalidade: Optional[str] = None
    iptu: Optional[float] = Field(default=None, ge=0)
    pronto_para_portais: Optional[bool] = None
    titulo_anuncio: Optional[str] = None
    descricao_seo: Optional[str] = None
    fotos: Optional[list] = None
    plantas: Optional[list] = None
    palavras_chave: Optional[list] = None
    pontos_de_interesse: Optional[list] = None
    tour_virtual_url: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    interesses: Optional[list] = None
    tipo_veiculo: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    motor: Optional[str] = None
    ano: Optional[int] = Field(default=None, ge=1900, le=2100)
    quilometragem: Optional[int] = Field(default=None, ge=0)
    faixa_preco_min: Optional[float] = Field(default=None, ge=0)
    faixa_preco_max: Optional[float] = Field(default=None, ge=0)
    regiao_preferida: Optional[list] = None
    aceita_completar_diferenca: Optional[bool] = None
    limite_complemento: Optional[float] = Field(default=None, ge=0)
    metragem_min: Optional[float] = Field(default=None, ge=0)
    metragem_max: Optional[float] = Field(default=None, ge=0)
    quartos_min: Optional[int] = Field(default=None, ge=0, le=50)
    vagas_min: Optional[int] = Field(default=None, ge=0, le=100)
    ano_min: Optional[int] = Field(default=None, ge=1900, le=2100)
    ano_max: Optional[int] = Field(default=None, ge=1900, le=2100)
    quilometragem_max: Optional[int] = Field(default=None, ge=0)


@router.get("")
async def listar_ativos(
    natureza: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tipo_imovel: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
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

    # Build count query
    count_query = db.table("ativos").select("id", count="exact")
    if natureza:
        if "," in natureza:
            count_query = count_query.in_("natureza", natureza.split(","))
        else:
            count_query = count_query.eq("natureza", natureza)
    if status:
        count_query = count_query.eq("status", status)
    if tipo_imovel:
        count_query = count_query.eq("tipo_imovel", tipo_imovel)
    if cidade:
        count_query = count_query.ilike("cidade", f"%{cidade}%")

    # Build data query with pagination
    query = db.table("ativos").select("*").order("created_at", desc=True)

    if natureza:
        if "," in natureza:
            query = query.in_("natureza", natureza.split(","))
        else:
            query = query.eq("natureza", natureza)
    if status:
        query = query.eq("status", status)
    if tipo_imovel:
        query = query.eq("tipo_imovel", tipo_imovel)
    if cidade:
        query = query.ilike("cidade", f"%{cidade}%")

    # Apply pagination
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    # Get total count
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    # Server-side text search
    if busca:
        q = busca.lower()
        data = [d for d in data if any(
            q in str(d.get(f, "") or "").lower()
            for f in ["id", "cidade", "bairro", "titulo_anuncio", "condominio_nome",
                       "marca", "modelo", "tipo_imovel", "tipo_veiculo", "ref"]
        )]
        total = len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{ativo_id}")
async def obter_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("ativos").select("*").eq("id", ativo_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_ativo(body: AtivoCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # natureza is validated by Pydantic Literal type
    data = body.model_dump(exclude_none=True)
    data["owner_id"] = user.id

    result = db.table("ativos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar ativo")

    ativo = row
    log_action(user.id, "criar", "ativo", ativo["id"],
               f"Criou {body.natureza} {ativo['id']}")

    # Auto-trigger embedding generation (non-blocking)
    try:
        from app.services.embedding_service import embed_ativo as do_embed
        admin = get_admin_client()
        await do_embed(ativo, admin)
    except Exception as e:
        logger.warning(f"Auto-embedding failed for {ativo['id']}: {e}")

    # Auto-trigger matching
    if body.natureza == "imovel" and body.aceita_permutas:
        try:
            from app.services.matching import gerar_matches_para_imovel
            admin = get_admin_client()
            permutas = admin.table("ativos").select("*").in_(
                "natureza", ["permuta_imovel", "permuta_automovel"]
            ).eq("status", "ativo").execute()
            matches = gerar_matches_para_imovel(ativo, permutas.data or [])
            for m in matches:
                admin.table("matches").upsert(
                    {**m, "status": "pendente"},
                    on_conflict="ativo_origem_id,ativo_destino_id",
                ).execute()
            ativo["_matches_count"] = len(matches)
        except Exception as e:
            logger.warning(f"Auto-matching failed: {e}")

    return success_response(ativo)


@router.patch("/{ativo_id}")
async def atualizar_ativo(ativo_id: str, body: AtivoUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("ativos").update(data).eq("id", ativo_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Ativo não encontrado ou sem permissão")

    log_action(user.id, "editar", "ativo", ativo_id, f"Editou ativo {ativo_id}")

    # Re-embed after update (non-blocking)
    try:
        from app.services.embedding_service import embed_ativo as do_embed
        admin = get_admin_client()
        await do_embed(row, admin)
    except Exception as e:
        logger.warning(f"Auto-embedding failed for {ativo_id}: {e}")

    return success_response(row)


@router.delete("/{ativo_id}")
async def excluir_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("ativos").delete().eq("id", ativo_id).execute()
    log_action(user.id, "excluir", "ativo", ativo_id, f"Excluiu ativo {ativo_id}")
    return ok_response("Ativo excluído com sucesso")
