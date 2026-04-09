"""
Therapists Router — Directory listing, profile detail, profile update.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_user_client, get_user_role
from app.responses import paginated_response, success_response
from app.schemas.therapist import TherapistProfileUpdate
from app.services import therapist_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/therapists", tags=["Therapists"])


@router.get("")
async def list_therapists(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    busca: Optional[str] = Query(None),
    specialty: Optional[str] = Query(None),
    approach: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_rating: Optional[float] = Query(None, ge=1, le=5),
    clinic_id: Optional[str] = Query(None),
    sort: Optional[str] = Query("relevance"),
):
    """Therapist directory — public to all authenticated users.

    Filters: busca, specialty, approach, min_price, max_price, min_rating, clinic_id.
    Sort: relevance | highest_rated | most_reviewed | lowest_price.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    filters = {
        "busca": busca,
        "specialty": specialty,
        "approach": approach,
        "min_price": min_price,
        "max_price": max_price,
        "min_rating": min_rating,
        "clinic_id": clinic_id,
        "sort": sort,
    }
    data, total = await therapist_service.list_therapists_directory(
        filters=filters,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/{therapist_id}")
async def get_therapist(
    therapist_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get therapist profile detail with rating stats."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    result = await therapist_service.get_therapist_with_stats(therapist_id, db)
    return success_response(result)


@router.patch("/{therapist_id}")
async def update_therapist(
    therapist_id: str,
    body: TherapistProfileUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update own therapist profile. Only the therapist themselves can update."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    if role != "therapist" or user.id != therapist_id:
        raise HTTPException(
            status_code=403,
            detail="Você só pode editar seu próprio perfil",
        )

    db = get_user_client(token)
    result = await therapist_service.update_therapist_profile(
        user_id=therapist_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)
