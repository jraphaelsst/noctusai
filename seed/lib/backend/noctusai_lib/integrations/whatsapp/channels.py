"""WhatsApp CHANNEL (newsletter) publishing through WAHA -- one-way posts, no member messages, no phone exposure.

A channel id ends ``@newsletter``. Only the line's account may post, and only to a channel it OWNS or ADMINS
(``role`` in ``OWNER|ADMIN`` from ``GET /api/{session}/channels``). Posting is a WhatsApp WRITE: it goes through the
client's single chokepoint (``WahaClient._request``), so the LINE POLICY (``send: enabled`` required, fail-closed,
refusal recorded as ``whatsapp.line.write_refused``) and the shared ``"whatsapp"`` rate-limit bucket apply with NO
bypass. ``post_*`` additionally pre-checks the policy so a refusal happens BEFORE any channel lookup.

WAHA channel support matrix (https://waha.devlike.pro/docs/how-to/channels/, read 2026-11-13). Our engine is NOWEB
(``deploy/fleet/waha-instances.yml``). NOWEB: list channels YES; get channel by id/invite YES; create YES; delete YES;
get messages YES (WAHA issue #433); send text YES; send image YES; send video YES; send poll NO (any engine);
receive text/media YES; follow/unfollow NO; mute/unmute NO; channel admin (revoke/invite/demote) NO (any engine).
``linkPreview`` is NOT documented for channel posts: it is sent only when the caller sets it explicitly, and the
result carries ``link_preview_requested`` so the caller knows it was a request, not a verified effect.
This module wraps list + send text + send image only; any other op raises :class:`ChannelEngineUnsupported`.

Inbound stays ignored: ``@newsletter`` chats are dropped by ``inbox/ingest.py``.
KB § CONTEXT/INTEGRATIONS/whatsapp.md.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from noctusai_lib.integrations.whatsapp.line_policy import seg

CHANNEL_SUFFIX = "@newsletter"
POSTING_ROLES = ("OWNER", "ADMIN")

#: engine -> operations WAHA documents as supported for channels.
ENGINE_SUPPORT: dict[str, frozenset[str]] = {
    "NOWEB": frozenset({"list", "get", "create", "delete", "send_text", "send_image", "send_video"}),
    "WEBJS": frozenset({"list", "get", "send_text", "send_image", "send_video"}),
    "GOWS": frozenset({"list", "get", "create", "send_text", "send_image", "send_video"}),
}


class ChannelError(RuntimeError):
    """Base for typed channel failures."""


class ChannelEngineUnsupported(ChannelError):
    def __init__(self, engine: str, op: str):
        self.engine, self.op = engine, op
        super().__init__(f"WAHA engine {engine} does not support channel operation {op!r}")


class ChannelIdInvalid(ChannelError):
    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        super().__init__(f"channel id must end with {CHANNEL_SUFFIX}: {channel_id!r}")


class ChannelNotPostable(ChannelError):
    """The channel is not among the line's channels, or its role is not OWNER/ADMIN."""

    def __init__(self, channel_id: str, role: Optional[str]):
        self.channel_id, self.role = channel_id, role
        super().__init__(
            f"channel {channel_id} is not postable by this line (role={role!r}; need one of {POSTING_ROLES})")


class ChannelApiError(ChannelError):
    def __init__(self, op: str, status: Optional[int], detail: str = ""):
        self.op, self.status, self.detail = op, status, detail[:200]
        super().__init__(f"channel {op} failed (HTTP {status}): {self.detail}")


@dataclass(frozen=True)
class WahaChannel:
    id: str
    name: str
    role: str
    description: str = ""
    invite: Optional[str] = None
    verified: bool = False

    @property
    def postable(self) -> bool:
        return self.role in POSTING_ROLES


def channel_from_payload(item: dict[str, Any]) -> WahaChannel:
    return WahaChannel(
        id=str(item.get("id") or ""), name=str(item.get("name") or ""), role=str(item.get("role") or "").upper(),
        description=str(item.get("description") or ""), invite=item.get("invite"),
        verified=bool(item.get("verified", False)))


def require_channel_id(channel_id: str) -> str:
    if not isinstance(channel_id, str) or not channel_id.endswith(CHANNEL_SUFFIX) \
            or len(channel_id) <= len(CHANNEL_SUFFIX):
        raise ChannelIdInvalid(str(channel_id))
    return channel_id


class _HttpBackend:
    """Real transport: rides the client's ``_request`` chokepoint (line policy + rate limit + redaction)."""

    def __init__(self, client: Any):
        self._c = client

    async def list_raw(self) -> list[dict[str, Any]]:
        r = await self._c._request("get", f"/api/{seg(self._c.session)}/channels", timeout=15,
                                   headers=self._c._headers())
        if r.status_code >= 400:
            raise ChannelApiError("list", r.status_code, r.text)
        body = r.json()
        return body if isinstance(body, list) else []

    async def post(self, path: str, body: dict[str, Any], op: str) -> dict[str, Any]:
        r = await self._c._request("post", path, timeout=30, json=body, headers=self._c._headers(json=True))
        if r.status_code >= 400:
            raise ChannelApiError(op, r.status_code, r.text)
        return r.json()


class WahaChannels:
    """Channel publisher over a ``WahaClient`` or ``FakeWahaClient`` (the Fake exposes ``channel_backend``)."""

    def __init__(self, client: Any, *, engine: str = "NOWEB", cache_ttl_s: float = 300.0):
        self._client = client
        self.engine = engine.upper()
        self._backend = getattr(client, "channel_backend", None) or _HttpBackend(client)
        self._ttl = cache_ttl_s
        self._cache: Optional[tuple[float, list[WahaChannel]]] = None

    def _require_engine(self, op: str) -> None:
        if op not in ENGINE_SUPPORT.get(self.engine, frozenset()):
            raise ChannelEngineUnsupported(self.engine, op)

    def _guard(self, path: str) -> None:
        # No bypass: the same guard the transport applies, run FIRST so a send-disabled line refuses before any lookup.
        self._client._guard_write("post", path)

    async def list_channels(self, *, refresh: bool = False) -> list[WahaChannel]:
        self._require_engine("list")
        now = time.monotonic()
        if not refresh and self._cache and now - self._cache[0] < self._ttl:
            return list(self._cache[1])
        chans = [channel_from_payload(i) for i in await self._backend.list_raw()]
        self._cache = (now, chans)
        return list(chans)

    async def list_postable(self, *, refresh: bool = False) -> list[WahaChannel]:
        return [c for c in await self.list_channels(refresh=refresh) if c.postable]

    async def validate_channel(self, channel_id: str, *, refresh: bool = False) -> WahaChannel:
        """Bind check: id shape + the line owns/admins it. Raises typed errors; never returns an unpostable channel."""
        require_channel_id(channel_id)
        for c in await self.list_channels(refresh=refresh):
            if c.id == channel_id:
                if not c.postable:
                    raise ChannelNotPostable(channel_id, c.role)
                return c
        raise ChannelNotPostable(channel_id, None)

    async def post_text(self, channel_id: str, text: str, *, link_preview: Optional[bool] = None) -> dict[str, Any]:
        self._require_engine("send_text")
        require_channel_id(channel_id)
        self._guard("/api/sendText")
        await self.validate_channel(channel_id)
        body: dict[str, Any] = {"session": self._client.session, "chatId": channel_id, "text": text}
        if link_preview is not None:
            body["linkPreview"] = bool(link_preview)
        out = await self._backend.post("/api/sendText", body, "send_text")
        return {**out, "link_preview_requested": link_preview}

    async def post_image(self, channel_id: str, image_url: str, *, caption: str = "",
                         mimetype: str = "image/jpeg", filename: str = "image.jpg") -> dict[str, Any]:
        self._require_engine("send_image")
        require_channel_id(channel_id)
        if not image_url.startswith("https://"):
            raise ChannelError("channel image url must be https")
        self._guard("/api/sendImage")
        await self.validate_channel(channel_id)
        body: dict[str, Any] = {"session": self._client.session, "chatId": channel_id,
                                "file": {"mimetype": mimetype, "url": image_url, "filename": filename}}
        if caption:
            body["caption"] = caption
        return await self._backend.post("/api/sendImage", body, "send_image")

    async def post_video(self, *_: Any, **__: Any) -> dict[str, Any]:  # not wrapped yet: explicit, never silent
        raise ChannelEngineUnsupported(self.engine, "send_video (not wrapped by this module)")

    async def create_channel(self, *_: Any, **__: Any) -> dict[str, Any]:
        raise ChannelEngineUnsupported(self.engine, "create (not wrapped by this module)")


def get_channel_publisher(client: Any, *, engine: str = "NOWEB") -> WahaChannels:
    return WahaChannels(client, engine=engine)
