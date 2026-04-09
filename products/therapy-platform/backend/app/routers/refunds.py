"""
Refund Router — Submit, list, and review refund requests.

- Patients submit refund requests (feature-flag controlled)
- Patients see their own requests
- Platform admins see all requests and can approve/deny
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_user_role, get_admin_client
from app.responses import paginated_response, success_response
from app.schemas.financial import RefundRequestCreate, RefundReviewRequest
from app.services import refund_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/refunds", tags=["Refunds"])


@router.post("/")
async def create_refund_request(
    body: RefundRequestCreate,
    authorization: Optional[str] = Header(None),
):
    """Patient submits a refund request. Feature-flag controlled."""
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem solicitar reembolso")

    db = get_admin_client()
    result = await refund_service.create_refund_request(
        patient_id=user.id,
        transaction_id=body.transaction_id,
        reason=body.reason,
        db=db,
    )
    return success_response(result)


@router.get("/")
async def list_refund_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List refund requests. Admin sees all, patient sees own."""
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_admin_client()

    filters: dict = {}
    if status:
        filters["status"] = status

    if role == "patient":
        filters["patient_id"] = user.id
    elif role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    data, total = await refund_service.list_refund_requests(filters, page, page_size, db)
    return paginated_response(data, total, page, page_size)


@router.patch("/{refund_id}")
async def review_refund(
    refund_id: str,
    body: RefundReviewRequest,
    authorization: Optional[str] = Header(None),
):
    """Admin reviews (approves/denies) a refund request."""
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da plataforma")

    db = get_admin_client()
    result = await refund_service.review_refund(
        refund_id=refund_id,
        admin_id=user.id,
        action=body.action,
        response=body.response,
        db=db,
    )
    return success_response(result)
