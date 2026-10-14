"""Printable PDF shell shared by the finance books (Livro Caixa, MEI Relatório Mensal).

One call site to the platform's HTML -> PDF renderer (`integrations.documents.render_html_pdf`, xhtml2pdf): the HTML is
built from escaped text only, and `cp1252_safe` strips what the core PDF fonts cannot draw (an emoji in a description
would otherwise vanish silently). A render failure RAISES (`HtmlPdfError` -> 500 through the seed handler): a broken PDF
is never returned as if it were a document.
"""
from __future__ import annotations

from html import escape
from typing import Iterable, Optional

from noctusai_lib.integrations.documents import cp1252_safe, render_html_pdf

_CSS = """
@page { size: A4 landscape; margin: 1.4cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9pt; color: #111; }
h1 { font-size: 14pt; margin: 0 0 2pt 0; }
h2 { font-size: 10pt; margin: 8pt 0 2pt 0; }
p { margin: 2pt 0; }
table { width: 100%; border-collapse: collapse; margin-top: 6pt; }
th { background: #eeeeee; text-align: left; border-bottom: 1px solid #888; padding: 3pt; }
td { border-bottom: 1px solid #ddd; padding: 3pt; vertical-align: top; }
.r { text-align: right; }
.note { font-size: 8pt; color: #444; }
.total td { font-weight: bold; border-top: 1px solid #888; }
"""


def brl(cents: int) -> str:
    """Integer cents -> `1.234,56` (pt-BR, exact; never a float)."""
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(int(cents)), 100)
    return f"{sign}{reais:,}".replace(",", ".") + f",{centavos:02d}"


def esc(value: object) -> str:
    return escape(cp1252_safe("" if value is None else str(value)), quote=True)


def table(headers: Iterable[tuple[str, bool]], rows: Iterable[Iterable[object]], *, total_row: Optional[Iterable[object]] = None) -> str:
    """`headers` = `(label, right_aligned)`; every cell is escaped."""
    hs = list(headers)
    head = "".join(f'<th class="{"r" if r else ""}">{esc(h)}</th>' for h, r in hs)

    def line(cells: Iterable[object], cls: str = "") -> str:
        return f'<tr class="{cls}">' + "".join(f'<td class="{"r" if hs[i][1] else ""}">{esc(c)}</td>' for i, c in enumerate(cells)) + "</tr>"

    body = "".join(line(r) for r in rows)
    if total_row is not None:
        body += line(total_row, "total")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def document(title: str, subtitle_lines: Iterable[str], body_html: str, notes: Iterable[str] = ()) -> bytes:
    subs = "".join(f"<p>{esc(x)}</p>" for x in subtitle_lines)
    foot = "".join(f'<p class="note">{esc(n)}</p>' for n in notes)
    html = f"<html><head><meta charset='utf-8'><style>{_CSS}</style></head><body><h1>{esc(title)}</h1>{subs}{body_html}{foot}</body></html>"
    return render_html_pdf(html)


__all__ = ["brl", "document", "esc", "table"]
