"""
Portais Router — Portal integration and XML feed generation for real estate listings.

Provides endpoints to generate XML feeds for major Brazilian real estate portals
(ZAP, OLX, VivaReal) and manage portal publishing status for properties.
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import Response
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import success_response
from app.services.xml_feeds import generate_zap_xml, generate_olx_xml, generate_vivareal_xml
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portais", tags=["Portais"])

PORTAL_GENERATORS = {
    "zap": generate_zap_xml,
    "olx": generate_olx_xml,
    "vivareal": generate_vivareal_xml,
}

PORTAL_INFO = {
    "zap": {
        "nome": "ZAP Imoveis",
        "descricao": "Feed XML para o portal ZAP Imoveis",
        "formato": "XML ZAP Schema",
    },
    "olx": {
        "nome": "OLX",
        "descricao": "Feed XML para o portal OLX",
        "formato": "XML OLX Ad Schema",
    },
    "vivareal": {
        "nome": "VivaReal",
        "descricao": "Feed XML para o portal VivaReal",
        "formato": "XML VivaReal ListingDataFeed",
    },
}


class TogglePortalRequest(StrictHttpModel):
    pronto_para_portais: bool


@router.get("/feeds")
async def listar_feeds(
    auth = Depends(get_current_user)):
    """
    List available portal feeds with their URLs and current property count.
    """
    user, token = auth
    db = get_user_client(token)

    # Count portal-ready properties
    count_result = db.table("ativos").select("id", count="exact").eq(
        "natureza", "imovel"
    ).eq("pronto_para_portais", True).eq("status", "ativo").execute()
    total_ready = count_result.count if count_result.count is not None else 0

    feeds = []
    for portal_key, info in PORTAL_INFO.items():
        feeds.append({
            "portal": portal_key,
            "nome": info["nome"],
            "descricao": info["descricao"],
            "formato": info["formato"],
            "url": f"/api/portais/feed/{portal_key}",
            "imoveis_prontos": total_ready,
        })

    return success_response(feeds)


@router.get("/feed/{portal}")
async def gerar_feed(
    portal: str,
    auth = Depends(get_current_user)):
    """
    Generate the XML feed for a specific portal.

    Only includes properties marked as pronto_para_portais=True and status='ativo'.
    Returns XML content type.
    """
    if portal not in PORTAL_GENERATORS:
        raise HTTPException(
            status_code=400,
            detail=f"Portal invalido. Portais disponiveis: {', '.join(PORTAL_GENERATORS.keys())}"
        )
    user, token = auth
    db = get_user_client(token)

    # Fetch portal-ready properties
    result = db.table("ativos").select("*").eq(
        "natureza", "imovel"
    ).eq("pronto_para_portais", True).eq("status", "ativo").execute()
    imoveis = result.data or []

    # Generate XML using the appropriate generator
    generator = PORTAL_GENERATORS[portal]
    xml_content = generator(imoveis)

    logger.info(f"Generated {portal} XML feed with {len(imoveis)} properties for user {user.id}")

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'inline; filename="feed_{portal}.xml"',
        },
    )


@router.patch("/toggle/{imovel_id}")
async def toggle_portal(
    imovel_id: str,
    body: TogglePortalRequest,
    auth = Depends(get_current_user)):
    """
    Toggle the portal publishing status for a specific property.

    Sets pronto_para_portais to True/False, controlling whether
    the property appears in generated XML feeds.
    """
    user, token = auth
    db = get_user_client(token)

    # Verify property exists and is an imovel
    existing = db.table("ativos").select("id, natureza").eq("id", imovel_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Imovel nao encontrado")
    if existing.data.get("natureza") != "imovel":
        raise HTTPException(status_code=400, detail="Apenas imoveis podem ser publicados em portais")

    result = db.table("ativos").update({
        "pronto_para_portais": body.pronto_para_portais,
    }).eq("id", imovel_id).execute()
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=500, detail="Erro ao atualizar status do portal")

    status_label = "ativado" if body.pronto_para_portais else "desativado"
    log_action(
        user.id, "editar", "ativo", imovel_id,
        f"Portal {status_label} para imovel {imovel_id}"
    )

    return success_response(row)


@router.get("/imoveis")
async def listar_imoveis_portal(
    pronto_para_portais: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """
    List properties with their portal readiness status.
    Useful for managing which properties appear in feeds.
    """
    from app.responses import paginated_response, calculate_pagination
    from app.config import settings
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("ativos").select("id", count="exact").eq("natureza", "imovel")
    if pronto_para_portais is not None:
        count_query = count_query.eq("pronto_para_portais", pronto_para_portais)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("ativos").select(
        "id, titulo_anuncio, cidade, bairro, estado, tipo_imovel, valor, "
        "pronto_para_portais, status, fotos, descricao_seo"
    ).eq("natureza", "imovel").order("created_at", desc=True)

    if pronto_para_portais is not None:
        query = query.eq("pronto_para_portais", pronto_para_portais)

    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)
