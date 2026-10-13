"""Fit a rasterized page to the vision model's NATIVE resolution — and split a
dense full page into overlapping horizontal bands when one image cannot carry
it.

WHY THIS EXISTS (2026-10-13)
----------------------------
`transcription._pdf_to_images_within_budget` used to step the render DPI down
until the page fit a byte budget ("page 1 rendered at 150 DPI (policy asked
for 400)"). Two facts made that the wrong lever:

1. **The vendor downscales anyway.** Anthropic resizes every image to the
   model's native resolution before the model sees it — "Images larger than
   either limit are downscaled before processing" — so a 400-DPI A4 page
   (3307x4677 px) reaches a high-resolution-tier model as ~1616x2286 px
   (~195 DPI): the extra pixels cost bytes and buy nothing. Sources, checked
   2026-10-13:
   - https://platform.claude.com/docs/en/build-with-claude/vision
     ("Resolution and token cost"): high-resolution tier = "Claude 4.7 and
     later models", max long edge 2576 px, max 4784 visual tokens; standard
     tier = 1568 px / 1568 tokens. One visual token = one 28x28 patch:
     `ceil(w/28) * ceil(h/28)`. Per image: 10 MB base64 on the direct API,
     5 MB on Bedrock/Vertex; 8000x8000 px hard max; >20 images in one
     request -> 2000 px per image; 32 MB per request.
   - https://platform.claude.com/docs/en/build-with-claude/vision-coordinates
     ("How Claude resizes and pads images"): the exact resize rule —
     `VisionResolution.fit_size` below is that reference implementation.
   The per-model numbers live on the catalog row
   (`llm.models.ModelEntry.vision_max_edge_px` / `vision_max_visual_tokens`).
2. **Bytes were never the binding limit once the pixels are right.** A page
   pre-fitted to 4784 visual tokens (~3.75 MP) is ~0.5-2 MB as JPEG q90 —
   far under the 5 MB budget — so stepping DPI down to save bytes was paying
   in legibility for a problem JPEG quality solves.

So: render at the density the text needs, pre-fit to what the model reads
natively (no silent server-side resize), and when a single fitted image would
be coarser than the policy's legibility floor, send the page as 2-4
overlapping bands, each at native resolution, in ONE request
(`transcription.OCR_BANDS_PROMPT_SUFFIX`). Anything that STILL has to be
downscaled below the floor is logged and marked `resolucao_reduzida`.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

#: One visual token is one 28x28 patch (Anthropic's vision guide).
PATCH_PX = 28

#: JPEG qualities tried, in order, when an encoded image is over the byte
#: budget. 90 is the measured default (`transcription._VISION_JPEG_QUALITY`);
#: lowering QUALITY is tried before lowering RESOLUTION — compression
#: artefacts at 75 still leave print legible, a halved resolution does not.
JPEG_QUALITY_LADDER: tuple[int, ...] = (90, 82, 75)

#: The aviso code a transcription carries when any page reached the model
#: below its policy's legibility floor (see `RenderPlan.resolucao_reduzida`).
AVISO_RESOLUCAO_REDUZIDA = "resolucao_reduzida"


@dataclass(frozen=True)
class VisionResolution:
    """A model's native image resolution — both limits must hold."""

    max_edge_px: int
    max_visual_tokens: int

    @staticmethod
    def visual_tokens(width: int, height: int) -> int:
        return math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX)

    def fits(self, width: int, height: int) -> bool:
        return (
            math.ceil(width / PATCH_PX) * PATCH_PX <= self.max_edge_px
            and math.ceil(height / PATCH_PX) * PATCH_PX <= self.max_edge_px
            and self.visual_tokens(width, height) <= self.max_visual_tokens
        )

    def fit_size(self, width: int, height: int) -> tuple[int, int]:
        """The size the vendor would resize `width x height` to — Anthropic's
        published reference implementation (vision-coordinates guide), so a
        pre-fitted image is exactly what the model sees."""
        if self.fits(width, height):
            return (width, height)
        if height > width:
            h, w = self.fit_size(height, width)
            return (w, h)
        aspect = width / height
        lo, hi = 1, width  # lo always fits; hi never does
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.fits(mid, max(round(mid / aspect), 1)):
                lo = mid
            else:
                hi = mid
        return (lo, max(round(lo / aspect), 1))


def vision_resolution_for(provider: Optional[str], model: Optional[str]) -> Optional[VisionResolution]:
    """The catalog's native resolution for this vision model, or `None` when
    the vendor publishes none we have recorded (OpenAI/Gemini today) — the
    caller then keeps the legacy byte-budget render, unchanged."""
    if not provider or not model:
        return None
    from noctusai_lib.integrations.llm.models import models_for

    for entry in models_for(provider, "vision"):
        if entry.id == model and entry.vision_max_edge_px and entry.vision_max_visual_tokens:
            return VisionResolution(entry.vision_max_edge_px, entry.vision_max_visual_tokens)
    return None


@dataclass(frozen=True)
class BandPlan:
    """How a `width x height` render is delivered: scaled by `scale`, then cut
    into `bands` — `(y0, y1)` pixel rows of the SCALED image, top to bottom,
    each fitting the model natively. One band = the whole page."""

    scale: float
    width: int
    height: int
    bands: tuple[tuple[int, int], ...]


def plan_bands(
    width: int,
    height: int,
    resolution: VisionResolution,
    *,
    max_bands: int,
    overlap: float,
) -> BandPlan:
    """Largest-scale plan with at most `max_bands` bands.

    Bands are horizontal strips spanning the full width (text lines run
    across them), so the width is capped at the model's edge limit; each
    strip's height is then as many 28-px patch rows as the token budget
    allows, minus nothing — neighbouring strips overlap by at least
    `overlap` of a strip so a text line cut by one edge is whole in the
    other. With `max_bands <= 1`, or when the whole image already fits, this
    is simply the vendor's own `fit_size`.
    """
    if max_bands <= 1 or resolution.fits(width, height):
        w, h = resolution.fit_size(width, height)
        return BandPlan(scale=w / width, width=w, height=h, bands=((0, h),))

    def plano(scale: float) -> Optional[BandPlan]:
        w = max(int(width * scale), 1)
        h = max(int(height * scale), 1)
        colunas = math.ceil(w / PATCH_PX)
        if colunas * PATCH_PX > resolution.max_edge_px:
            return None
        linhas = min(resolution.max_visual_tokens // colunas, resolution.max_edge_px // PATCH_PX)
        altura_faixa = linhas * PATCH_PX
        if altura_faixa <= 0:
            return None
        if h <= altura_faixa:
            return BandPlan(scale=scale, width=w, height=h, bands=((0, h),))
        sobreposicao = max(int(round(altura_faixa * overlap)), PATCH_PX)
        n = math.ceil((h - sobreposicao) / (altura_faixa - sobreposicao))
        if n > max_bands:
            return None
        passo = (h - altura_faixa) / (n - 1)
        faixas = []
        for i in range(n):
            y0 = int(round(i * passo))
            y1 = h if i == n - 1 else y0 + altura_faixa
            faixas.append((y0, min(y1, h)))
        return BandPlan(scale=scale, width=w, height=h, bands=tuple(faixas))

    # Full width at the edge limit (a multiple of the patch size).
    teto = (resolution.max_edge_px // PATCH_PX) * PATCH_PX
    escala = min(1.0, teto / width)
    melhor = plano(escala)
    if melhor is not None:
        return melhor
    # Too tall for `max_bands` at full width: the largest scale that fits.
    lo, hi = 0.0, escala
    for _ in range(40):
        mid = (lo + hi) / 2
        if plano(mid) is not None:
            lo = mid
        else:
            hi = mid
    resultado = plano(lo)
    if resultado is None:  # pragma: no cover - lo is always feasible down to tiny scales
        w, h = resolution.fit_size(width, height)
        return BandPlan(scale=w / width, width=w, height=h, bands=((0, h),))
    return resultado


@dataclass(frozen=True)
class EncodedImage:
    data: bytes
    fmt: str  # "jpeg" | "png"
    quality: Optional[int]  # JPEG quality, None for PNG


def encoded_size(raw: bytes) -> int:
    """Base64 length — what the vision request actually carries."""
    return 4 * ((len(raw) + 2) // 3)


def encode_for_vision(pix, max_encoded_bytes: int) -> Optional[EncodedImage]:
    """The smallest faithful encoding of a PyMuPDF pixmap under the budget.

    JPEG q90 first (photographic scans: 8-12x smaller than PNG, measured
    2026-09-23 — `transcription._VISION_JPEG_QUALITY`); PNG instead only
    when it is SMALLER (bilevel / flat-colour text renders, where lossless
    wins and has no artefacts). Over budget -> the next JPEG quality on
    `JPEG_QUALITY_LADDER`. `None` when nothing fits: the caller must then
    lower the resolution and say so (`resolucao_reduzida`).
    """
    png = pix.tobytes("png")
    for q in JPEG_QUALITY_LADDER:
        jpg = pix.tobytes("jpg", jpg_quality=q)
        if q == JPEG_QUALITY_LADDER[0] and len(png) < len(jpg) and encoded_size(png) <= max_encoded_bytes:
            return EncodedImage(png, "png", None)
        if encoded_size(jpg) <= max_encoded_bytes:
            return EncodedImage(jpg, "jpeg", q)
    return None


@dataclass(frozen=True)
class RenderPlan:
    """What one page sends to the model."""

    images: tuple[bytes, ...]
    #: Pixel density, in the page's own units (px per inch of the rendered
    #: region), of what the model actually reads.
    delivered_dpi: float
    #: The density the policy asked for, already capped at the source's own
    #: information (`render_page_for_vision`'s `native_dpi`).
    floor_dpi: float
    resolucao_reduzida: bool


#: Rounding slack on the floor comparison — a page at 199.6 DPI against a
#: 200 floor is the same page.
_FLOOR_TOLERANCE = 0.98


def render_page_for_vision(
    page,
    clip,
    *,
    target_dpi: float,
    min_dpi: float,
    native_dpi: Optional[float],
    resolution: VisionResolution,
    max_bands: int,
    overlap: float,
    max_encoded_bytes: int,
) -> Optional[RenderPlan]:
    """Render `clip` of `page` for `resolution`, banded when allowed.

    `target_dpi` is the density to render at before fitting; `min_dpi` the
    policy's legibility floor; `native_dpi` the scan's own pixel density when
    the region IS an embedded image (a phone photo of a certidão is ~116
    DPI) — the floor never asks for more than the source holds, so a coarse
    scan delivered at its full native density is NOT "reduced".

    Returns `None` only when PyMuPDF cannot rasterize the page.
    """
    import fitz  # type: ignore  # PyMuPDF

    rect = clip if clip is not None else page.rect
    largura_pol = rect.width / 72.0
    altura_pol = rect.height / 72.0
    if largura_pol <= 0 or altura_pol <= 0:
        return None
    largura = max(int(round(largura_pol * target_dpi)), 1)
    altura = max(int(round(altura_pol * target_dpi)), 1)
    plano = plan_bands(largura, altura, resolution, max_bands=max_bands, overlap=overlap)

    piso = min(min_dpi, native_dpi) if native_dpi else min_dpi
    escala = plano.scale
    for _tentativa in range(6):
        zoom = (target_dpi * escala) / 72.0
        try:
            cheio = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
        except Exception:
            logger.debug("vision_tiling: rasterize failed", exc_info=True)
            return None
        faixas = plano.bands if escala == plano.scale else _reescalar(plano, escala)
        # `get_pixmap` rounds the clip outward, so the render can be a pixel
        # or two larger than planned; every band is cut to the PLANNED
        # rectangle, which is what `plan_bands` proved fits the model.
        largura_plano = min(cheio.width, max(int(largura * escala), 1))
        imagens: list[bytes] = []
        estourou = False
        for y0, y1 in faixas:
            y1 = min(y1, cheio.height)
            irect = fitz.IRect(0, y0, largura_plano, y1)
            pedaco = fitz.Pixmap(cheio.colorspace, irect, cheio.alpha)
            pedaco.copy(cheio, irect)
            pedaco.set_origin(0, 0)
            if not resolution.fits(pedaco.width, pedaco.height):
                # A planning defect, not a document property: say so — the
                # vendor will downscale this band server-side.
                logger.error(
                    "vision_tiling: band %dx%d exceeds the model's native "
                    "resolution (%d px / %d tokens) — the vendor will resize it",
                    pedaco.width, pedaco.height,
                    resolution.max_edge_px, resolution.max_visual_tokens,
                )
            codificada = encode_for_vision(pedaco, max_encoded_bytes)
            if codificada is None:
                estourou = True
                break
            imagens.append(codificada.data)
        if not estourou:
            entregue = target_dpi * escala
            reduzida = entregue < piso * _FLOOR_TOLERANCE
            return RenderPlan(
                images=tuple(imagens),
                delivered_dpi=entregue,
                floor_dpi=piso,
                resolucao_reduzida=reduzida,
            )
        # Even the lowest JPEG quality is over the byte budget at this size
        # (practically unreachable at native resolution: ~3.75 MP per image)
        # — shrink, and let the floor check above report it honestly.
        escala *= 0.85
    logger.error(
        "vision_tiling: page could not be encoded under %d bytes even after "
        "shrinking — giving up on this page",
        max_encoded_bytes,
    )
    return None


def _reescalar(plano: BandPlan, escala: float) -> tuple[tuple[int, int], ...]:
    """Band rows of `plano` mapped onto a smaller `escala` (byte-budget retry)."""
    fator = escala / plano.scale
    return tuple((int(y0 * fator), int(math.ceil(y1 * fator))) for y0, y1 in plano.bands)


__all__ = [
    "AVISO_RESOLUCAO_REDUZIDA",
    "BandPlan",
    "EncodedImage",
    "JPEG_QUALITY_LADDER",
    "PATCH_PX",
    "RenderPlan",
    "VisionResolution",
    "encode_for_vision",
    "encoded_size",
    "plan_bands",
    "render_page_for_vision",
    "vision_resolution_for",
]
