"""`/api/edicao-fotos/uploads` — resumable chunked upload of ONE photo (seed `resumable_uploads` seam).

Open -> part status -> PUT parts -> complete -> then `POST /lotes/{id}/fotos/de-upload` turns the assembled file into a
batch photo through the same validation as the multipart route. Tier `org`, member-gated like the rest of the module.
"""
from __future__ import annotations

from noctusai_lib.domain.resumable_uploads import create_resumable_upload_router

from app.modules.edicao_fotos.deps import get_upload_service, require_member

router = create_resumable_upload_router(
    get_auth_context=require_member,
    get_service=get_upload_service,
    prefix="/api/edicao-fotos/uploads",
)
