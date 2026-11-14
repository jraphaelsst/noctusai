"""Upload-session store: Protocol + Fake + Supabase + factory. Sessions + append-only events."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Optional, Protocol

from .types import STATUS_OPEN, UploadSession

__all__ = [
    "SESSIONS_TABLE", "EVENTS_TABLE", "UploadSessionStore", "FakeUploadSessionStore",
    "SupabaseUploadSessionStore", "make_upload_session_store",
]

SESSIONS_TABLE = "upload_sessions"
EVENTS_TABLE = "upload_session_events"


class UploadSessionStore(Protocol):
    def insert(self, session: UploadSession) -> None: ...
    def get(self, org_id: str, session_id: str) -> Optional[UploadSession]: ...
    def find_open(self, org_id: str, user_id: Optional[str], client_key: str, now: datetime) -> Optional[UploadSession]: ...
    def transition(self, org_id: str, session_id: str, status: str, *, at: datetime, object_key: Optional[str] = None) -> None: ...
    def list_expired(self, now: datetime, limit: int = 100) -> list[UploadSession]: ...
    def add_event(self, org_id: str, session_id: str, kind: str, *, at: datetime, detail: Optional[dict] = None) -> None: ...


class FakeUploadSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, UploadSession] = {}
        self.events: list[dict[str, Any]] = []

    def insert(self, session: UploadSession) -> None:
        self.sessions[session.id] = session

    def get(self, org_id: str, session_id: str) -> Optional[UploadSession]:
        s = self.sessions.get(session_id)
        return s if s is not None and s.org_id == org_id else None

    def find_open(self, org_id, user_id, client_key, now):
        for s in self.sessions.values():
            if (s.org_id == org_id and s.user_id == user_id and s.client_key == client_key
                    and s.status == STATUS_OPEN and s.expires_at > now):
                return s
        return None

    def transition(self, org_id, session_id, status, *, at, object_key=None):
        s = self.get(org_id, session_id)
        if s is None:
            return
        self.sessions[session_id] = replace(
            s, status=status, object_key=object_key or s.object_key,
            completed_at=at if status == "completed" else s.completed_at)

    def list_expired(self, now, limit=100):
        return [s for s in self.sessions.values() if s.status == STATUS_OPEN and s.expires_at <= now][:limit]

    def add_event(self, org_id, session_id, kind, *, at, detail=None):
        self.events.append({"org_id": org_id, "session_id": session_id, "kind": kind, "at": at, "detail": detail or {}})


def _row(s: UploadSession) -> dict[str, Any]:
    return {
        "id": s.id, "org_id": s.org_id, "user_id": s.user_id, "filename": s.filename,
        "content_type": s.content_type, "size_bytes": s.size_bytes, "part_size": s.part_size,
        "total_parts": s.total_parts, "status": s.status, "client_key": s.client_key,
        "object_key": s.object_key, "created_at": s.created_at.isoformat(), "expires_at": s.expires_at.isoformat(),
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }


def _parse(v: Any) -> Optional[datetime]:
    return None if v is None else (v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00")))


def _from_row(r: dict[str, Any]) -> UploadSession:
    return UploadSession(
        id=str(r["id"]), org_id=str(r["org_id"]), user_id=None if r.get("user_id") is None else str(r["user_id"]),
        filename=r["filename"], content_type=r["content_type"], size_bytes=int(r["size_bytes"]),
        part_size=int(r["part_size"]), total_parts=int(r["total_parts"]), status=r["status"],
        created_at=_parse(r["created_at"]), expires_at=_parse(r["expires_at"]), client_key=r.get("client_key"),
        object_key=r.get("object_key"), completed_at=_parse(r.get("completed_at")))


class SupabaseUploadSessionStore:
    """Service-role client over `<schema>.upload_sessions` / `upload_session_events` (RLS: service only)."""

    def __init__(self, client: Any, schema: str = "public") -> None:
        self._client, self._schema = client, schema

    def _t(self, name: str) -> Any:
        return self._client.schema(self._schema).table(name)

    def insert(self, session: UploadSession) -> None:
        self._t(SESSIONS_TABLE).insert(_row(session)).execute()

    def get(self, org_id: str, session_id: str) -> Optional[UploadSession]:
        res = self._t(SESSIONS_TABLE).select("*").eq("id", session_id).eq("org_id", org_id).limit(1).execute()
        return _from_row(res.data[0]) if res.data else None

    def find_open(self, org_id, user_id, client_key, now):
        q = self._t(SESSIONS_TABLE).select("*").eq("org_id", org_id).eq("client_key", client_key).eq("status", STATUS_OPEN)
        q = q.eq("user_id", user_id) if user_id is not None else q.is_("user_id", "null")
        res = q.gt("expires_at", now.isoformat()).limit(1).execute()
        return _from_row(res.data[0]) if res.data else None

    def transition(self, org_id, session_id, status, *, at, object_key=None):
        patch: dict[str, Any] = {"status": status}
        if object_key:
            patch["object_key"] = object_key
        if status == "completed":
            patch["completed_at"] = at.isoformat()
        self._t(SESSIONS_TABLE).update(patch).eq("id", session_id).eq("org_id", org_id).execute()

    def list_expired(self, now, limit=100):
        res = (self._t(SESSIONS_TABLE).select("*").eq("status", STATUS_OPEN)
               .lte("expires_at", now.isoformat()).limit(limit).execute())
        return [_from_row(r) for r in res.data or []]

    def add_event(self, org_id, session_id, kind, *, at, detail=None):
        self._t(EVENTS_TABLE).insert({
            "org_id": org_id, "session_id": session_id, "kind": kind,
            "occurred_at": at.isoformat(), "detail": detail or {}}).execute()


def make_upload_session_store(*, kind: str = "fake", get_client: Optional[Callable[[], Any]] = None,
                              schema: str = "public") -> UploadSessionStore:
    if kind == "fake":
        return FakeUploadSessionStore()
    if kind == "supabase":
        if get_client is None:
            raise ValueError("make_upload_session_store(kind='supabase') requires get_client=")
        return SupabaseUploadSessionStore(get_client(), schema)
    raise ValueError(f"unsupported upload session store kind: {kind!r}")
