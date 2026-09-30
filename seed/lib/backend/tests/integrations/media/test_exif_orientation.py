"""`_correct_exif_orientation` — the EXIF-orientation fix for the vision
read path (2026-09-30).

Synthetic images only — a solid two-colour split so orientation is
mechanically checkable, no real photographs anywhere in this file.

🔴 THE MEASURED GAP THIS CLOSES. Anthropic's vision endpoint (like every
raw-bytes vision API this seed calls) base64-encodes exactly the bytes it is
given; it never consults EXIF. A phone photo of an identity document, shot
with the phone held sideways, carries an `Orientation` tag telling a VIEWER
how to rotate it — and reaches the model unrotated unless something bakes
that tag into the pixels first. `_resolve_image` is the seam every
standalone-image upload (identity documents included — the ladder's rung 2
for a JPEG/PNG upload, not a PDF) passes through before the vision call.
"""
from __future__ import annotations

import io

import pytest

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from noctusai_lib.integrations.media import InboundMedia  # noqa: E402
from noctusai_lib.integrations.media.real_adapter import (  # noqa: E402
    RealMediaResolver,
    _correct_exif_orientation,
)


def _jpeg_leftred_rightblue(*, orientation: int | None) -> bytes:
    """A 100x60 JPEG, left half red / right half blue, optionally carrying
    an EXIF `Orientation` tag. `orientation=None` -> no EXIF at all."""
    im = Image.new("RGB", (100, 60))
    for y in range(60):
        for x in range(100):
            im.putpixel((x, y), (200, 10, 10) if x < 50 else (10, 10, 200))
    buf = io.BytesIO()
    if orientation is None:
        im.save(buf, format="JPEG")
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation
        im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class _FakeAnalyze:
    def __init__(self, answer: str = "[FAKE] descricao") -> None:
        self.answer = answer
        self.calls: list[dict] = []

    async def __call__(self, image, prompt, **kwargs):
        self.calls.append({"image": image, "prompt": prompt, **kwargs})
        return self.answer


class TestCorrectExifOrientationPureFunction:
    def test_rotated_orientation_is_baked_into_the_pixels(self) -> None:
        # Orientation 6 = "rotate 90 CW to display" — a phone held
        # sideways is the overwhelmingly common real-world shape.
        rotado = _jpeg_leftred_rightblue(orientation=6)
        corrigido = _correct_exif_orientation(rotado)

        antes = Image.open(io.BytesIO(rotado))
        depois = Image.open(io.BytesIO(corrigido))
        assert antes.size == (100, 60)
        assert depois.size == (60, 100)  # transposed, matches a 90° turn
        # The corrected image carries no outstanding rotation instruction —
        # a second `exif_transpose` on it must be a no-op.
        assert depois.getexif().get(0x0112, 1) == 1

    def test_normal_orientation_is_returned_byte_identical(self) -> None:
        """The overwhelming majority of uploads need no correction at all —
        must not pay a lossy JPEG re-encode for nothing."""
        normal = _jpeg_leftred_rightblue(orientation=1)
        assert _correct_exif_orientation(normal) == normal

    def test_no_exif_at_all_is_returned_byte_identical(self) -> None:
        sem_exif = _jpeg_leftred_rightblue(orientation=None)
        assert _correct_exif_orientation(sem_exif) == sem_exif

    def test_undecodable_bytes_pass_through_unchanged_never_raises(self) -> None:
        lixo = b"this is not an image at all"
        assert _correct_exif_orientation(lixo) == lixo


class TestResolveImageAppliesTheCorrectionBeforeVision:
    @pytest.mark.asyncio
    async def test_the_bytes_reaching_vision_are_already_upright(self) -> None:
        rotado = _jpeg_leftred_rightblue(orientation=6)
        analyze = _FakeAnalyze()
        resolver = RealMediaResolver(org_id="org-1", analyze=analyze)

        await resolver.resolve(InboundMedia(content=rotado, mimetype="image/jpeg"))

        assert len(analyze.calls) == 1
        enviado = analyze.calls[0]["image"]
        assert enviado != rotado
        im = Image.open(io.BytesIO(enviado))
        assert im.size == (60, 100)
