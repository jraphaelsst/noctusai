"""The roteiro cronograma, as a PDF — one imóvel per page, in visiting order.

WHY reportlab AND NOT WeasyPrint (user-ratified 2026-08-25)
-----------------------------------------------------------
`reportlab` is pure Python: no Cairo, no Pango, no system packages, so the
house single-container image is unchanged. WeasyPrint would have given prettier
layout control in exchange for dragging a graphics stack into every
social-wiring build — a real base-image cost for a four-field page.

It is also already the product's answer: `modules/meta_ads/services/
ads_export_service.to_pdf` renders the ads report with it and
`requirements.txt` has declared `reportlab>=4.0.0` since. This module adds no
dependency.

🔴 N=2 ON PDF GENERATION — NOT YET FORMALIZED, DELIBERATELY. The ads export is
a landscape TABLE report built with `platypus`; this is a portrait
one-record-per-page canvas document. They share the library and nothing else —
no page furniture, no styles, no data shape — so extracting a "PDF helper" now
would be a wrapper over `import reportlab`. Flagged as the triage the DRY rule
asks for at N=2; a THIRD PDF surface is where a shared seam becomes mandatory,
and the shape to extract will be visible by then.

Server-side rather than a browser print dialog for the same reason it is worth
doing at all: these bytes can later be attached to a WhatsApp message or an
e-mail without a browser in the loop, and they do not depend on which browser
the corretor happened to open.

WHY ONE IMÓVEL PER PAGE
-----------------------
The user asked for it, and the shape earns it: a corretor carries this between
properties, reads one page at the door, and turns it over on the way to the
next. Cramming three per page would save paper and lose the thing that makes it
a cronograma.

WHAT IS DELIBERATELY NOT ON IT
------------------------------
No photo. The user named exactly four data points and a photo is not among
them; fetching a remote image server-side would add a network failure mode to
a document that otherwise cannot fail.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from noctusai_lib.primitives.exceptions import ValidationError_

#: reportlab is imported INSIDE `gerar`, matching
#: `meta_ads/services/ads_export_service.to_pdf`. Module-level would make every
#: importer of `card_hub.router` — i.e. the whole app and its whole test suite —
#: hard-depend on a library only one route needs, so a missing wheel would fail
#: everything instead of the one endpoint that actually cannot work.

#: A4 in points, resolved without importing reportlab (595.27 x 841.89).
_LARGURA, _ALTURA = 210 / 25.4 * 72, 297 / 25.4 * 72
#: One millimetre in points — reportlab's `units.mm`, inlined for the same
#: reason as the page size.
mm = 72.0 / 25.4
_MARGEM = 20 * mm
_UTIL = _LARGURA - 2 * _MARGEM

#: Values a field renders when we have nothing. One constant, so the PDF and
#: the UI cannot drift into showing "-" in one place and "" in the other.
VAZIO = "—"


def gerar(roteiro: dict, *, cliente_nome: Optional[str] = None) -> bytes:
    """`RoteiroOut` -> PDF bytes.

    Takes the already-enriched dict rather than re-reading the database: the
    service that built it has the batched reads, and a second enrichment path
    here is exactly how the two would drift.
    """
    visitas = roteiro.get("visitas") or []
    if not visitas:
        # A zero-page PDF is a corrupt file, not an empty state. Refusing is
        # the honest answer and the UI can disable the button on `total == 0`.
        raise ValidationError_(
            "roteiro sem imóveis não gera cronograma", field="visitas"
        )

    # Deferred import — see the module note above.
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas

    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(_titulo_documento(roteiro))

    total = len(visitas)
    for i, visita in enumerate(visitas, start=1):
        _pagina(c, visita, indice=i, total=total, roteiro=roteiro, cliente_nome=cliente_nome)
        c.showPage()

    c.save()
    return buf.getvalue()


def nome_arquivo(roteiro: dict) -> str:
    return f"roteiro-{str(roteiro.get('id') or '')[:8]}.pdf"


def _titulo_documento(roteiro: dict) -> str:
    return roteiro.get("titulo") or f"Roteiro de {_data_curta(roteiro.get('created_at'))}"


def _data_curta(iso: Any) -> str:
    if not iso:
        return VAZIO
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        # Not swallowed: an unparseable timestamp still renders the raw value
        # rather than disappearing, so a bad row is visible instead of silent.
        return str(iso)


def _pagina(
    c: Any,
    visita: dict,
    *,
    indice: int,
    total: int,
    roteiro: dict,
    cliente_nome: Optional[str],
) -> None:
    imovel = visita.get("imovel") or {}
    y = _ALTURA - _MARGEM

    # ── header: which route, for whom ──────────────────────────────────
    c.setFont("Helvetica", 9)
    cabecalho = _titulo_documento(roteiro)
    if cliente_nome:
        cabecalho = f"{cabecalho}  ·  {cliente_nome}"
    c.drawString(_MARGEM, y, cabecalho)
    c.drawRightString(_LARGURA - _MARGEM, y, f"Imóvel {indice} de {total}")
    y -= 6
    c.line(_MARGEM, y, _LARGURA - _MARGEM, y)
    y -= 16 * mm

    # ── the código, large: this is what a corretor looks for ───────────
    c.setFont("Helvetica-Bold", 28)
    c.drawString(_MARGEM, y, str(visita.get("codigo") or VAZIO))
    y -= 10 * mm

    if imovel.get("titulo"):
        c.setFont("Helvetica", 11)
        y = _paragrafo(c, imovel["titulo"], y, "Helvetica", 11)
        y -= 2 * mm

    if imovel and not imovel.get("ativo_no_vista", True):
        # Not decoration: a corretor routing a visit to a property that has
        # left the catalog needs to know before driving there.
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(_MARGEM, y, "fora do catálogo Vista")
        y -= 8 * mm

    y -= 6 * mm
    y = _campo(c, "Condomínio", imovel.get("empreendimento"), y)
    y = _campo(c, "Endereço", _endereco(imovel), y)
    y = _campo(c, "Captação", _captacao(imovel), y)

    # NOC-REMEDIATE[imovel-owner-data]: Vista exposes no proprietário field
    # (see `noctusai_lib/integrations/vista/calibration.py` — neither
    # CANDIDATE_IMOVEL_LIST_FIELDS nor CANDIDATE_IMOVEL_DETAIL_FIELDS carries
    # one), so there is nothing to read yet. User-ratified 2026-08-25 to ship
    # the slot empty rather than invent a source.
    # DESTINATION: `social_wiring.imovel_dados` (migration 075) — the table
    # that already holds what WE author about a property. Add
    # `proprietario_nome` / `proprietario_celular` there, surface them through
    # `roteiros_service._imovel_out`, and delete this marker.
    y = _campo(c, "Proprietário", None, y)
    y = _campo(c, "Celular", None, y)

    if visita.get("observacao"):
        y -= 4 * mm
        y = _campo(c, "Observação", visita["observacao"], y)

    # ── the outcome line the corretor fills in by hand ─────────────────
    rodape = _MARGEM + 18 * mm
    c.line(_MARGEM, rodape, _LARGURA - _MARGEM, rodape)
    c.setFont("Helvetica", 9)
    c.drawString(_MARGEM, rodape - 6 * mm, "Visita realizada?   (   ) Sim      (   ) Não")


def _campo(c: Any, rotulo: str, valor: Optional[str], y: float) -> float:
    c.setFont("Helvetica-Bold", 9)
    c.drawString(_MARGEM, y, rotulo.upper())
    y -= 5.5 * mm
    return _paragrafo(c, valor or VAZIO, y, "Helvetica", 12) - 5 * mm


def _paragrafo(c: Any, texto: str, y: float, fonte: str, tamanho: int) -> float:
    """Draw `texto`, wrapped to the printable width, and return the new `y`.

    Wrapping is not cosmetic here: an endereço with a complemento overflows the
    page width on a real address, and reportlab's `drawString` would silently
    run it off the right edge rather than clip or wrap.
    """
    from reportlab.lib.utils import simpleSplit

    c.setFont(fonte, tamanho)
    for linha in simpleSplit(str(texto), fonte, tamanho, _UTIL):
        c.drawString(_MARGEM, y, linha)
        y -= tamanho + 3
    return y


def _endereco(imovel: dict) -> Optional[str]:
    """Logradouro, número, complemento, bairro, cidade/UF, CEP — whichever of
    them we have. A delisted imóvel answers from the registry snapshot, which
    carries bairro/cidade/uf and no street, so this must read correctly with
    half the parts missing rather than printing stray commas."""
    rua = " ".join(
        p for p in [imovel.get("logradouro"), imovel.get("numero")] if p
    ).strip()
    if imovel.get("complemento"):
        rua = f"{rua} — {imovel['complemento']}".strip(" —")

    cidade_uf = "/".join(p for p in [imovel.get("cidade"), imovel.get("uf")] if p)
    partes = [rua, imovel.get("bairro"), cidade_uf, imovel.get("cep")]
    texto = " · ".join(str(p) for p in partes if p)
    return texto or None


def _captacao(imovel: dict) -> Optional[str]:
    """Who brought the property in.

    `imovel_dados.captador_user_id` (migration 075) is the canonical answer and
    wins: it is a USER, which is what the commission slice is attributed to.
    The Vista `corretores` list is the fallback — ALL of them, joined, because
    13.1% of the catalog carries two or three and a first-only read discards
    the rest (040's own measurement).
    """
    captacao = imovel.get("captacao") or {}
    if captacao.get("nome"):
        return str(captacao["nome"])

    nomes = [
        str(cor.get("nome"))
        for cor in (imovel.get("corretores") or [])
        if isinstance(cor, dict) and cor.get("nome")
    ]
    return " · ".join(nomes) or None
