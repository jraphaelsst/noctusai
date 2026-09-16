"""OpenAIImageEditAdapter — offline via constructor-injected `client`.

No live OpenAI call is exercised anywhere in this file (no credits on
the account at S3b write time — see `projects/edicao-fotos/PROJECT.md`
§ 4c). The success-path assertions are built from a scripted double that
duck-types `client.images.edit(**kwargs) -> Awaitable[response]`; the
error-classification assertions raise REAL `openai.*Error` instances
(the SDK is an installed seed dependency, so these are the actual
classes `_classify_openai_error` pattern-matches against — not a
reimplementation of them) from that same scripted double. Neither is
`sys.modules` patching nor monkeypatching this module's own code — see
`openai_adapter.py`'s module docstring for the DI-seam rationale.
"""
from __future__ import annotations

import base64
import types

import httpx
import openai
import pytest

from noctusai_lib.integrations.image_edit.exceptions import (
    ImageEditContentPolicyViolation,
    ImageEditFatalError,
    ImageEditNotConfigured,
    ImageEditRateLimited,
    ImageEditServerError,
    ImageEditTimeout,
)
from noctusai_lib.integrations.image_edit.openai_adapter import OpenAIImageEditAdapter
from noctusai_lib.integrations.image_edit.types import ImageEditRequest


class _FakeImagesNamespace:
    """Duck-types `AsyncOpenAI().images`."""

    def __init__(self, *, response: object | None = None, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    async def edit(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._response


class _FakeAsyncOpenAI:
    """Duck-types `openai.AsyncOpenAI` — the ONLY surface this adapter touches."""

    def __init__(self, *, response: object | None = None, raises: Exception | None = None) -> None:
        self.images = _FakeImagesNamespace(response=response, raises=raises)


def _make_response(
    *,
    b64_images: list[str],
    text_tokens: int = 10,
    image_tokens: int = 200,
    output_tokens: int = 300,
    total_tokens: int = 510,
) -> types.SimpleNamespace:
    data = [types.SimpleNamespace(b64_json=b64) for b64 in b64_images]
    usage = types.SimpleNamespace(
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        input_tokens_details=types.SimpleNamespace(text_tokens=text_tokens, image_tokens=image_tokens),
    )
    return types.SimpleNamespace(data=data, usage=usage)


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/images/edits")
    return httpx.Response(status_code, request=request, json={})


def _http_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/images/edits")


# ── Success path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_success_decodes_b64_and_maps_usage() -> None:
    png_bytes = b"not-a-real-png-just-bytes"
    b64 = base64.b64encode(png_bytes).decode("ascii")
    fake_client = _FakeAsyncOpenAI(response=_make_response(b64_images=[b64]))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    result = await adapter.edit(
        ImageEditRequest(images=(b"photo",), prompt="stage it", size="1536x1024")
    )

    assert result.images[0].image_bytes == png_bytes
    assert result.images[0].format == "png"
    assert result.model == "gpt-image-2.5-sunburst"  # adapter default
    assert result.usage.prompt_tokens == 10
    assert result.usage.image_input_tokens == 200
    assert result.usage.image_output_tokens == 300
    assert result.usage.total_tokens == 510
    call = fake_client.images.calls[0]
    assert call["prompt"] == "stage it"
    assert call["size"] == "1536x1024"
    assert call["image"] == b"photo"  # single-image request passes the bare value


@pytest.mark.asyncio
async def test_edit_multi_image_request_passes_list() -> None:
    b64 = base64.b64encode(b"out").decode("ascii")
    fake_client = _FakeAsyncOpenAI(response=_make_response(b64_images=[b64]))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    await adapter.edit(ImageEditRequest(images=(b"a", b"b"), prompt="x", size="1024x1024"))

    assert fake_client.images.calls[0]["image"] == [b"a", b"b"]


@pytest.mark.asyncio
async def test_mask_is_forwarded_when_present() -> None:
    b64 = base64.b64encode(b"out").decode("ascii")
    fake_client = _FakeAsyncOpenAI(response=_make_response(b64_images=[b64]))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    await adapter.edit(
        ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024", mask=b"mask-bytes")
    )

    assert fake_client.images.calls[0]["mask"] == b"mask-bytes"


@pytest.mark.asyncio
async def test_mask_omitted_when_absent() -> None:
    b64 = base64.b64encode(b"out").decode("ascii")
    fake_client = _FakeAsyncOpenAI(response=_make_response(b64_images=[b64]))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))

    assert "mask" not in fake_client.images.calls[0]


@pytest.mark.asyncio
async def test_multiple_output_images_all_decoded() -> None:
    b64_a = base64.b64encode(b"out-a").decode("ascii")
    b64_b = base64.b64encode(b"out-b").decode("ascii")
    fake_client = _FakeAsyncOpenAI(response=_make_response(b64_images=[b64_a, b64_b]))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    result = await adapter.edit(
        ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024", n=2)
    )

    assert [im.image_bytes for im in result.images] == [b"out-a", b"out-b"]


@pytest.mark.asyncio
async def test_empty_data_raises_fatal() -> None:
    fake_client = _FakeAsyncOpenAI(response=types.SimpleNamespace(data=[], usage=None))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditFatalError):
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))


@pytest.mark.asyncio
async def test_missing_b64_json_raises_fatal() -> None:
    response = types.SimpleNamespace(
        data=[types.SimpleNamespace(b64_json=None)], usage=None
    )
    fake_client = _FakeAsyncOpenAI(response=response)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditFatalError):
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))


# ── Error classification (retryable vs fatal) ──────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_is_retryable() -> None:
    exc = openai.RateLimitError("rate limited", response=_http_response(429), body=None)
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditRateLimited) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_internal_server_error_is_retryable() -> None:
    exc = openai.InternalServerError("boom", response=_http_response(500), body=None)
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditServerError) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_timeout_is_retryable() -> None:
    exc = openai.APITimeoutError(request=_http_request())
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditTimeout) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_connection_error_is_retryable() -> None:
    exc = openai.APIConnectionError(request=_http_request())
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditTimeout) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_authentication_error_is_not_configured_and_fatal() -> None:
    exc = openai.AuthenticationError("bad key", response=_http_response(401), body=None)
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditNotConfigured) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_content_policy_bad_request_is_fatal_content_policy() -> None:
    exc = openai.BadRequestError(
        "Your request was rejected by our safety system", response=_http_response(400), body=None
    )
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditContentPolicyViolation) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_generic_bad_request_is_fatal_invalid_size() -> None:
    from noctusai_lib.integrations.image_edit.exceptions import ImageEditInvalidSize

    exc = openai.BadRequestError("size must be a multiple of 16", response=_http_response(400), body=None)
    fake_client = _FakeAsyncOpenAI(raises=exc)
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(ImageEditInvalidSize) as excinfo:
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_non_openai_exception_is_not_reclassified() -> None:
    """A bug in OUR code (e.g. TypeError) must propagate unchanged, never
    get silently reclassified as a provider error."""
    fake_client = _FakeAsyncOpenAI(raises=TypeError("not an OpenAIError"))
    adapter = OpenAIImageEditAdapter("key", client=fake_client)

    with pytest.raises(TypeError):
        await adapter.edit(ImageEditRequest(images=(b"a",), prompt="x", size="1024x1024"))


# ── capabilities() ──────────────────────────────────────────────────────


def test_capabilities_matches_catalog_for_known_model() -> None:
    adapter = OpenAIImageEditAdapter("key", client=object())
    caps = adapter.capabilities("gpt-image-2.5-flare")
    assert caps.known is True
    assert caps.supports_batch is False  # C8 — no priced batch-capable model yet


def test_capabilities_reports_unknown_for_unregistered_model() -> None:
    adapter = OpenAIImageEditAdapter("key", client=object())
    caps = adapter.capabilities("not-a-real-model")
    assert caps.known is False
