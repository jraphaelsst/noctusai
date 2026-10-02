"""Private-bucket assets: the author photo + the product kit.

Bucket `store-produtos` is PRIVATE — nothing here ever returns a public URL;
bytes are served only through the backend (302 to a short-lived signed URL).
Layout (contract §1): `contrato-blindado/kit.zip`, `autor/foto.<ext>`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from noctusai_lib.integrations.storage.protocol import StorageBackend

BUCKET = "store-produtos"
KIT_KEY = "contrato-blindado/kit.zip"
PHOTO_PREFIX = "autor/"

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_KIT_BYTES = 50 * 1024 * 1024

#: content-type -> (extension, magic-number check). The client's declared
#: type is never trusted alone: the leading bytes must agree.
_PHOTO_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "image/jpeg": ("jpg", (b"\xff\xd8\xff",)),
    "image/png": ("png", (b"\x89PNG\r\n\x1a\n",)),
    "image/webp": ("webp", (b"RIFF",)),
}
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")


class AssetRejected(Exception):
    """The upload is not an acceptable file (HTTP 422 / 413)."""

    def __init__(self, detail: str, *, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class AssetService:
    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    # ── photo ────────────────────────────────────────────────────────────
    async def photo_key(self) -> Optional[str]:
        keys = await self._storage.list_keys(bucket=BUCKET, prefix=PHOTO_PREFIX, limit=10)
        return keys[0] if keys else None

    async def photo_signed_url(self, *, expires_in_seconds: int = 300) -> Optional[str]:
        key = await self.photo_key()
        if key is None:
            return None
        return await self._storage.signed_url(bucket=BUCKET, key=key, expires_in_seconds=expires_in_seconds)

    async def put_photo(self, data: bytes, content_type: str) -> str:
        spec = _PHOTO_TYPES.get((content_type or "").split(";")[0].strip().lower())
        if spec is None:
            raise AssetRejected("Envie uma imagem JPG, PNG ou WebP.")
        ext, magics = spec
        if len(data) > MAX_PHOTO_BYTES:
            raise AssetRejected("A foto deve ter no máximo 5 MB.", status_code=413)
        if not data.startswith(magics):
            raise AssetRejected("O arquivo não é uma imagem válida.")
        # Replace, never accumulate: drop any previous photo (other extension too).
        for old in await self._storage.list_keys(bucket=BUCKET, prefix=PHOTO_PREFIX, limit=20):
            await self._storage.delete(bucket=BUCKET, key=old)
        key = f"{PHOTO_PREFIX}foto.{ext}"
        await self._storage.put(bucket=BUCKET, key=key, data=data, content_type=content_type)
        return key

    # ── kit ──────────────────────────────────────────────────────────────
    async def kit_exists(self) -> bool:
        return await self._storage.exists(bucket=BUCKET, key=KIT_KEY)

    async def kit_info(self) -> dict[str, Any]:
        blob = await self._storage.get(bucket=BUCKET, key=KIT_KEY)
        if blob is None:
            return {"exists": False, "size": None, "updated_at": None}
        created: datetime = blob.metadata.created_at
        return {"exists": True, "size": blob.metadata.size, "updated_at": created.isoformat()}

    async def put_kit(self, data: bytes) -> None:
        if len(data) > MAX_KIT_BYTES:
            raise AssetRejected("O arquivo deve ter no máximo 50 MB.", status_code=413)
        if not data.startswith(_ZIP_MAGIC):
            raise AssetRejected("Envie um arquivo .zip válido.")
        await self._storage.put(bucket=BUCKET, key=KIT_KEY, data=data, content_type="application/zip")

    async def kit_signed_url(self, *, expires_in_seconds: int = 300) -> str:
        return await self._storage.signed_url(bucket=BUCKET, key=KIT_KEY, expires_in_seconds=expires_in_seconds)


__all__ = [
    "AssetRejected",
    "AssetService",
    "BUCKET",
    "KIT_KEY",
    "MAX_KIT_BYTES",
    "MAX_PHOTO_BYTES",
    "PHOTO_PREFIX",
]
