"""Canonical ingest sanitizer for user-supplied images (security standard S8).

Real-estate photos carry GPS EXIF = the owner's/client's home location
(LGPD). EVERY image upload that is stored or re-served must pass through
`sanitize_image` first. One helper, one behaviour, typed refusals.

What it does (in order):

1. Size gate, then a STRICT magic-byte sniff (JPEG/PNG/WebP/HEIC). No
   fallback guess: unknown magic -> `ImageNotAllowedError`.
2. Decode-verify with Pillow restricted to the sniffed format; a
   mismatch or corrupt body -> `ImageCorruptError`.
3. Drop ALL metadata (EXIF incl. GPS, XMP, IPTC, comments, thumbnails,
   MPF) and apply the EXIF orientation to the pixels; the ICC profile is
   KEPT (colour fidelity). `stripped` lists what the source carried.

Quality policy (no silent loss):

- JPEG with no/identity orientation: LOSSLESS — the marker segments are
  rewritten, pixels are never re-encoded (byte-identical entropy data).
- JPEG with a non-identity orientation: pixels must be rotated, so it is
  re-encoded at quality 95 / 4:4:4 (documented, near-lossless).
- PNG: re-encoded losslessly (PNG is lossless), metadata chunks dropped.
- WebP: re-encoded lossy at quality 95 (Pillow cannot drop its EXIF/XMP
  chunks without a re-encode); documented, near-lossless.
- HEIC: only when named in `allowed`; decoded and emitted as JPEG
  (quality 95, mime image/jpeg) — the platform does not emit HEIC.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()

DEFAULT_ALLOWED: tuple[str, ...] = ("jpeg", "png", "webp")
_ORIENTATION_TAG = 0x0112
_REENCODE_QUALITY = 95
_MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


class ImageIngestError(ValueError):
    """Base of every refusal; never swallowed, never a pass-through."""


class ImageTooLargeError(ImageIngestError):
    pass


class ImageNotAllowedError(ImageIngestError):
    pass


class ImageCorruptError(ImageIngestError):
    pass


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes
    mime: str
    width: int
    height: int
    #: metadata kinds the SOURCE carried and the output does not
    #: (subset of: exif, gps, xmp, iptc, comment, orientation).
    stripped: list[str]


def sniff_image_format(data: bytes) -> str | None:
    """Strict magic-byte sniff -> jpeg|png|webp|heic, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "heic"
    return None


def _jpeg_strip_segments(data: bytes) -> tuple[bytes, set[str]]:
    """Rewrite JPEG marker segments, dropping metadata; entropy data untouched."""
    out = bytearray(data[:2])
    found: set[str] = set()
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise ImageCorruptError("JPEG: malformed marker stream")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # SOS: copy the rest verbatim
            out += data[i:]
            return bytes(out), found
        if 0xD0 <= marker <= 0xD9 or marker == 0x01:  # standalone
            out += data[i : i + 2]
            i += 2
            continue
        seglen = int.from_bytes(data[i + 2 : i + 4], "big")
        if seglen < 2 or i + 2 + seglen > n:
            raise ImageCorruptError("JPEG: truncated segment")
        seg = data[i : i + 2 + seglen]
        payload = seg[4:]
        keep = True
        if marker == 0xE1:
            keep = False
            found.add("xmp" if payload.startswith(b"http://ns.adobe.com/xap") else "exif")
        elif marker == 0xED:
            keep, _ = False, found.add("iptc")
        elif marker == 0xFE:
            keep, _ = False, found.add("comment")
        elif marker == 0xE2:
            keep = payload.startswith(b"ICC_PROFILE\x00")  # drop MPF etc.
        elif marker in (0xE0, 0xEE):  # JFIF, Adobe colour transform
            keep = True
        elif 0xE3 <= marker <= 0xEF:
            keep = False
        if keep:
            out += seg
        i += 2 + seglen
    raise ImageCorruptError("JPEG: no start-of-scan marker")


def sanitize_image(
    data: bytes,
    *,
    max_bytes: int,
    allowed: tuple[str, ...] = DEFAULT_ALLOWED,
) -> SanitizedImage:
    if len(data) > max_bytes:
        raise ImageTooLargeError(f"image is {len(data)} bytes, limit {max_bytes}")
    fmt = sniff_image_format(data)
    if fmt is None:
        raise ImageNotAllowedError("unrecognised image format (magic bytes)")
    if fmt not in allowed:
        raise ImageNotAllowedError(f"image format {fmt!r} not allowed")

    pil_format = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "heic": "HEIF"}[fmt]
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != pil_format:
            raise ImageCorruptError(f"declared {fmt} but decoder saw {im.format}")
        im.load()
    except ImageIngestError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ImageCorruptError(f"cannot decode {fmt}: {exc}") from exc

    exif = im.getexif()
    stripped: set[str] = set()
    if len(exif):
        stripped.add("exif")
    if 0x8825 in exif:
        stripped.add("gps")
    if im.info.get("xmp") or im.info.get("XML:com.adobe.xmp"):
        stripped.add("xmp")
    orientation = exif.get(_ORIENTATION_TAG, 1)
    needs_rotation = orientation not in (None, 1)
    if needs_rotation:
        stripped.add("orientation")

    icc = im.info.get("icc_profile")
    mime = _MIME["jpeg" if fmt == "heic" else fmt]

    if fmt == "jpeg" and not needs_rotation:
        out, found = _jpeg_strip_segments(data)
        stripped |= found
        if "exif" in found:
            stripped.add("exif")
        return SanitizedImage(out, mime, im.width, im.height, sorted(stripped))

    transposed = ImageOps.exif_transpose(im)
    if transposed is None:  # pragma: no cover - defensive, Pillow returns a copy
        raise ImageCorruptError("orientation could not be applied")
    im = transposed
    buf = io.BytesIO()
    kwargs: dict = {}
    if icc:
        kwargs["icc_profile"] = icc
    try:
        if fmt in ("jpeg", "heic"):
            im.convert("RGB").save(
                buf, "JPEG", quality=_REENCODE_QUALITY, subsampling=0, **kwargs
            )
        elif fmt == "png":
            im.save(buf, "PNG", **kwargs)  # no exif=/pnginfo: metadata dropped
        else:
            im.save(buf, "WEBP", quality=_REENCODE_QUALITY, method=4, **kwargs)
    except (OSError, ValueError) as exc:
        raise ImageCorruptError(f"cannot re-encode {fmt}: {exc}") from exc
    return SanitizedImage(buf.getvalue(), mime, im.width, im.height, sorted(stripped))
