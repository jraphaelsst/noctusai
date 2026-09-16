"""Pillow-backed real ImagingAdapter — HEIC/EXIF/ICC/GPS/resize/watermark.

`Pillow` and `pillow-heif` are HARD seed dependencies (declared in
`seed/lib/backend/pyproject.toml` `[project] dependencies` AND the root
`requirements.txt` — every product backend installs them), so this
module imports them directly at module load. That is a DELIBERATE
departure from the lazy-import-with-RuntimeError shape used elsewhere
in this package for genuinely optional heavy deps (PyMuPDF, resvg-py,
docxtpl): those stay importable without their dependency because a
CONSUMER might not need that capability at all; imaging IS a hard
platform capability every product gets, same class as `jinja2`
(`email/digest.py`) or `cryptography` (`security/encrypted_tokens.py`).

The privacy-critical invariant this module exists to guarantee: **the
final encoded JPEG never carries an `exif=` (or `icc_profile=`) kwarg
on save.** Pillow does not round-trip EXIF/ICC into a saved image
unless the caller explicitly re-attaches it — so simply never doing
that is what strips GPS coordinates (an LGPD requirement, not an
optimization), the EXIF orientation tag (already baked into the pixels
by `ImageOps.exif_transpose` before this point — carrying the tag
forward would double-rotate downstream viewers that also honour it),
and any ICC profile (already converted to sRGB — the profile pointer
is dropped, downstream consumers assume untagged sRGB).
"""

from __future__ import annotations

import io

import pillow_heif
from PIL import ExifTags, Image, ImageDraw, ImageFont, ImageOps
from PIL import UnidentifiedImageError

try:
    from PIL import ImageCms
except ImportError:  # pragma: no cover - ImageCms needs littlecms; ships with
    # the manylinux/macOS Pillow wheels this repo installs, but is not
    # present in every minimal Pillow build (e.g. some musl/Alpine
    # wheels). Degrade to "skip ICC conversion" rather than fail import
    # of the whole adapter for a capability only some inputs even use.
    ImageCms = None  # type: ignore[assignment]

from noctusai_lib.integrations.imaging.types import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_WATERMARK_TEXT,
    NormalizedImage,
    UnsupportedImageFormatError,
)

# Registers the HEIF/HEIC opener with Pillow's plugin registry so
# `Image.open` transparently decodes `.heic`/`.heif` bytes. Safe to call
# more than once (module-level import is itself already idempotent).
pillow_heif.register_heif_opener()

_GPS_INFO_TAG_ID = next(
    tag_id for tag_id, name in ExifTags.TAGS.items() if name == "GPSInfo"
)


def _open_image(image_bytes: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(image_bytes))
        im.load()
        return im
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UnsupportedImageFormatError(
            f"Could not decode image bytes ({len(image_bytes)} bytes): {exc}"
        ) from exc


def _convert_icc_to_srgb(im: Image.Image, icc_bytes: bytes) -> Image.Image:
    if ImageCms is None:
        return im
    try:
        src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
        dst_profile = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(im, src_profile, dst_profile, outputMode="RGB")
    except (ImageCms.PyCMSError, OSError):
        # A malformed/unsupported embedded profile is not itself reason
        # to refuse the whole photo — `.convert("RGB")` right after this
        # call still yields a valid RGB image; we simply cannot honour
        # the (broken) profile's specific colour transform. The output
        # never carries the ICC profile forward either way (see module
        # docstring), so there is no silent partial-conversion state.
        return im


def _encode_jpeg(im: Image.Image, *, quality: int = DEFAULT_JPEG_QUALITY) -> bytes:
    if im.mode != "RGB":
        im = im.convert("RGB")
    out = io.BytesIO()
    # No `exif=` / `icc_profile=` kwarg — see module docstring. This is
    # the one line that makes GPS-strip / orientation-drop / ICC-drop
    # true for every call site in this module, by construction.
    im.save(out, format="JPEG", quality=quality)
    return out.getvalue()


class RealImagingAdapter:
    """Real imaging adapter backed by Pillow + pillow-heif."""

    backend = "pillow"

    def normalize_for_edit(self, image_bytes: bytes) -> NormalizedImage:
        im = _open_image(image_bytes)
        source_format = im.format or "UNKNOWN"

        exif = im.getexif()
        had_gps = _GPS_INFO_TAG_ID in exif

        transposed = ImageOps.exif_transpose(im)
        if transposed is None:
            raise UnsupportedImageFormatError(
                f"{source_format}: exif_transpose could not produce a usable image"
            )
        im = transposed

        icc_bytes = im.info.get("icc_profile")
        if icc_bytes:
            im = _convert_icc_to_srgb(im, icc_bytes)

        jpeg_bytes = _encode_jpeg(im)

        return NormalizedImage(
            jpeg_bytes=jpeg_bytes,
            width=im.width,
            height=im.height,
            source_format=source_format,
            converted=source_format != "JPEG",
            gps_stripped=had_gps,
        )

    def resize(self, image_bytes: bytes, *, width: int, height: int) -> bytes:
        if width <= 0 or height <= 0:
            raise ValueError(f"width/height must be positive, got {width}x{height}")
        im = _open_image(image_bytes)
        resized = im.resize((width, height), Image.Resampling.LANCZOS)
        return _encode_jpeg(resized)

    def apply_watermark(
        self, image_bytes: bytes, *, text: str = DEFAULT_WATERMARK_TEXT
    ) -> bytes:
        im = _open_image(image_bytes)
        if im.mode != "RGB":
            im = im.convert("RGB")

        # Font size + margin scale with the image so the watermark
        # stays legibly sized on both a small preview and a full
        # edit-resolution photo.
        font_size = max(14, im.height // 32)
        margin = max(8, font_size // 2)
        font = ImageFont.load_default(size=font_size)

        draw = ImageDraw.Draw(im, "RGBA")
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = max(0, im.width - text_w - margin * 2)
        y = max(0, im.height - text_h - margin * 2)

        # Semi-transparent backing rectangle so the text stays legible
        # over both light and dark photo backgrounds.
        draw.rectangle(
            [x, y, x + text_w + margin * 2, y + text_h + margin * 2],
            fill=(0, 0, 0, 140),
        )
        draw.text(
            (x + margin, y + margin - bbox[1]),
            text,
            font=font,
            fill=(255, 255, 255, 255),
        )

        return _encode_jpeg(im)
