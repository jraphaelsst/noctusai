"""Dashboard de criação (geracao-contract.md §4.7, endpoint 49)."""
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.services.dashboard_criacao_service import (
    DashboardCriacaoService,
    DashboardError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation", tags=["Media Creation — Dashboard"])


def get_dashboard_storage() -> StorageBackend:
    """Blob storage used only to sign viral thumbnails. Tests override with a ``FakeStorageBackend``."""
    return get_cerebro_storage()


@router.get("/dashboard")
async def get_dashboard(
    marca_id: uuid.UUID,
    historico_ordem: Literal["data_desc", "data_asc", "tipo"] = "data_desc",
    auth=Depends(get_current_user_org),
    storage: StorageBackend = Depends(get_dashboard_storage),
):
    user, _, org_id = auth
    try:
        return success_response(
            await DashboardCriacaoService(get_admin_client(), org_id, storage).dashboard(str(marca_id), historico_ordem, user)
        )
    except DashboardError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
