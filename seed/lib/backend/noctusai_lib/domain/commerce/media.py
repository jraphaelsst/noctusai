"""Product media -- images and videos in a PRIVATE bucket, served as signed URLs.

Nothing here ever returns a public URL. Object keys are
`<org_id>/products/<product_id>/<media_id>.<ext>` so the bucket's per-org object
RLS (`private_org_bucket_sql`) and the service-layer org filter agree. The
client's declared content type is never trusted alone: the leading bytes must
match (store `assets.py` precedent).

HOST NOTE: the upload route is an `UploadFile` route, so the host product MUST
list `MEDIA_UPLOAD_PATH_PATTERN` in its `max_body_path_overrides` (the 1 MB
webhook default 413s any real photo, silently, in prod only):
`{MEDIA_UPLOAD_PATH_PATTERN: MEDIA_UPLOAD_MAX_BYTES}`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.integrations.storage.protocol import StorageBackend

from ._common import first, get_row, new_id, now_iso, tbl
from .catalog import get_product
from .config import CommerceConfig
from .errors import CommerceError, invalid, not_found
from .types import MediaKind

logger = logging.getLogger(__name__)

_MEDIA = "commerce_media"

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
MAX_MEDIA_PER_PRODUCT = 30
MEDIA_UPLOAD_PATH_PATTERN = "/api/commerce/products/*/media"
MEDIA_UPLOAD_MAX_BYTES = MAX_VIDEO_BYTES + 1024 * 1024  # multipart framing headroom

#: content-type -> (kind, extension, magic-number predicate)
_TYPES: dict[str, tuple[MediaKind, str]] = {
    "image/jpeg": (MediaKind.IMAGE, "jpg"),
    "image/png": (MediaKind.IMAGE, "png"),
    "image/webp": (MediaKind.IMAGE, "webp"),
    "video/mp4": (MediaKind.VIDEO, "mp4"),
    "video/webm": (MediaKind.VIDEO, "webm"),
}


def _magic_ok(content_type: str, data: bytes) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if content_type == "video/mp4":
        return data[4:8] == b"ftyp"
    if content_type == "video/webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    return False


def validate_upload(content_type: str, data: bytes) -> tuple[MediaKind, str]:
    """`(kind, extension)` for an acceptable upload, else a 422/413 `CommerceError`."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    spec = _TYPES.get(ctype)
    if spec is None:
        raise invalid("file", "Envie uma imagem (JPG, PNG, WebP) ou um vídeo (MP4, WebM).", code="midia_invalida")
    kind, ext = spec
    limit = MAX_IMAGE_BYTES if kind is MediaKind.IMAGE else MAX_VIDEO_BYTES
    if len(data) > limit:
        raise CommerceError(
            "midia_grande_demais", f"O arquivo deve ter no máximo {limit // (1024 * 1024)} MB.", 413
        )
    if not _magic_ok(ctype, data):
        raise invalid("file", "O arquivo não corresponde ao tipo informado.", code="midia_invalida")
    return kind, ext


def _storage_key(org_id: Any, product_id: Any, media_id: str, ext: str) -> str:
    return f"{org_id}/products/{product_id}/{media_id}.{ext}"


async def add_media(
    db: Any,
    storage: StorageBackend,
    cfg: CommerceConfig,
    org_id: Any,
    product_id: Any,
    *,
    content_type: str,
    data: bytes,
    alt: str = "",
) -> dict:
    get_product(db, org_id, product_id)
    kind, ext = validate_upload(content_type, data)
    existing = paged_rows(db, _MEDIA, org_id, eq_filters={"product_id": str(product_id)})
    if len(existing) >= MAX_MEDIA_PER_PRODUCT:
        raise CommerceError("midia_limite", f"Máximo de {MAX_MEDIA_PER_PRODUCT} mídias por produto.", 422)
    media_id = new_id()
    key = _storage_key(org_id, product_id, media_id, ext)
    await storage.put(bucket=cfg.bucket, key=key, data=data, content_type=content_type.split(";")[0].strip())
    row = {
        "id": media_id,
        "org_id": str(org_id),
        "product_id": str(product_id),
        "storage_path": key,
        "kind": kind.value,
        "alt": alt or "",
        "position": max((int(r.get("position", 0)) for r in existing), default=-1) + 1,
        "created_at": now_iso(),
    }
    try:
        saved = first(tbl(db, _MEDIA).insert(row).execute()) or row
    except Exception:
        logger.warning("commerce media row insert failed; removing the orphan object %s", key)
        await storage.delete(bucket=cfg.bucket, key=key)
        raise
    return await with_url(storage, cfg, saved)


async def delete_media(
    db: Any, storage: StorageBackend, cfg: CommerceConfig, org_id: Any, product_id: Any, media_id: Any
) -> None:
    row = get_row(db, _MEDIA, org_id, media_id)
    if row is None or str(row["product_id"]) != str(product_id):
        raise not_found("Mídia")
    tbl(db, _MEDIA).delete().eq("org_id", str(org_id)).eq("id", str(media_id)).execute()
    await storage.delete(bucket=cfg.bucket, key=row["storage_path"])


async def delete_objects(storage: StorageBackend, cfg: CommerceConfig, rows: list[dict]) -> None:
    for row in rows:
        await storage.delete(bucket=cfg.bucket, key=row["storage_path"])


async def with_url(storage: StorageBackend, cfg: CommerceConfig, row: dict) -> dict:
    """The media row with a short-TTL signed `url` (and without the raw storage path)."""
    url: Optional[str] = await storage.signed_url(
        bucket=cfg.bucket, key=row["storage_path"], expires_in_seconds=cfg.signed_url_ttl_seconds
    )
    public = {k: v for k, v in row.items() if k != "storage_path"}
    public["url"] = url
    return public


async def list_media(db: Any, storage: StorageBackend, cfg: CommerceConfig, org_id: Any, product_id: Any) -> list[dict]:
    rows = paged_rows(db, _MEDIA, org_id, eq_filters={"product_id": str(product_id)})
    rows.sort(key=lambda r: (r.get("position", 0), str(r["id"])))
    return [await with_url(storage, cfg, r) for r in rows]


__all__ = [
    "MAX_IMAGE_BYTES",
    "MAX_MEDIA_PER_PRODUCT",
    "MAX_VIDEO_BYTES",
    "MEDIA_UPLOAD_MAX_BYTES",
    "MEDIA_UPLOAD_PATH_PATTERN",
    "add_media",
    "delete_media",
    "delete_objects",
    "list_media",
    "validate_upload",
    "with_url",
]
