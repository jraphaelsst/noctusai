"""FakeImageEditAdapter — deterministic + records calls."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.image_edit import (
    FakeImageEditAdapter,
    ImageEditRequest,
)


@pytest.mark.asyncio
async def test_fake_returns_deterministic_bytes_per_prompt_and_image() -> None:
    adapter = FakeImageEditAdapter()
    photo = b"input-bytes"
    a = await adapter.edit(ImageEditRequest(images=(photo,), prompt="staging", size="1536x1024"))
    b = await adapter.edit(ImageEditRequest(images=(photo,), prompt="staging", size="1536x1024"))
    assert a.images[0].image_bytes == b.images[0].image_bytes
    assert a.images[0].image_bytes.startswith(b"FAKE-IMAGE-EDIT:")


@pytest.mark.asyncio
async def test_fake_returns_different_bytes_for_different_prompt() -> None:
    adapter = FakeImageEditAdapter()
    photo = b"input-bytes"
    a = await adapter.edit(ImageEditRequest(images=(photo,), prompt="staging", size="1536x1024"))
    b = await adapter.edit(ImageEditRequest(images=(photo,), prompt="declutter", size="1536x1024"))
    assert a.images[0].image_bytes != b.images[0].image_bytes


@pytest.mark.asyncio
async def test_fake_returns_different_bytes_for_different_input_image() -> None:
    adapter = FakeImageEditAdapter()
    a = await adapter.edit(ImageEditRequest(images=(b"photo-1",), prompt="x", size="1024x1024"))
    b = await adapter.edit(ImageEditRequest(images=(b"photo-2",), prompt="x", size="1024x1024"))
    assert a.images[0].image_bytes != b.images[0].image_bytes


@pytest.mark.asyncio
async def test_fake_records_calls() -> None:
    adapter = FakeImageEditAdapter()
    await adapter.edit(
        ImageEditRequest(images=(b"p1",), prompt="A", size="1024x1024"),
        org_id="org-1",
    )
    await adapter.edit(
        ImageEditRequest(images=(b"p2", b"ref"), prompt="B", size="1536x1024", n=2),
        org_id="org-2",
    )
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["org_id"] == "org-1"
    assert adapter.calls[0]["n_images_in"] == 1
    assert adapter.calls[1]["n_images_in"] == 2
    assert adapter.calls[1]["n_out"] == 2


@pytest.mark.asyncio
async def test_fake_honours_n_output_images() -> None:
    adapter = FakeImageEditAdapter()
    result = await adapter.edit(ImageEditRequest(images=(b"p",), prompt="x", size="1024x1024", n=3))
    assert len(result.images) == 3


@pytest.mark.asyncio
async def test_fake_carries_request_id_through() -> None:
    adapter = FakeImageEditAdapter()
    result = await adapter.edit(
        ImageEditRequest(images=(b"p",), prompt="x", size="1024x1024", request_id="req-abc"),
    )
    assert result.raw["request_id"] == "req-abc"


@pytest.mark.asyncio
async def test_fake_reports_non_none_usage() -> None:
    adapter = FakeImageEditAdapter()
    result = await adapter.edit(ImageEditRequest(images=(b"p",), prompt="one two three", size="1024x1024"))
    assert result.usage.prompt_tokens == 3
    assert result.usage.image_input_tokens == 100
    assert result.usage.image_output_tokens == 100
    assert result.usage.total_tokens == 203


def test_fake_capabilities_matches_catalog_for_known_model() -> None:
    adapter = FakeImageEditAdapter()
    caps = adapter.capabilities("gpt-image-2.5-sunburst")
    assert caps.known is True
    assert caps.supports_batch is False  # C8 — no priced batch-capable model yet


def test_fake_capabilities_reports_unknown_for_unregistered_model() -> None:
    adapter = FakeImageEditAdapter()
    caps = adapter.capabilities("not-a-real-model")
    assert caps.known is False
    assert caps.supports_batch is False


def test_empty_images_tuple_rejected() -> None:
    with pytest.raises(ValueError, match="at least one image"):
        ImageEditRequest(images=(), prompt="x", size="1024x1024")


def test_zero_n_rejected() -> None:
    with pytest.raises(ValueError, match="n must be"):
        ImageEditRequest(images=(b"p",), prompt="x", size="1024x1024", n=0)
