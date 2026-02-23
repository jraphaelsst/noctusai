"""
Ativos CRUD Router — Unified table for imóveis + permutas.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ativos", tags=["Ativos"])


class AtivoCreate(BaseModel):
    natureza: str  # imovel | permuta_imovel | permuta_automovel
    valor: float = 0
    status: str = "ativo"
    observacoes: Optional[str] = None
    tipo_imovel: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    zona: Optional[str] = None
    condominio_id: Optional[str] = None
    condominio_nome: Optional[str] = None
    area_privativa: Optional[float] = None
    area_total: Optional[float] = None
    quartos: Optional[int] = None
    suites: Optional[int] = None
    banheiros: Optional[int] = None
    vagas: Optional[int] = None
    andar: Optional[int] = None
    ano_construcao: Optional[int] = None
    ref: Optional[str] = None
    corretor: Optional[str] = None
    proprietario_id: Optional[str] = None
    aceita_permutas: bool = False
    finalidade: Optional[str] = "venda"
    iptu: Optional[float] = None
    pronto_para_portais: bool = False
    titulo_anuncio: Optional[str] = None
    descricao_seo: Optional[str] = None
    fotos: Optional[list] = None
    plantas: Optional[list] = None
    palavras_chave: Optional[list] = None
    pontos_de_interesse: Optional[list] = None
    tour_virtual_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    interesses: Optional[list] = None
    tipo_veiculo: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    motor: Optional[str] = None
    ano: Optional[int] = None
    quilometragem: Optional[int] = None
    faixa_preco_min: Optional[float] = None
    faixa_preco_max: Optional[float] = None
    regiao_preferida: Optional[list] = None
    aceita_completar_diferenca: bool = False
    limite_complemento: Optional[float] = None
    metragem_min: Optional[float] = None
    metragem_max: Optional[float] = None
    quartos_min: Optional[int] = None
    vagas_min: Optional[int] = None
    ano_min: Optional[int] = None
    ano_max: Optional[int] = None
    quilometragem_max: Optional[int] = None


class AtivoUpdate(BaseModel):
    valor: Optional[float] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    tipo_imovel: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    zona: Optional[str] = None
    condominio_id: Optional[str] = None
    condominio_nome: Optional[str] = None
    area_privativa: Optional[float] = None
    area_total: Optional[float] = None
    quartos: Optional[int] = None
    suites: Optional[int] = None
    banheiros: Optional[int] = None
    vagas: Optional[int] = None
    andar: Optional[int] = None
    ano_construcao: Optional[int] = None
    ref: Optional[str] = None
    corretor: Optional[str] = None
    proprietario_id: Optional[str] = None
    aceita_permutas: Optional[bool] = None
    finalidade: Optional[str] = None
    iptu: Optional[float] = None
    pronto_para_portais: Optional[bool] = None
    titulo_anuncio: Optional[str] = None
    descricao_seo: Optional[str] = None
    fotos: Optional[list] = None
    plantas: Optional[list] = None
    palavras_chave: Optional[list] = None
    pontos_de_interesse: Optional[list] = None
    tour_virtual_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    interesses: Optional[list] = None
    tipo_veiculo: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    motor: Optional[str] = None
    ano: Optional[int] = None
    quilometragem: Optional[int] = None
    faixa_preco_min: Optional[float] = None
    faixa_preco_max: Optional[float] = None
    regiao_preferida: Optional[list] = None
    aceita_completar_diferenca: Optional[bool] = None
    limite_complemento: Optional[float] = None
    metragem_min: Optional[float] = None
    metragem_max: Optional[float] = None
    quartos_min: Optional[int] = None
    vagas_min: Optional[int] = None
    ano_min: Optional[int] = None
    ano_max: Optional[int] = None
    quilometragem_max: Optional[int] = None


@router.get("")
async def listar_ativos(
    natureza: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tipo_imovel: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

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

    result = query.execute()
    data = result.data or []

    # Server-side text search
    if busca:
        q = busca.lower()
        data = [d for d in data if any(
            q in str(d.get(f, "") or "").lower()
            for f in ["id", "cidade", "bairro", "titulo_anuncio", "condominio_nome",
                       "marca", "modelo", "tipo_imovel", "tipo_veiculo", "ref"]
        )]

    return {"data": data, "total": len(data)}


@router.get("/{ativo_id}")
async def obter_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("ativos").select("*").eq("id", ativo_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    return {"data": result.data}


@router.post("")
async def criar_ativo(body: AtivoCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    valid_naturezas = {"imovel", "permuta_imovel", "permuta_automovel"}
    if body.natureza not in valid_naturezas:
        raise HTTPException(status_code=400, detail=f"Natureza inválida. Use: {valid_naturezas}")

    data = body.model_dump(exclude_none=True)
    data["owner_id"] = user.id

    result = db.table("ativos").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar ativo")

    ativo = result.data
    log_action(user.id, "criar", "ativo", ativo["id"],
               f"Criou {body.natureza} {ativo['id']}")

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

    return {"data": ativo}


@router.patch("/{ativo_id}")
async def atualizar_ativo(ativo_id: str, body: AtivoUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("ativos").update(data).eq("id", ativo_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Ativo não encontrado ou sem permissão")

    log_action(user.id, "editar", "ativo", ativo_id, f"Editou ativo {ativo_id}")
    return {"data": result.data}


@router.delete("/{ativo_id}")
async def excluir_ativo(ativo_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("ativos").delete().eq("id", ativo_id).execute()
    log_action(user.id, "excluir", "ativo", ativo_id, f"Excluiu ativo {ativo_id}")
    return {"ok": True}
