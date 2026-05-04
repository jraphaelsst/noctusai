"""Supabase Storage `StorageBackend`.

Wraps `supabase.storage.from_(bucket).{upload,download,remove,list,
create_signed_url}` from `storage3.SyncBucketProxy`. The SDK is sync;
we hop off the event loop with `asyncio.to_thread` to keep the public
async surface uniform.

Errors from `storage3` (network failures, 4xx/5xx responses) are
logged at WARN before re-raising — never silently swallowed (per the
no-silent-errors rule). 404 / "Not Found" specifically gets translated
to `None` / `False` for `get` / `delete` / `exists` so callers can
treat "missing" as a normal control-flow signal without try/except.

The wrapper does NOT manage bucket creation — operators create
buckets out-of-band via the Supabase dashboard or migration scripts.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.storage.types import BlobMetadata, StoredBlob

logger = logging.getLogger(__name__)


def _is_not_found(exc: Exception) -> bool:
    """Heuristic: detect "object not found" across `storage3` versions.

    `storage3.utils.StorageException` carries a dict-shaped `args[0]`
    in modern releases and a status_code in older ones. We sniff for
    `statusCode == "404"` / `error == "not_found"` / a 'not found'
    substring in the message — robust across SDK upgrades without
    importing version-specific exception classes.
    """
    try:
        first = exc.args[0] if exc.args else None
    except (IndexError, AttributeError):
        first = None
    if isinstance(first, dict):
        status_code = str(first.get("statusCode", "")).strip()
        if status_code in {"404", "400"}:
            # Supabase returns 400 for some "object not found" paths.
            err = str(first.get("error", "")).lower()
            message = str(first.get("message", "")).lower()
            if (
                "not_found" in err
                or "not found" in message
                or "object not found" in message
            ):
                return True
        if status_code == "404":
            return True
    text = str(exc).lower()
    return "not found" in text or "object not found" in text


class SupabaseStorageBackend:
    """Real Supabase Storage `StorageBackend`.

    Pass a configured `supabase.Client` (or any object exposing a
    `.storage.from_(bucket)` chain matching `storage3.SyncBucketProxy`).
    Buckets must exist server-side; the wrapper does NOT create them.

    The class holds no state beyond the client reference, so it's safe
    to instantiate per-request or share a singleton — whatever fits
    the consumer's wiring.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    # ---- Internal helpers --------------------------------------------

    def _bucket(self, bucket: str) -> Any:
        return self._client.storage.from_(bucket)

    # ---- StorageBackend surface --------------------------------------

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> BlobMetadata:
        # Supabase's `upload` rejects existing keys with a 409 unless we
        # pass `upsert="true"`. We ALWAYS upsert to match the contract
        # ("overwrites any existing blob at key"). `x-upsert` is the
        # documented option name; `upsert` (no prefix) is the legacy.
        file_options: dict[str, str] = {
            "content-type": content_type,
            "x-upsert": "true",
            "upsert": "true",
        }
        custom_metadata = dict(metadata or {})
        # Supabase Storage accepts a "metadata" file_option as JSON; the
        # storage3 typing only allows `str` values, so we serialize.
        # (Older SDK versions may ignore unknown keys — harmless.)
        if custom_metadata:
            try:
                import json as _json

                file_options["metadata"] = _json.dumps(custom_metadata)
            except (TypeError, ValueError) as exc:
                # Caller passed non-JSON-serializable metadata. Surface it.
                logger.warning(
                    "storage.supabase.metadata_serialize_failed bucket=%s key=%s err=%s",
                    bucket,
                    key,
                    exc,
                )
                raise

        try:
            await asyncio.to_thread(
                self._bucket(bucket).upload,
                key,
                data,
                file_options,
            )
        except Exception as exc:
            logger.warning(
                "storage.supabase.put_failed bucket=%s key=%s err=%s",
                bucket,
                key,
                exc,
            )
            raise

        return BlobMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            created_at=datetime.now(timezone.utc),
            custom_metadata=custom_metadata,
        )

    async def get(self, *, bucket: str, key: str) -> StoredBlob | None:
        try:
            data: bytes = await asyncio.to_thread(
                self._bucket(bucket).download, key
            )
        except Exception as exc:
            if _is_not_found(exc):
                return None
            logger.warning(
                "storage.supabase.get_failed bucket=%s key=%s err=%s",
                bucket,
                key,
                exc,
            )
            raise

        meta = BlobMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            # Supabase doesn't surface content-type on download; consumers
            # that need it should attach it as custom_metadata at put time
            # OR fetch it via `list` (which returns metadata blobs).
            content_type="application/octet-stream",
            created_at=datetime.now(timezone.utc),
            custom_metadata={},
        )
        return StoredBlob(metadata=meta, data=data)

    async def delete(self, *, bucket: str, key: str) -> bool:
        try:
            result = await asyncio.to_thread(
                self._bucket(bucket).remove, [key]
            )
        except Exception as exc:
            if _is_not_found(exc):
                return False
            logger.warning(
                "storage.supabase.delete_failed bucket=%s key=%s err=%s",
                bucket,
                key,
                exc,
            )
            raise

        # `remove` returns a list of metadata dicts for the keys it
        # actually removed. Empty list = nothing removed (i.e. the key
        # was already gone — the soft case our contract returns False for).
        if isinstance(result, list) and len(result) == 0:
            return False
        return True

    async def list_keys(
        self,
        *,
        bucket: str,
        prefix: str = "",
        limit: int = 100,
    ) -> list[str]:
        # storage3's `list(path=...)` lists items inside a "folder"
        # (path prefix UP TO the last /). For a true prefix filter that
        # matches keys at any depth we list the parent of the prefix and
        # filter client-side. Empty prefix → list bucket root.
        list_path: str | None
        if "/" in prefix:
            list_path = prefix.rsplit("/", 1)[0]
        else:
            list_path = None  # bucket root

        try:
            options: dict[str, Any] = {"limit": limit}
            items = await asyncio.to_thread(
                self._bucket(bucket).list, list_path, options
            )
        except Exception as exc:
            if _is_not_found(exc):
                return []
            logger.warning(
                "storage.supabase.list_failed bucket=%s prefix=%r err=%s",
                bucket,
                prefix,
                exc,
            )
            raise

        # Reconstruct the full key by joining the listed-folder path with
        # each item's `name`. `name` already has no leading slash.
        results: list[str] = []
        prefix_for_join = list_path + "/" if list_path else ""
        for item in items or []:
            name = item.get("name") if isinstance(item, dict) else None
            if not name:
                continue
            full_key = prefix_for_join + name
            if full_key.startswith(prefix):
                results.append(full_key)
        results.sort()
        return results[:limit]

    async def signed_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        try:
            response = await asyncio.to_thread(
                self._bucket(bucket).create_signed_url,
                key,
                expires_in_seconds,
            )
        except Exception as exc:
            logger.warning(
                "storage.supabase.signed_url_failed bucket=%s key=%s err=%s",
                bucket,
                key,
                exc,
            )
            raise

        # `create_signed_url` returns `{"signedURL": "...", ...}`. Older
        # SDKs used `signed_url` (snake_case); accept either.
        if isinstance(response, dict):
            url = response.get("signedURL") or response.get("signed_url")
            if isinstance(url, str) and url:
                return url
        raise RuntimeError(
            f"Unexpected create_signed_url response shape: {response!r}"
        )

    async def exists(self, *, bucket: str, key: str) -> bool:
        # Cheapest existence check: list at the key's parent and look
        # for the basename. `download` would also work but pulls bytes.
        if "/" in key:
            parent, basename = key.rsplit("/", 1)
        else:
            parent, basename = None, key
        try:
            items = await asyncio.to_thread(
                self._bucket(bucket).list, parent, {"limit": 100, "search": basename}
            )
        except Exception as exc:
            if _is_not_found(exc):
                return False
            logger.warning(
                "storage.supabase.exists_failed bucket=%s key=%s err=%s",
                bucket,
                key,
                exc,
            )
            raise

        for item in items or []:
            if isinstance(item, dict) and item.get("name") == basename:
                return True
        return False


__all__ = ["SupabaseStorageBackend"]
