"""RealImagingAdapter — Pillow + pillow-heif pixel-level behaviour.

Every fixture is built PROGRAMMATICALLY with Pillow in this file (no
committed binary blobs) — the point of a pure-Python image library
dependency is that we never need a checked-in sample photo to prove
these transforms.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from noctusai_lib.integrations.imaging import (
    RealImagingAdapter,
    UnsupportedImageFormatError,
)

_JPEG_MAGIC = b"\xff\xd8\xff"
_ORIENTATION_TAG = 0x0112
_GPS_INFO_TAG = 0x8825


def _rational(n: int) -> IFDRational:
    return IFDRational(n, 1)


def _jpeg_bytes(
    size: tuple[int, int] = (60, 40),
    color: tuple[int, int, int] = (200, 30, 30),
    *,
    orientation: int | None = None,
    with_gps: bool = False,
    icc_profile: bytes | None = None,
    quality: int = 95,
) -> bytes:
    im = Image.new("RGB", size, color=color)
    save_kwargs: dict = {"quality": quality}

    exif = im.getexif()
    if orientation is not None:
        exif[_ORIENTATION_TAG] = orientation
    if with_gps:
        exif[_GPS_INFO_TAG] = {
            1: "N",
            2: (_rational(23), _rational(32), _rational(0)),
            3: "W",
            4: (_rational(46), _rational(48), _rational(0)),
        }
    if orientation is not None or with_gps:
        save_kwargs["exif"] = exif
    if icc_profile is not None:
        save_kwargs["icc_profile"] = icc_profile

    buf = io.BytesIO()
    im.save(buf, format="JPEG", **save_kwargs)
    return buf.getvalue()


def _heic_bytes(size: tuple[int, int] = (48, 32), color=(9, 9, 200)) -> bytes:
    im = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    im.save(buf, format="HEIF", quality=90)
    return buf.getvalue()


def _png_bytes(size: tuple[int, int] = (20, 20), color=(1, 2, 3)) -> bytes:
    im = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _srgb_icc_bytes() -> bytes:
    from PIL import ImageCms

    profile = ImageCms.createProfile("sRGB")
    return ImageCms.ImageCmsProfile(profile).tobytes()


# ---------------------------------------------------------------------------
# normalize_for_edit — format conversion
# ---------------------------------------------------------------------------

class TestNormalizeForEditFormatConversion:
    def test_jpeg_source_is_not_flagged_as_converted(self) -> None:
        adapter = RealImagingAdapter()
        result = adapter.normalize_for_edit(_jpeg_bytes())
        assert result.source_format == "JPEG"
        assert result.converted is False
        assert result.jpeg_bytes[:3] == _JPEG_MAGIC

    def test_heic_source_converts_to_jpeg(self) -> None:
        adapter = RealImagingAdapter()
        result = adapter.normalize_for_edit(_heic_bytes())
        assert result.source_format == "HEIF"
        assert result.converted is True
        assert result.jpeg_bytes[:3] == _JPEG_MAGIC
        out = Image.open(io.BytesIO(result.jpeg_bytes))
        out.load()
        assert out.format == "JPEG"

    def test_png_source_converts_to_jpeg(self) -> None:
        adapter = RealImagingAdapter()
        result = adapter.normalize_for_edit(_png_bytes())
        assert result.source_format == "PNG"
        assert result.converted is True
        out = Image.open(io.BytesIO(result.jpeg_bytes))
        out.load()
        assert out.format == "JPEG"

    def test_unsupported_bytes_raise_typed_error_not_a_passthrough(self) -> None:
        adapter = RealImagingAdapter()
        garbage = b"this is not an image, not even close"
        with pytest.raises(UnsupportedImageFormatError):
            adapter.normalize_for_edit(garbage)


# ---------------------------------------------------------------------------
# normalize_for_edit — EXIF orientation transpose
# ---------------------------------------------------------------------------

class TestNormalizeForEditExifTranspose:
    def test_orientation_6_physically_rotates_the_pixels(self) -> None:
        # Orientation 6 = "rotate 90 CW to display correctly" -> a
        # 60x40 stored image with that tag must come out as 40x60.
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(60, 40), orientation=6)
        result = adapter.normalize_for_edit(source)
        assert (result.width, result.height) == (40, 60)

    def test_orientation_tag_is_dropped_from_the_output(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(60, 40), orientation=6)
        result = adapter.normalize_for_edit(source)
        out = Image.open(io.BytesIO(result.jpeg_bytes))
        assert out.getexif().get(_ORIENTATION_TAG) is None

    def test_no_orientation_tag_leaves_dimensions_unchanged(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(60, 40))
        result = adapter.normalize_for_edit(source)
        assert (result.width, result.height) == (60, 40)


# ---------------------------------------------------------------------------
# normalize_for_edit — GPS EXIF strip (LGPD)
# ---------------------------------------------------------------------------

class TestNormalizeForEditGpsStrip:
    def test_gps_tags_are_removed_from_the_output(self) -> None:
        """The dedicated LGPD assertion: build a fixture that HAS GPS
        tags and assert they are gone from the normalized output."""
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(with_gps=True)
        result = adapter.normalize_for_edit(source)

        # Sanity: the fixture actually carries GPS before normalizing.
        source_im = Image.open(io.BytesIO(source))
        assert _GPS_INFO_TAG in source_im.getexif()

        out = Image.open(io.BytesIO(result.jpeg_bytes))
        out_exif = out.getexif()
        assert _GPS_INFO_TAG not in out_exif
        assert list(out_exif.keys()) == []  # no EXIF survives at all
        assert result.gps_stripped is True

    def test_gps_stripped_is_false_when_source_carried_no_gps(self) -> None:
        adapter = RealImagingAdapter()
        result = adapter.normalize_for_edit(_jpeg_bytes(with_gps=False))
        assert result.gps_stripped is False

    def test_gps_strip_also_holds_through_a_rotated_image(self) -> None:
        # Orientation + GPS together — the rotation codepath must not
        # accidentally re-attach the raw EXIF blob.
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(orientation=6, with_gps=True)
        result = adapter.normalize_for_edit(source)
        out = Image.open(io.BytesIO(result.jpeg_bytes))
        assert _GPS_INFO_TAG not in out.getexif()


# ---------------------------------------------------------------------------
# normalize_for_edit — ICC -> sRGB
# ---------------------------------------------------------------------------

class TestNormalizeForEditIccProfile:
    def test_icc_profile_is_not_carried_into_the_output(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(icc_profile=_srgb_icc_bytes())

        source_im = Image.open(io.BytesIO(source))
        assert "icc_profile" in source_im.info

        result = adapter.normalize_for_edit(source)
        out = Image.open(io.BytesIO(result.jpeg_bytes))
        assert "icc_profile" not in out.info

    def test_image_with_no_icc_profile_normalizes_without_error(self) -> None:
        adapter = RealImagingAdapter()
        result = adapter.normalize_for_edit(_jpeg_bytes())
        assert result.jpeg_bytes[:3] == _JPEG_MAGIC


# ---------------------------------------------------------------------------
# resize — Lanczos, back to exact caller-supplied dimensions
# ---------------------------------------------------------------------------

class TestResize:
    def test_resizes_to_the_exact_requested_dimensions(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(200, 100))
        out_bytes = adapter.resize(source, width=64, height=32)
        out = Image.open(io.BytesIO(out_bytes))
        assert out.size == (64, 32)
        assert out_bytes[:3] == _JPEG_MAGIC

    def test_upscale_and_downscale_both_work(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(100, 100))
        upscaled = adapter.resize(source, width=500, height=500)
        downscaled = adapter.resize(source, width=10, height=10)
        assert Image.open(io.BytesIO(upscaled)).size == (500, 500)
        assert Image.open(io.BytesIO(downscaled)).size == (10, 10)

    def test_round_trip_resize_returns_to_original_dimensions(self) -> None:
        # Mirrors the real use: shrink to the API edit size, then grow
        # back to the caller's original dimensions.
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(720, 480))
        shrunk = adapter.resize(source, width=1568, height=1045)
        restored = adapter.resize(shrunk, width=720, height=480)
        assert Image.open(io.BytesIO(restored)).size == (720, 480)

    @pytest.mark.parametrize("width,height", [(0, 10), (10, 0), (-5, 10)])
    def test_non_positive_dimensions_raise(self, width, height) -> None:
        adapter = RealImagingAdapter()
        with pytest.raises(ValueError):
            adapter.resize(_jpeg_bytes(), width=width, height=height)

    def test_unsupported_bytes_raise_typed_error(self) -> None:
        adapter = RealImagingAdapter()
        with pytest.raises(UnsupportedImageFormatError):
            adapter.resize(b"garbage", width=100, height=100)


# ---------------------------------------------------------------------------
# apply_watermark — text overlay, opt-in
# ---------------------------------------------------------------------------

class TestApplyWatermark:
    def test_returns_a_different_but_same_sized_jpeg(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(400, 300), color=(30, 30, 30))
        watermarked = adapter.apply_watermark(source)
        assert watermarked[:3] == _JPEG_MAGIC
        assert watermarked != source
        out = Image.open(io.BytesIO(watermarked))
        assert out.size == (400, 300)

    def test_default_watermark_text_is_the_portuguese_ai_disclosure(self) -> None:
        from noctusai_lib.integrations.imaging import DEFAULT_WATERMARK_TEXT

        assert DEFAULT_WATERMARK_TEXT == "Imagem gerada com IA"

    def test_pixels_actually_change_near_the_watermark_corner(self) -> None:
        # A solid-color image watermarked in the bottom-right corner
        # must have SOME pixel there that is no longer the background
        # color — proves text was actually drawn, not a no-op.
        adapter = RealImagingAdapter()
        bg = (10, 10, 10)
        source = _jpeg_bytes(size=(300, 200), color=bg, quality=100)
        watermarked = adapter.apply_watermark(source)
        out = Image.open(io.BytesIO(watermarked)).convert("RGB")
        px = out.load()
        width, height = out.size
        changed = any(
            px[x, y] != bg
            for x in range(width - 60, width)
            for y in range(height - 30, height)
        )
        assert changed

    def test_custom_text_is_accepted(self) -> None:
        adapter = RealImagingAdapter()
        source = _jpeg_bytes(size=(300, 200))
        out_bytes = adapter.apply_watermark(source, text="Custom label")
        assert out_bytes[:3] == _JPEG_MAGIC

    def test_unsupported_bytes_raise_typed_error(self) -> None:
        adapter = RealImagingAdapter()
        with pytest.raises(UnsupportedImageFormatError):
            adapter.apply_watermark(b"garbage")


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_normalize_resize_watermark_round_trip(self) -> None:
        from noctusai_lib.primitives.image_sizing import compute_edit_size

        adapter = RealImagingAdapter()
        source = _jpeg_bytes(
            size=(720, 1080), orientation=6, with_gps=True, quality=90
        )

        normalized = adapter.normalize_for_edit(source)
        assert normalized.gps_stripped is True

        edit_w, edit_h = compute_edit_size(normalized.width, normalized.height)
        edit_input = adapter.resize(normalized.jpeg_bytes, width=edit_w, height=edit_h)
        assert Image.open(io.BytesIO(edit_input)).size == (edit_w, edit_h)

        # Simulate the OpenAI edit call round-trip by resizing straight
        # back to the caller's original (post-transpose) dimensions.
        restored = adapter.resize(
            edit_input, width=normalized.width, height=normalized.height
        )
        watermarked = adapter.apply_watermark(restored)
        final = Image.open(io.BytesIO(watermarked))
        assert final.size == (normalized.width, normalized.height)
        assert list(final.getexif().keys()) == []
