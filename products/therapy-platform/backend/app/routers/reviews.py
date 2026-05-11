"""
Reviews Router — Therapist reviews, clinic reviews, responses, flags.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_admin_client,
    get_current_user,
    get_user_client,
    get_user_role,
    get_clinic_id_for_user,
)
from app.responses import paginated_response, success_response
from app.schemas.review import (
    ReviewCreate,
    ReviewUpdate,
    ClinicReviewCreate,
    ReviewResponseCreate,
    ReviewFlagRequest,
)
from app.services import review_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["Reviews"])


@router.post("")
async def create_review(
    body: ReviewCreate,
    authorization: Optional[str] = Header(None),
):
    """Create a therapist review (patient only, must have completed session)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem avaliar terapeutas")

    db = get_user_client(token)
    result = await review_service.create_review(
        patient_id=user.id,
        data=body.model_dump(),
        db=db,
    )
    return success_response(result)


@router.patch("/{review_id}")
async def update_review(
    review_id: str,
    body: ReviewUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update own review (patient only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem editar avaliações")

    db = get_user_client(token)
    result = await review_service.update_review(
        review_id=review_id,
        patient_id=user.id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)


@router.get("/therapist/{therapist_id}")
async def list_therapist_reviews(
    therapist_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List reviews for a therapist (public to authenticated users)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data, total = await review_service.list_therapist_reviews(
        therapist_id=therapist_id,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/clinic")
async def create_clinic_review(
    body: ClinicReviewCreate,
    authorization: Optional[str] = Header(None),
):
    """Create a clinic review (patient only, must have session with clinic therapist)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem avaliar clínicas")

    db = get_user_client(token)
    result = await review_service.create_clinic_review(
        patient_id=user.id,
        data=body.model_dump(),
        db=db,
    )
    return success_response(result)


@router.get("/clinic/{clinic_id}")
async def list_clinic_reviews(
    clinic_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List reviews for a clinic (public to authenticated users)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data, total = await review_service.list_clinic_reviews(
        clinic_id=clinic_id,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/patient/{patient_id}")
async def list_patient_reviews(
    patient_id: str,
    authorization: Optional[str] = Header(None),
):
    """List reviews authored by a patient + completed-but-unreviewed CTAs.

    Returns the patient-portal `usePatientReviews` shape — the union of the
    caller's therapist and clinic reviews, each enriched with `entity_name` +
    `entity_type`, plus a `pending` list of completed appointments without
    reviews. Patients can only read their own reviews; admins can read any.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role == "patient" and user.id != patient_id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para acessar avaliações de outro paciente",
        )
    if role not in ("patient", "platform_admin"):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para acessar avaliações de paciente",
        )

    db = get_user_client(token)
    admin_db = get_admin_client()
    payload = await review_service.list_patient_reviews(
        patient_id=patient_id,
        db=db,
        admin_db=admin_db,
    )
    return payload


@router.delete("/{review_id}")
async def delete_review(
    review_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete own review (patient only).

    Looks across `reviews` and `clinic_reviews`; patient ownership is enforced
    by the row's `patient_id` column matching the caller.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Apenas pacientes podem remover suas próprias avaliações",
        )

    db = get_user_client(token)
    result = await review_service.delete_review(
        review_id=review_id,
        patient_id=user.id,
        db=db,
    )
    return success_response(result)


@router.post("/{review_id}/respond")
async def respond_to_review(
    review_id: str,
    body: ReviewResponseCreate,
    authorization: Optional[str] = Header(None),
):
    """Respond to a review (therapist only, for own reviews)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem responder avaliações")

    db = get_user_client(token)
    result = await review_service.create_review_response(
        review_id=review_id,
        responder_id=user.id,
        response_text=body.response_text,
        db=db,
    )
    return success_response(result)


@router.post("/{review_id}/flag")
async def flag_review(
    review_id: str,
    body: ReviewFlagRequest,
    authorization: Optional[str] = Header(None),
):
    """Flag a review for moderation.

    Therapists can flag reviews on their profiles.
    Clinic admins can flag clinic reviews.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(
            status_code=403,
            detail="Apenas terapeutas, clínicas ou admins podem sinalizar avaliações",
        )

    db = get_user_client(token)
    result = await review_service.flag_review(
        review_id=review_id,
        flagged_by=user.id,
        reason=body.reason,
        db=db,
    )
    return success_response(result)
