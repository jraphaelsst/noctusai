"""Tests for ``app/clients/social_wiring.py`` (contract §E.6).

The Fake covers the two seams routers actually depend on:
``get_one_chat_state`` / ``set_one_chat_auto_reply`` raising
``SocialWiringUnreachable`` on failure. The Real (``HttpSocialWiringClient``)
is exercised against a stub ASGI app via `httpx.ASGITransport` — no network,
no real social-wiring process, per seed-fake-real-adapter conventions.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.clients.social_wiring import (
    FakeSocialWiringClient,
    HttpSocialWiringClient,
    SocialWiringUnreachable,
    get_social_wiring_client,
)


class TestFakeSocialWiringClient:
    @pytest.mark.asyncio
    async def test_unregistered_connection_unreachable(self):
        client = FakeSocialWiringClient()
        with pytest.raises(SocialWiringUnreachable):
            await client.get_one_chat_state(uuid4())

    @pytest.mark.asyncio
    async def test_register_then_read(self):
        client = FakeSocialWiringClient()
        connection_id = uuid4()
        client.register(connection_id, auto_reply_enabled=True)
        state = await client.get_one_chat_state(connection_id)
        assert state["auto_reply_enabled"] is True

    @pytest.mark.asyncio
    async def test_toggle_updates_state(self):
        client = FakeSocialWiringClient()
        connection_id = uuid4()
        client.register(connection_id, auto_reply_enabled=False)
        result = await client.set_one_chat_auto_reply(connection_id, True)
        assert result == {"connection_id": str(connection_id), "auto_reply_enabled": True}
        state = await client.get_one_chat_state(connection_id)
        assert state["auto_reply_enabled"] is True

    @pytest.mark.asyncio
    async def test_marked_unreachable_raises_on_every_call(self):
        client = FakeSocialWiringClient()
        connection_id = uuid4()
        client.register(connection_id, auto_reply_enabled=True)
        client.fail_connection_ids.add(str(connection_id))
        with pytest.raises(SocialWiringUnreachable):
            await client.get_one_chat_state(connection_id)
        with pytest.raises(SocialWiringUnreachable):
            await client.set_one_chat_auto_reply(connection_id, False)


class TestGetSocialWiringClientFactory:
    def test_no_token_returns_fake(self):
        settings = type("S", (), {"social_wiring_api_token": ""})()
        assert isinstance(get_social_wiring_client(settings), FakeSocialWiringClient)

    def test_token_configured_returns_http_client(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://social-wiring.example.com")
        settings = type("S", (), {"social_wiring_api_token": "tok_abc"})()
        client = get_social_wiring_client(settings)
        assert isinstance(client, HttpSocialWiringClient)


class TestHttpSocialWiringClient:
    """Exercises the Real adapter over a stub ASGI app — no live network."""

    def _stub_app(self, connection_id, *, auto_reply_enabled: bool):
        async def get_state(request):
            return JSONResponse(
                {
                    "connection_id": str(connection_id),
                    "label": "stub",
                    "auto_reply_enabled": auto_reply_enabled,
                }
            )

        async def toggle(request):
            body = await request.json()
            return JSONResponse(
                {"connection_id": str(connection_id), "auto_reply_enabled": body["enabled"]}
            )

        return Starlette(
            routes=[
                Route(
                    f"/api/agents-bridge/one-chat/{connection_id}",
                    get_state,
                    methods=["GET"],
                ),
                Route(
                    f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
                    toggle,
                    methods=["PUT"],
                ),
            ]
        )

    @pytest.mark.asyncio
    async def test_get_one_chat_state_success(self):
        connection_id = uuid4()
        app = self._stub_app(connection_id, auto_reply_enabled=True)
        client = HttpSocialWiringClient(
            "http://social-wiring.local", "tok_abc", transport=httpx.ASGITransport(app=app)
        )
        body = await client.get_one_chat_state(connection_id)
        assert body["auto_reply_enabled"] is True

    @pytest.mark.asyncio
    async def test_toggle_success(self):
        connection_id = uuid4()
        app = self._stub_app(connection_id, auto_reply_enabled=False)
        client = HttpSocialWiringClient(
            "http://social-wiring.local", "tok_abc", transport=httpx.ASGITransport(app=app)
        )
        body = await client.set_one_chat_auto_reply(connection_id, True)
        assert body == {"connection_id": str(connection_id), "auto_reply_enabled": True}

    @pytest.mark.asyncio
    async def test_non_2xx_raises_unreachable(self):
        connection_id = uuid4()

        async def not_found(request):
            return JSONResponse({"detail": "not found"}, status_code=404)

        app = Starlette(
            routes=[
                Route(
                    f"/api/agents-bridge/one-chat/{connection_id}", not_found, methods=["GET"]
                )
            ]
        )
        client = HttpSocialWiringClient(
            "http://social-wiring.local", "tok_abc", transport=httpx.ASGITransport(app=app)
        )
        with pytest.raises(SocialWiringUnreachable):
            await client.get_one_chat_state(connection_id)

    @pytest.mark.asyncio
    async def test_unreachable_host_raises(self):
        client = HttpSocialWiringClient(
            "http://social-wiring.invalid.nonexistent-host:1", "tok_abc", timeout=0.2
        )
        with pytest.raises(SocialWiringUnreachable):
            await client.get_one_chat_state(uuid4())
