"""WhatsApp channel publishing: Fake + mocked httpx only (no live WAHA)."""
import asyncio
import functools
import json

import httpx
import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.whatsapp import FakeWahaClient, WahaClient
from noctusai_lib.integrations.whatsapp.channels import (
    ChannelApiError, ChannelEngineUnsupported, ChannelIdInvalid, ChannelNotPostable, WahaChannels)
from noctusai_lib.integrations.whatsapp.line_policy import LinePolicy, LineWriteRefused

def arun(fn):
    @functools.wraps(fn)
    def wrapper():
        return asyncio.run(fn())
    return wrapper


ENABLED = LinePolicy("enabled", False, False, False)
DISABLED = LinePolicy("disabled", False, False, False)
OWN = "111@newsletter"
SUB = "222@newsletter"
CH = [{"id": OWN, "name": "Mine", "role": "OWNER"}, {"id": SUB, "name": "Theirs", "role": "SUBSCRIBER"}]


def fake(policy=ENABLED):
    c = FakeWahaClient(line_policy=policy)
    c.fake_channels = list(CH)
    return c


@arun
async def test_list_and_postable():
    ch = WahaChannels(fake())
    assert [c.id for c in await ch.list_postable()] == [OWN]


@arun
async def test_post_text_and_image_fake():
    c = fake()
    ch = WahaChannels(c)
    await ch.post_text(OWN, "hi", link_preview=True)
    await ch.post_image(OWN, "https://x/y.jpg", caption="cap")
    assert c.channel_posts[0]["chatId"] == OWN and c.channel_posts[0]["linkPreview"] is True
    assert c.channel_posts[1]["caption"] == "cap"
    assert c.sent_messages == []


@arun
async def test_validation_errors():
    ch = WahaChannels(fake())
    with pytest.raises(ChannelIdInvalid):
        await ch.post_text("5511@c.us", "x")
    with pytest.raises(ChannelNotPostable):
        await ch.post_text(SUB, "x")
    with pytest.raises(ChannelNotPostable):
        await ch.post_text("999@newsletter", "x")


@arun
async def test_policy_disabled_refuses_before_lookup():
    c = fake(DISABLED)
    with pytest.raises(LineWriteRefused):
        await WahaChannels(c).post_text(OWN, "x")
    assert c.channel_posts == []


@arun
async def test_undeclared_line_refuses():
    from noctusai_lib.integrations.whatsapp.line_policy import clear_line_policies
    clear_line_policies()
    c = FakeWahaClient()
    c.fake_channels = list(CH)
    with pytest.raises(LineWriteRefused):
        await WahaChannels(c).post_text(OWN, "x")


@arun
async def test_engine_unsupported_typed():
    with pytest.raises(ChannelEngineUnsupported):
        await WahaChannels(fake(), engine="NOWEB").post_video()
    with pytest.raises(ChannelEngineUnsupported):
        await WahaChannels(fake(), engine="UNKNOWN").list_channels()


def _real(handler, policy=ENABLED):
    return WahaClient("http://waha:3000", "k", "s", transport=httpx.MockTransport(handler), line_policy=policy)


@arun
async def test_real_http_shape_and_uses_whatsapp_bucket():
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        if req.method == "GET":
            return httpx.Response(200, json=CH)
        return httpx.Response(201, json={"id": "m1"})

    rate_limit._async_registry._reset()
    out = await WahaChannels(_real(handler)).post_text(OWN, "hello")
    assert seen[0][:2] == ("GET", "/api/s/channels")
    assert seen[1] == ("POST", "/api/sendText", {"session": "s", "chatId": OWN, "text": "hello"})
    assert out["link_preview_requested"] is None
    bucket = rate_limit._async_registry.bucket("whatsapp")
    assert bucket._capacity - bucket._tokens >= 1.9  # both calls (list + send) drew from the shared bucket


@arun
async def test_real_disabled_line_makes_no_http_call():
    calls = []
    c = _real(lambda r: calls.append(r) or httpx.Response(200, json=CH), DISABLED)
    with pytest.raises(LineWriteRefused):
        await WahaChannels(c).post_text(OWN, "x")
    assert calls == []


@arun
async def test_real_api_error_typed():
    def handler(req):
        return httpx.Response(200, json=CH) if req.method == "GET" else httpx.Response(422, text="nope")
    with pytest.raises(ChannelApiError) as e:
        await WahaChannels(_real(handler)).post_text(OWN, "x")
    assert e.value.status == 422
