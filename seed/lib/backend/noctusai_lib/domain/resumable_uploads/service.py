"""ResumableUploadService: open -> part status -> put parts -> complete / abort / expire.

Chunks are stored as parts under `<prefix>/_parts/<session>/<n>` through the seed `StorageBackend` seam (so Fake /
Local / Supabase all work), then assembled into `<prefix>/<session>/<filename>`. The browser never holds a storage
credential: it talks only to our endpoints, and every session is bound to one org and one object prefix server-side.
`complete` assembles in memory, so `UploadPolicy.max_bytes` bounds it (default 500 MiB).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noctusai_lib.integrations.storage.protocol import StorageBackend

from .store import UploadSessionStore
from .types import (
    STATUS_ABORTED, STATUS_COMPLETED, STATUS_EXPIRED, STATUS_OPEN, PartInfo, PartInvalid, PartsMissing,
    UploadExpired, UploadNotFound, UploadNotOpen, UploadPolicy, UploadRejected, UploadSession, safe_filename,
)

__all__ = ["ResumableUploadService"]


class ResumableUploadService:
    def __init__(self, *, store: UploadSessionStore, storage: StorageBackend, bucket: str, prefix: str,
                 policy: Optional[UploadPolicy] = None, now_fn: Optional[Callable[[], datetime]] = None) -> None:
        self.store, self.storage, self.bucket = store, storage, bucket
        self.prefix = prefix.strip("/")
        self.policy = policy or UploadPolicy()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    # -- keys (server-derived; never from the client) -------------------------------------------------------------
    def _base(self, s: UploadSession) -> str:
        return f"{self.prefix}/{s.org_id}"

    def _part_key(self, s: UploadSession, n: int) -> str:
        return f"{self._base(s)}/_parts/{s.id}/{n:06d}"

    def _load(self, org_id: str, session_id: str) -> UploadSession:
        s = self.store.get(org_id, session_id)
        if s is None:  # another org's session is a 404, never a 403
            raise UploadNotFound()
        return s

    def _require_open(self, s: UploadSession) -> None:
        if s.status != STATUS_OPEN:
            raise UploadNotOpen(status=s.status)
        if s.expires_at <= self._now():
            raise UploadExpired()

    # -- lifecycle -----------------------------------------------------------------------------------------------
    def open(self, *, org_id: str, user_id: Optional[str], filename: str, content_type: str, size_bytes: int,
             client_key: Optional[str] = None, part_size: Optional[int] = None) -> UploadSession:
        p, now = self.policy, self._now()
        if size_bytes <= 0:
            raise UploadRejected("arquivo vazio")
        if size_bytes > p.max_bytes:
            raise UploadRejected("arquivo acima do limite", max_bytes=p.max_bytes)
        if not p.type_allowed(content_type):
            raise UploadRejected("tipo de arquivo nao permitido", content_type=content_type)
        if client_key:  # resume after a reload: same file -> same session
            existing = self.store.find_open(org_id, user_id, client_key, now)
            if existing is not None and existing.size_bytes == size_bytes:
                return existing
        size = min(max(part_size or p.part_size, p.min_part_size), p.max_part_size)
        total = -(-size_bytes // size)
        if total > p.max_parts:
            size = -(-size_bytes // p.max_parts)
            total = -(-size_bytes // size)
            if size > p.max_part_size:
                raise UploadRejected("arquivo acima do limite de partes")
        s = UploadSession(
            id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, filename=safe_filename(filename),
            content_type=content_type, size_bytes=size_bytes, part_size=size, total_parts=total,
            status=STATUS_OPEN, created_at=now, expires_at=now + timedelta(seconds=p.ttl_s), client_key=client_key)
        self.store.insert(s)
        self.store.add_event(org_id, s.id, "opened", at=now, detail={"size_bytes": size_bytes, "total_parts": total})
        return s

    async def received_parts(self, s: UploadSession) -> list[PartInfo]:
        """Parts the server HAS (existence == exact size, enforced at put) -- the source of truth for resume."""
        keys = await self.storage.list_keys(bucket=self.bucket, prefix=f"{self._base(s)}/_parts/{s.id}/",
                                            limit=s.total_parts + 1)
        nums = sorted(int(k.rsplit("/", 1)[-1]) for k in keys)
        return [PartInfo(number=n, size=s.part_len(n)) for n in nums]

    async def status(self, *, org_id: str, session_id: str) -> tuple[UploadSession, list[PartInfo]]:
        s = self._load(org_id, session_id)
        if s.status != STATUS_OPEN:
            return s, []
        return s, await self.received_parts(s)

    async def put_part(self, *, org_id: str, session_id: str, number: int, data: bytes) -> PartInfo:
        s = self._load(org_id, session_id)
        self._require_open(s)
        if not 1 <= number <= s.total_parts:
            raise PartInvalid("numero de parte fora do intervalo", total_parts=s.total_parts)
        if len(data) != s.part_len(number):
            raise PartInvalid("tamanho da parte diferente do esperado", expected=s.part_len(number), got=len(data))
        await self.storage.put(bucket=self.bucket, key=self._part_key(s, number), data=data,
                               content_type="application/octet-stream")
        return PartInfo(number=number, size=len(data))

    async def complete(self, *, org_id: str, session_id: str) -> UploadSession:
        s = self._load(org_id, session_id)
        if s.status == STATUS_COMPLETED:  # idempotent retry of a lost response
            return s
        self._require_open(s)
        have = {p.number for p in await self.received_parts(s)}
        missing = [n for n in range(1, s.total_parts + 1) if n not in have]
        if missing:
            raise PartsMissing("partes faltando", missing=missing)
        chunks = []
        for n in range(1, s.total_parts + 1):
            blob = await self.storage.get(bucket=self.bucket, key=self._part_key(s, n))
            if blob is None:
                raise PartsMissing("parte sumiu durante a montagem", missing=[n])
            chunks.append(blob.data)
        data = b"".join(chunks)
        if len(data) != s.size_bytes:
            raise PartInvalid("tamanho final diferente do declarado", expected=s.size_bytes, got=len(data))
        object_key = f"{self._base(s)}/{s.id}/{s.filename}"
        await self.storage.put(bucket=self.bucket, key=object_key, data=data, content_type=s.content_type)
        await self._drop_parts(s)
        now = self._now()
        self.store.transition(org_id, s.id, STATUS_COMPLETED, at=now, object_key=object_key)
        self.store.add_event(org_id, s.id, "completed", at=now, detail={"size_bytes": s.size_bytes})
        return self._load(org_id, s.id)

    async def read(self, *, org_id: str, session_id: str) -> bytes:
        """Bytes of a COMPLETED session (server-side consumers, e.g. the pilot ingesting a photo)."""
        s = self._load(org_id, session_id)
        if s.status != STATUS_COMPLETED or not s.object_key:
            raise UploadNotOpen(status=s.status)
        blob = await self.storage.get(bucket=self.bucket, key=s.object_key)
        if blob is None:
            raise UploadNotFound()
        return blob.data

    async def consume(self, *, org_id: str, session_id: str) -> tuple[UploadSession, bytes]:
        """`read` + delete the assembled object: a server-side consumer takes ownership of the bytes (no orphan copy)."""
        s = self._load(org_id, session_id)
        data = await self.read(org_id=org_id, session_id=session_id)
        await self.storage.delete(bucket=self.bucket, key=s.object_key or "")
        return s, data

    async def abort(self, *, org_id: str, session_id: str) -> None:
        s = self._load(org_id, session_id)
        if s.status != STATUS_OPEN:
            return
        await self._drop_parts(s)
        now = self._now()
        self.store.transition(org_id, s.id, STATUS_ABORTED, at=now)
        self.store.add_event(org_id, s.id, "aborted", at=now)

    async def expire_stale(self, limit: int = 100) -> int:
        """Scheduler entry point: drop parts of open sessions past `expires_at`, mark + record `expired`."""
        n = 0
        for s in self.store.list_expired(self._now(), limit):
            await self._drop_parts(s)
            now = self._now()
            self.store.transition(s.org_id, s.id, STATUS_EXPIRED, at=now)
            self.store.add_event(s.org_id, s.id, "expired", at=now)
            n += 1
        return n

    async def _drop_parts(self, s: UploadSession) -> None:
        for k in await self.storage.list_keys(bucket=self.bucket, prefix=f"{self._base(s)}/_parts/{s.id}/",
                                              limit=s.total_parts + 1):
            await self.storage.delete(bucket=self.bucket, key=k)
