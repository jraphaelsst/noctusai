"""
Campo (Mobile Field Features) API endpoints.

Endpoints for field agents: GPS check-in, quick inspections, and nearby properties.

-- CREATE TABLE checkins (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   corretor_id uuid NOT NULL,
--   imovel_id uuid,
--   latitude numeric NOT NULL,
--   longitude numeric NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('visita', 'vistoria', 'captacao', 'reuniao')),
--   observacoes text,
--   fotos text[] NOT NULL DEFAULT '{}',
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
import math
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campo", tags=["Campo"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CheckinCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    tipo: Literal["visita", "vistoria", "captacao", "reuniao"]
    imovel_id: Optional[str] = None
    observacoes: Optional[str] = Field(default=None, max_length=1000)
    fotos: Optional[list[str]] = Field(default_factory=list)


class VistoriaRapidaCreate(BaseModel):
    imovel_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    estado_geral: Literal["bom", "regular", "ruim", "critico"]
    itens_checklist: Optional[dict] = Field(
        default_factory=dict,
        description="Checklist de vistoria: {item: bool} — ex: {'pintura': true, 'hidraulica': false}",
    )
    observacoes: Optional[str] = Field(default=None, max_length=2000)
    fotos: Optional[list[str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS coordinates using Haversine formula."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/checkin")
async def registrar_checkin(body: CheckinCreate, authorization: Optional[str] = Header(None)):
    """Registra um check-in GPS do corretor em campo."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["corretor_id"] = user.id

    result = db.table("checkins").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao registrar check-in")

    log_action(user.id, "checkin", "campo", result.data["id"],
               f"Check-in ({body.tipo}) em {body.latitude:.4f}, {body.longitude:.4f}")
    return success_response(result.data)


@router.get("/checkins")
async def listar_checkins(
    corretor_id: Optional[str] = Query(None, description="Filtrar por corretor"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de check-in"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """Lista check-ins com filtros opcionais."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("checkins").select("id", count="exact")
    if corretor_id:
        count_query = count_query.eq("corretor_id", corretor_id)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if data_inicio:
        count_query = count_query.gte("created_at", f"{data_inicio}T00:00:00")
    if data_fim:
        count_query = count_query.lte("created_at", f"{data_fim}T23:59:59")

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("checkins").select("*").order("created_at", desc=True)
    if corretor_id:
        query = query.eq("corretor_id", corretor_id)
    if tipo:
        query = query.eq("tipo", tipo)
    if data_inicio:
        query = query.gte("created_at", f"{data_inicio}T00:00:00")
    if data_fim:
        query = query.lte("created_at", f"{data_fim}T23:59:59")

    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()

    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("/vistoria-rapida")
async def vistoria_rapida(body: VistoriaRapidaCreate, authorization: Optional[str] = Header(None)):
    """Registra uma vistoria rápida em campo com checklist simplificado e fotos."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Create a check-in record
    checkin_data = {
        "corretor_id": user.id,
        "imovel_id": body.imovel_id,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "tipo": "vistoria",
        "observacoes": body.observacoes,
        "fotos": body.fotos or [],
    }
    checkin_result = db.table("checkins").insert(checkin_data).select().single().execute()

    # Store the inspection details in vistorias_rapidas table
    vistoria_data = {
        "corretor_id": user.id,
        "imovel_id": body.imovel_id,
        "checkin_id": checkin_result.data["id"] if checkin_result.data else None,
        "estado_geral": body.estado_geral,
        "itens_checklist": body.itens_checklist or {},
        "observacoes": body.observacoes,
        "fotos": body.fotos or [],
        "latitude": body.latitude,
        "longitude": body.longitude,
    }

    result = db.table("vistorias_rapidas").insert(vistoria_data).select().single().execute()
    if not result.data:
        # If vistorias_rapidas table doesn't exist yet, return checkin data
        logger.warning("vistorias_rapidas table may not exist; returning checkin data")
        return success_response(checkin_result.data)

    log_action(user.id, "vistoria_rapida", "campo", result.data["id"],
               f"Vistoria rápida no imóvel {body.imovel_id} — estado: {body.estado_geral}")

    return success_response({
        "vistoria": result.data,
        "checkin": checkin_result.data,
    })


@router.get("/proximos")
async def imoveis_proximos(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude atual do corretor"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude atual do corretor"),
    raio_km: float = Query(5.0, ge=0.1, le=50, description="Raio de busca em km"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de resultados"),
    authorization: Optional[str] = Header(None),
):
    """Retorna imóveis próximos à localização GPS atual do corretor."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch properties with coordinates
    result = db.table("ativos").select(
        "id, natureza, tipo_imovel, titulo_anuncio, valor, cidade, bairro, logradouro, "
        "numero, estado, latitude, longitude, quartos, area_privativa, fotos, status, finalidade"
    ).eq("status", "ativo").not_.is_("latitude", "null").not_.is_(
        "longitude", "null"
    ).execute()

    properties = result.data or []

    # Calculate distances and filter by radius
    nearby = []
    for prop in properties:
        prop_lat = float(prop.get("latitude", 0))
        prop_lng = float(prop.get("longitude", 0))
        if prop_lat == 0 and prop_lng == 0:
            continue
        distance = _haversine_distance(latitude, longitude, prop_lat, prop_lng)
        if distance <= raio_km:
            prop["distancia_km"] = round(distance, 2)
            nearby.append(prop)

    # Sort by distance (closest first)
    nearby.sort(key=lambda p: p["distancia_km"])

    return success_response(nearby[:limit])
