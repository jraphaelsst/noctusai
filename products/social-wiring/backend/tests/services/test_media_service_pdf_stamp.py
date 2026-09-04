"""`media_service._resolve_document`'s tier-1 text must be real characters.

🔴 THE DEFECT THIS PINS
-----------------------
`_resolve_document` rasterizes only when the PDF's text layer is thin
(`< 200` chars). A Brazilian cartório scan's text layer is a verification
stamp printed over the image — long enough to clear that threshold on its
own — so the WhatsApp bot skipped vision entirely and summarised the
document's own validation link as its contents.

Measured on documents this platform has ingested (2026-09-04):

    CERTIDÃO DE MATRÍCULA - EUROVILLE.pdf     137 chars/page × 3 = 411
    Visualização de Matrícula - Quebec        83  chars/page × 7 = 581

Both are over 200. Both were scans whose content never left the JPEG.

Same defect as the matrícula extractor's — same file even — reached
through a different threshold, which is exactly why the fix belongs in the
seed (`strip_provenance_stamps`) and is only *consumed* here.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.media import strip_provenance_stamps

from app.services.media_service import _extract_pdf_text

#: Verbatim from `CERTIDÃO DE MATRÍCULA - EUROVILLE.pdf`.
ONR_CERTIDAO_STAMP = (
    "Valide este documento clicando no link a seguir: "
    "https://assinador-web.onr.org.br/docs/7JX9U-HLZEA-9LJWT-PM2QS\n"
    "Valide aqui\neste documento"
)

#: Verbatim from `Visualização de Matrícula - Quebec - Casa 78.pdf`.
ONR_VISUALIZACAO_STAMP = (
    "SOLICITADO POR: GILSON JUNIOR - CPF/CNPJ: ***.751.658-** "
    "DATA:  25/08/2026 10:23:01"
)

#: The threshold in `_resolve_document` that these stamps used to clear.
RASTERIZE_BELOW_CHARS = 200


def _scanned_pdf(stamp: str, pages: int) -> bytes:
    """A page-sized image per page with `stamp` printed over it — the shape
    a cartório issues."""
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280))
        pix.set_rect(pix.irect, (128, 128, 128))
        page.insert_image(page.rect, pixmap=pix)
        page.insert_textbox(
            fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20),
            stamp,
            fontsize=6,
        )
    out = doc.tobytes()
    doc.close()
    return out


@pytest.mark.parametrize(
    "stamp,pages",
    [
        pytest.param(ONR_CERTIDAO_STAMP, 3, id="certidao-de-matricula"),
        pytest.param(ONR_VISUALIZACAO_STAMP, 7, id="visualizacao-de-matricula"),
    ],
)
def test_a_stamped_scan_reads_as_nothing_and_so_gets_rasterized(
    stamp: str, pages: int
) -> None:
    """Both registry document types must behave the SAME.

    They did not: 137 and 83 chars/page straddle the seed classifier's own
    100-char floor, which is the entire reason a certidão failed where a
    visualização worked.
    """
    pdf = _scanned_pdf(stamp, pages)

    # The raw reader still hands over the stamp — unchanged, and the reason
    # the threshold was cleared.
    cru = _extract_pdf_text(pdf)
    assert len(cru.strip()) >= RASTERIZE_BELOW_CHARS, (
        "fixture no longer reproduces the defect: the stamp must be long "
        "enough to clear the rasterize threshold on its own"
    )

    # What `_resolve_document` now measures instead.
    assert strip_provenance_stamps(cru) == ""


def test_a_typeset_document_still_takes_the_free_path() -> None:
    """The stripper must not push genuine documents into vision — that
    would trade a silent-wrong answer for a needless bill."""
    fitz = pytest.importorskip("fitz")

    corpo = (
        "IMOVEL: Terreno situado na Alameda Alemanha, constituido pelo lote "
        "n 14 da quadra D, no loteamento denominado Residencial Euroville. "
    ) * 6
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20),
        corpo,
        fontsize=8,
    )
    pdf = doc.tobytes()
    doc.close()

    limpo = strip_provenance_stamps(_extract_pdf_text(pdf))
    assert len(limpo.strip()) >= RASTERIZE_BELOW_CHARS
    assert "Alameda Alemanha" in limpo
