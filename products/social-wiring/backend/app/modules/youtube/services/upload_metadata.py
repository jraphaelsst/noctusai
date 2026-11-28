"""Product code -> YouTube upload metadata, resolved against the LOCAL property catalog.

One derivation shared by every entry point that only knows a property code: the dashboard's
`/upload/from-code` + `/drive-folder` routes (which translate the errors below to 422 / 404 / 502) and
Julia's "Vídeos Prontos" group intake (`app.services.julia_videos_prontos_service`), which turns them into
a submission outcome. Moved out of `modules/youtube/routers/upload.py` so a non-HTTP caller never has to
catch an `HTTPException`.

Resolves against `social_wiring.imoveis` -- never a live Vista call. No fallback branch on a miss (roadmap
`social-wiring-imoveis-vista-2026-08`, P2.5): a code not in the local catalog is real information.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.youtube.schemas.upload import UploadMetadata


class UploadMetadataError(Exception):
    """Base class: the code could not be turned into upload metadata."""


class InvalidProductCode(UploadMetadataError):
    """The code does not have the canonical shape (`validate_product_code`)."""

    def __init__(self, code: str) -> None:
        super().__init__(f"invalid product_code format: {code!r}")
        self.code = code


class PropertyNotFound(UploadMetadataError):
    """The code is valid, but the local catalog has no property for it."""

    def __init__(self, code: str) -> None:
        super().__init__(f"no property found for product_code={code} in local catalog")
        self.code = code


class MetadataLookupFailed(UploadMetadataError):
    """The local lookup itself failed (DB / transport problem)."""


def resolve_metadata_from_product_code(
    admin_client: Any, *, product_code: str, privacy_status: str, org_id: UUID,
) -> UploadMetadata:
    """Local-catalog lookup -> `UploadMetadata` (title / description / tags from `build_youtube_metadata`).

    Raises `InvalidProductCode`, `PropertyNotFound` or `MetadataLookupFailed` (all `UploadMetadataError`)."""
    from noctusai_lib.domain.real_estate import build_youtube_metadata, validate_product_code

    from app.services.imoveis_service import ImoveisLookupError, build_imoveis_service

    code = (product_code or "").strip().upper()
    if not validate_product_code(code):
        raise InvalidProductCode(code)
    try:
        prop = build_imoveis_service(admin_client).get_property_data(org_id, code)
    except ImoveisLookupError as exc:
        raise MetadataLookupFailed(f"local imoveis lookup failed: {exc}") from exc
    if prop is None:
        raise PropertyNotFound(code)

    yt_meta = build_youtube_metadata(prop, code)
    return UploadMetadata(
        title=yt_meta["title"],
        description=yt_meta["description"],
        tags=yt_meta["tags"],
        privacy_status=privacy_status,
        category_id="22",
        notify_recipients=[],
        product_code=code,
    )


__all__ = [
    "InvalidProductCode", "MetadataLookupFailed", "PropertyNotFound", "UploadMetadataError",
    "resolve_metadata_from_product_code",
]
