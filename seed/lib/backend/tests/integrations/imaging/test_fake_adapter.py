"""FakeImagingAdapter — deterministic placeholder JPEG + call recording."""

from __future__ import annotations

from noctusai_lib.integrations.imaging import FakeImagingAdapter

_JPEG_MAGIC = b"\xff\xd8\xff"


def test_normalize_for_edit_returns_valid_jpeg_bytes() -> None:
    adapter = FakeImagingAdapter()
    result = adapter.normalize_for_edit(b"anything at all")
    assert result.jpeg_bytes[:3] == _JPEG_MAGIC
    assert (result.width, result.height) == (2, 2)
    assert result.converted is True
    assert result.gps_stripped is False


def test_resize_returns_valid_jpeg_bytes() -> None:
    adapter = FakeImagingAdapter()
    out = adapter.resize(b"input bytes", width=1920, height=1080)
    assert out[:3] == _JPEG_MAGIC


def test_apply_watermark_returns_valid_jpeg_bytes() -> None:
    adapter = FakeImagingAdapter()
    out = adapter.apply_watermark(b"input bytes")
    assert out[:3] == _JPEG_MAGIC


def test_fake_is_deterministic_across_instances() -> None:
    a = FakeImagingAdapter().normalize_for_edit(b"same input")
    b = FakeImagingAdapter().normalize_for_edit(b"same input")
    assert a.jpeg_bytes == b.jpeg_bytes


def test_fake_records_calls() -> None:
    adapter = FakeImagingAdapter()
    adapter.normalize_for_edit(b"in1")
    adapter.resize(b"in2", width=100, height=200)
    adapter.apply_watermark(b"in3", text="custom")
    assert [c["op"] for c in adapter.calls] == [
        "normalize_for_edit",
        "resize",
        "apply_watermark",
    ]
    assert adapter.calls[1]["width"] == 100
    assert adapter.calls[1]["height"] == 200
    assert adapter.calls[2]["text"] == "custom"
    # every recorded call hashes its OWN input bytes, not a shared sentinel
    assert len(adapter.calls[0]["input_sha256"]) == 64
    assert adapter.calls[0]["input_sha256"] != adapter.calls[1]["input_sha256"]
