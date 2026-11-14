"""Canonical ingest sanitizer (security standard S8)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from noctusai_lib.integrations.imaging import (
    ImageCorruptError,
    ImageNotAllowedError,
    ImageTooLargeError,
    RealImagingAdapter,
    sanitize_image,
    sniff_image_format,
)

_BIG = 10_000_000


def _exif(orientation: int | None = None, gps: bool = True) -> Image.Image.Exif:
    ex = Image.Exif()
    ex[0x010F] = "CameraCo"
    if orientation:
        ex[0x0112] = orientation
    if gps:
        ex[0x8825] = {1: "S", 2: (23.0, 33.0, 0.0), 3: "W", 4: (46.0, 38.0, 0.0)}
    return ex


def _img(w: int = 40, h: int = 20) -> Image.Image:
    im = Image.new("RGB", (w, h), (10, 120, 200))
    im.putpixel((0, 0), (255, 0, 0))
    return im


def _enc(fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    _img().save(buf, fmt, **kw)
    return buf.getvalue()


def _icc() -> bytes:
    from PIL import ImageCms

    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _read(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def test_jpeg_gps_removed_and_lossless_path() -> None:
    src = _enc("JPEG", exif=_exif())
    assert 0x8825 in _read(src).getexif()
    out = sanitize_image(src, max_bytes=_BIG)
    back = _read(out.data)
    assert len(back.getexif()) == 0 and 0x8825 not in back.getexif()
    assert {"exif", "gps"} <= set(out.stripped)
    assert out.mime == "image/jpeg" and (out.width, out.height) == (40, 20)
    # lossless: entropy-coded scan data is byte-identical
    assert src[src.index(b"\xff\xda") :] == out.data[out.data.index(b"\xff\xda") :]


def test_jpeg_orientation_applied_and_gps_gone() -> None:
    out = sanitize_image(_enc("JPEG", exif=_exif(orientation=6)), max_bytes=_BIG)
    back = _read(out.data)
    assert (back.width, back.height) == (20, 40)
    assert (out.width, out.height) == (20, 40)
    assert len(back.getexif()) == 0
    assert "orientation" in out.stripped


def test_icc_kept_jpeg_both_paths() -> None:
    icc = _icc()
    for ori in (None, 6):
        out = sanitize_image(
            _enc("JPEG", exif=_exif(ori), icc_profile=icc), max_bytes=_BIG
        )
        assert _read(out.data).info.get("icc_profile") == icc


def test_png_exif_stripped_icc_kept() -> None:
    icc = _icc()
    out = sanitize_image(_enc("PNG", exif=_exif(), icc_profile=icc), max_bytes=_BIG)
    back = _read(out.data)
    assert back.format == "PNG" and out.mime == "image/png"
    assert len(back.getexif()) == 0
    assert back.info.get("icc_profile") == icc
    assert "gps" in out.stripped


def test_webp_exif_stripped() -> None:
    out = sanitize_image(
        _enc("WEBP", exif=_exif(orientation=3).tobytes()), max_bytes=_BIG
    )
    back = _read(out.data)
    assert back.format == "WEBP" and out.mime == "image/webp"
    assert len(back.getexif()) == 0


def test_heic_refused_by_default_converted_when_allowed() -> None:
    import pillow_heif  # noqa: F401

    src = _enc("HEIF", quality=90)
    with pytest.raises(ImageNotAllowedError):
        sanitize_image(src, max_bytes=_BIG)
    out = sanitize_image(src, max_bytes=_BIG, allowed=("heic",))
    assert out.mime == "image/jpeg" and _read(out.data).format == "JPEG"


def test_refusals() -> None:
    good = _enc("JPEG")
    with pytest.raises(ImageTooLargeError):
        sanitize_image(good, max_bytes=10)
    with pytest.raises(ImageNotAllowedError):
        sanitize_image(b"GIF89a....", max_bytes=_BIG)
    with pytest.raises(ImageNotAllowedError):
        sanitize_image(_enc("PNG"), max_bytes=_BIG, allowed=("jpeg",))
    with pytest.raises(ImageCorruptError):
        sanitize_image(good[:30], max_bytes=_BIG)
    with pytest.raises(ImageCorruptError):  # PNG magic, junk body
        sanitize_image(b"\x89PNG\r\n\x1a\n" + b"junk" * 20, max_bytes=_BIG)
    with pytest.raises(ImageCorruptError):  # JPEG magic wrapping a PNG body? mismatch
        sanitize_image(b"\xff\xd8\xff" + _enc("PNG"), max_bytes=_BIG)


def test_sniff() -> None:
    assert sniff_image_format(_enc("JPEG")) == "jpeg"
    assert sniff_image_format(_enc("WEBP")) == "webp"
    assert sniff_image_format(b"nope") is None


def test_adapter_parity_gps_flag_and_clean_output() -> None:
    res = RealImagingAdapter().normalize_for_edit(_enc("JPEG", exif=_exif(6)))
    assert res.gps_stripped is True and (res.width, res.height) == (20, 40)
    assert len(_read(res.jpeg_bytes).getexif()) == 0
