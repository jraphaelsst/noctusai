"""Rendering a quote: HTML (the print view), PDF (xhtml2pdf via the seed's one call site), DOCX (host template).

* **PDF** -- `integrations.documents.html_pdf.render_html_pdf` over HTML built here. No new dependency; nothing is
  fetched (no remote resources); every user string is `html.escape`d and reduced to what the core PDF fonts can
  draw (`cp1252_safe`) so an emoji in a description never renders as a silent blank.
* **DOCX** -- `integrations.docx_render` fills a HOST-SUPPLIED Word template (the organ ships no template: a
  proposal's wording and letterhead are the tenant's). The template's placeholders are checked against the context
  FIRST (`modelo_invalido` lists what is missing) -- a gap is reported, never rendered blank.

The context (`quote_context`) is the one documented vocabulary a template author writes against:
`number`, `version`, `title`, `status`, `valid_until`, `party_name`, `issuer_name`, `subtotal`, `discount`, `total`,
`notes`, `terms`, `lines` (each: `n`, `description`, `unit`, `qty`, `unit_price`, `discount`, `total`).
"""
from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.docx_render import DocxRenderAdapter, DocxRenderError
from noctusai_lib.integrations.documents.html_pdf import cp1252_safe, render_html_pdf

from ._common import dec, to_date
from .errors import MODELO_INVALIDO, QuotesError
from .money import money_text

STATUS_LABELS = {
    "draft": "Rascunho", "sent": "Enviado", "viewed": "Visualizado", "accepted": "Aceito",
    "rejected": "Recusado", "expired": "Expirado", "superseded": "Substituído",
}


def _qty_text(value: Any) -> str:
    d = dec(value).normalize()
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") or "0"


def _date_text(value: Any) -> str:
    day: Optional[date] = to_date(value)
    return day.strftime("%d/%m/%Y") if day else ""


def quote_context(quote: Mapping[str, Any], lines: list[Mapping[str, Any]], *, party_name: str = "", issuer_name: str = "") -> dict:
    """The template / print context (every value already a display string)."""
    cur = quote.get("currency") or "BRL"
    return {
        "number": quote["number"],
        "version": quote["version"],
        "title": quote.get("title") or "",
        "status": STATUS_LABELS.get(quote.get("status", ""), quote.get("status", "")),
        "valid_until": _date_text(quote.get("valid_until")),
        "party_name": party_name,
        "issuer_name": issuer_name,
        "subtotal": money_text(quote["subtotal_cents"], cur),
        "discount": money_text(quote["discount_cents"], cur),
        "total": money_text(quote["total_cents"], cur),
        "notes": quote.get("notes") or "",
        "terms": quote.get("terms") or "",
        "lines": [
            {
                "n": i + 1,
                "description": ln["description"],
                "unit": ln.get("unit") or "UN",
                "qty": _qty_text(ln["qty"]),
                "unit_price": money_text(ln["unit_price_cents"], cur),
                "discount": money_text(ln.get("discount_cents") or 0, cur),
                "total": money_text(ln["total_cents"], cur),
            }
            for i, ln in enumerate(lines)
        ],
    }


def _e(text: Any) -> str:
    return escape(cp1252_safe(str(text or "")), quote=True).replace("\n", "<br/>")


_CSS = """
body { font-family: Helvetica; font-size: 10pt; color: #1a1a1a; }
h1 { font-size: 18pt; margin: 0 0 2pt 0; } h2 { font-size: 11pt; margin: 12pt 0 3pt 0; }
table { width: 100%; border-collapse: collapse; } th { background-color: #eeeeee; text-align: left; }
th, td { border: 0.5pt solid #bbbbbb; padding: 3pt 4pt; } td.r, th.r { text-align: right; }
.muted { color: #666666; font-size: 9pt; } .total td { font-weight: bold; }
"""


def render_html(ctx: Mapping[str, Any]) -> str:
    """A self-contained, print-ready HTML document for the context from `quote_context`."""
    rows = "".join(
        f"<tr><td>{ln['n']}</td><td>{_e(ln['description'])}</td><td>{_e(ln['unit'])}</td>"
        f"<td class='r'>{_e(ln['qty'])}</td><td class='r'>{_e(ln['unit_price'])}</td>"
        f"<td class='r'>{_e(ln['discount'])}</td><td class='r'>{_e(ln['total'])}</td></tr>"
        for ln in ctx["lines"]
    )
    title = f"<p>{_e(ctx['title'])}</p>" if ctx["title"] else ""
    notes = f"<h2>Observações</h2><p>{_e(ctx['notes'])}</p>" if ctx["notes"] else ""
    terms = f"<h2>Termos e condições</h2><p>{_e(ctx['terms'])}</p>" if ctx["terms"] else ""
    validity = f"Válido até {_e(ctx['valid_until'])}" if ctx["valid_until"] else ""
    return (
        f"<html><head><meta charset='utf-8'/><style>{_CSS}</style></head><body>"
        f"<h1>Orçamento {_e(ctx['number'])}</h1>"
        f"<p class='muted'>Versão {ctx['version']} · {_e(ctx['status'])} · {validity}</p>{title}"
        f"<p><b>Cliente:</b> {_e(ctx['party_name'])}<br/><b>Emitido por:</b> {_e(ctx['issuer_name'])}</p>"
        "<table><thead><tr><th>#</th><th>Descrição</th><th>Un.</th><th class='r'>Qtd.</th>"
        "<th class='r'>Preço unit.</th><th class='r'>Desconto</th><th class='r'>Total</th></tr></thead>"
        f"<tbody>{rows}</tbody></table><br/>"
        "<table><tbody>"
        f"<tr><td>Subtotal</td><td class='r'>{_e(ctx['subtotal'])}</td></tr>"
        f"<tr><td>Desconto</td><td class='r'>{_e(ctx['discount'])}</td></tr>"
        f"<tr class='total'><td>Total</td><td class='r'>{_e(ctx['total'])}</td></tr>"
        f"</tbody></table>{notes}{terms}</body></html>"
    )


def render_pdf(ctx: Mapping[str, Any], *, deterministic: bool = False) -> bytes:
    return render_html_pdf(render_html(ctx), deterministic=deterministic)


def render_docx(adapter: DocxRenderAdapter, template: bytes, ctx: Mapping[str, Any]) -> bytes:
    """Fill the host's Word template; a placeholder the context cannot satisfy is `modelo_invalido` (422)."""
    try:
        missing = adapter.list_placeholders(template) - set(ctx)
        if missing:
            raise QuotesError(
                MODELO_INVALIDO, f"O modelo usa campos que o orçamento não fornece: {', '.join(sorted(missing))}.", 422,
                details={"missing": sorted(missing)},
            )
        return adapter.render(template, ctx)
    except DocxRenderError as exc:
        raise QuotesError(MODELO_INVALIDO, f"Não foi possível preencher o modelo DOCX: {exc}", 422) from exc


__all__ = ["quote_context", "render_docx", "render_html", "render_pdf"]
