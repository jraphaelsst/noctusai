"""HTML for the roteiro cronograma — pure string building, no I/O, no state.

Split from `roteiro_pdf_service` so the layout (this file) and the data
gathering / rendering (the service) can each change without the other. Rendered
by `noctusai_lib.integrations.documents.html_pdf.render_html_pdf` (xhtml2pdf):

  * xhtml2pdf's core fonts are cp1252 — every pt-BR glyph is covered, ☐ is not.
    Checkboxes are therefore drawn as `[   ]` text, and EVERY interpolated value
    goes through `cp1252_safe` after escaping so a stray emoji in a title can
    never render as nothing.
  * The renderer fetches nothing remote; the photo arrives as a `data:` URI.
  * One imóvel per page via `page-break-before`, so the page count == N.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Any, Optional

from noctusai_lib.integrations.documents.html_pdf import cp1252_safe

#: What a field renders when we have nothing — one constant so the PDF never
#: shows "-" in one place and "" in another.
VAZIO = "—"
SEM_FOTO = "Sem foto (foto indisponível)"
CAIXA = "[&nbsp;&nbsp;&nbsp;&nbsp;]"

_CSS = """
@page { size: A4; margin: 14mm 16mm 12mm 16mm; }
body { font-family: Helvetica; font-size: 10pt; color: #111111; }
h1 { font-size: 15pt; margin: 0 0 2pt 0; }
.cab td { font-size: 9pt; padding: 1pt 0; }
.cod { font-size: 22pt; font-weight: bold; margin: 6pt 0 2pt 0; }
.sec { font-size: 8pt; font-weight: bold; color: #444444; margin: 8pt 0 2pt 0; }
td.k { font-size: 8pt; color: #555555; width: 28%; padding: 1.5pt 0; }
td.v { font-size: 10pt; padding: 1.5pt 0; }
.foto { text-align: center; margin: 4pt 0; }
.semfoto { text-align: center; font-size: 10pt; color: #666666; padding: 38pt 0;
           border: 0.5pt solid #999999; }
.linha { border-bottom: 0.6pt solid #333333; height: 15pt; }
.rule { border-top: 0.8pt solid #333333; margin: 4pt 0 2pt 0; }
"""


def _t(valor: Any) -> str:
    """Escape + make cp1252-safe. Empty/None -> the VAZIO dash."""
    texto = "" if valor is None else str(valor).strip()
    if not texto:
        return VAZIO
    return escape(cp1252_safe(texto))


def _num(valor: Any) -> Optional[str]:
    if valor in (None, ""):
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").replace(".", ",")


def formatar_valor(valor: Any, tipo: Optional[str] = None) -> Optional[str]:
    """`1234567.5` -> `R$ 1.234.567,50` (+ ` /mês` for locação)."""
    if valor in (None, ""):
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    texto = f"R$ {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} /mês" if tipo == "locacao" else texto


def formatar_area(valor: Any) -> Optional[str]:
    n = _num(valor)
    return f"{n} m²" if n else None


def formatar_data(valor: Any) -> str:
    """ISO date/datetime (or `date`) -> dd/mm/yyyy; unparseable renders raw."""
    if not valor:
        return VAZIO
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        # Not swallowed: a bad value stays visible instead of disappearing.
        return str(valor)


def endereco(imovel: dict) -> Optional[str]:
    """Logradouro, número, complemento — whichever we have (a delisted imóvel's
    registry snapshot carries no street)."""
    rua = " ".join(p for p in [imovel.get("logradouro"), imovel.get("numero")] if p).strip()
    if imovel.get("complemento"):
        rua = f"{rua} — {imovel['complemento']}".strip(" —")
    return rua or imovel.get("endereco") or None


def local(imovel: dict) -> Optional[str]:
    cidade_uf = "/".join(p for p in [imovel.get("cidade"), imovel.get("uf")] if p)
    return " · ".join(p for p in [imovel.get("bairro"), cidade_uf] if p) or None


def captacao(imovel: dict) -> Optional[str]:
    """`imovel_dados.captador` wins; else every Vista corretor, joined."""
    cap = imovel.get("captacao") or {}
    if cap.get("nome"):
        return str(cap["nome"])
    nomes = [
        str(c.get("nome"))
        for c in (imovel.get("corretores") or [])
        if isinstance(c, dict) and c.get("nome")
    ]
    return " · ".join(nomes) or None


def _quartos(imovel: dict) -> Optional[str]:
    partes = [
        (rot, _num(imovel.get(chave)))
        for rot, chave in (("dorm.", "dormitorios"), ("suítes", "suites"), ("vagas", "vagas"))
    ]
    texto = " · ".join(f"{n} {rot}" for rot, n in partes if n)
    return texto or None


def _areas(imovel: dict) -> Optional[str]:
    partes = [
        (rot, formatar_area(imovel.get(chave)))
        for rot, chave in (
            ("útil", "area_privativa"), ("construída", "area_construida"),
            ("total", "area_total"),
        )
    ]
    texto = " · ".join(f"{rot} {v}" for rot, v in partes if v)
    return texto or None


def _valor(imovel: dict) -> Optional[str]:
    if imovel.get("valor") is not None:
        return formatar_valor(imovel.get("valor"), imovel.get("valor_tipo"))
    if imovel.get("valor_venda") is not None:
        return formatar_valor(imovel["valor_venda"])
    return formatar_valor(imovel.get("valor_locacao"), "locacao")


def _linha(rotulo: str, valor: Optional[str]) -> str:
    return f'<tr><td class="k">{escape(rotulo.upper())}</td><td class="v">{_t(valor)}</td></tr>'


def _proprietarios(lista: list[dict]) -> str:
    if not lista:
        return f'<div class="linha">{VAZIO}</div>'
    linhas = []
    for p in lista:
        nome = _t(p.get("nome"))
        doc = p.get("documento")
        linhas.append(f"<div>{nome}" + (f" &nbsp;({_t(doc)})" if doc else "") + "</div>")
    return "".join(linhas)


def pagina(
    visita: dict,
    *,
    indice: int,
    total: int,
    titulo: str,
    data_visita: str,
    cliente_nome: Optional[str],
    proprietarios: list[dict],
    foto_data_uri: Optional[str],
    foto_dim: tuple[int, int] = (330, 230),
) -> str:
    imovel = visita.get("imovel") or {}
    # A data: URI is base64 + a fixed prefix we built ourselves, so it needs no
    # escaping — escaping it would corrupt nothing but is wasted work.
    foto = (
        f'<div class="foto"><img src="{foto_data_uri}" width="{foto_dim[0]}" height="{foto_dim[1]}" /></div>'
        if foto_data_uri
        else f'<div class="semfoto">{SEM_FOTO}</div>'
    )
    fora = (
        '<div style="font-size:9pt;font-style:italic">fora do catálogo Vista</div>'
        if imovel and not imovel.get("ativo_no_vista", True)
        else ""
    )
    obs = (
        f'<div class="sec">OBSERVAÇÃO</div><div>{_t(visita.get("observacao"))}</div>'
        if visita.get("observacao")
        else ""
    )
    linhas_proposta = "".join('<div class="linha">&nbsp;</div>' for _ in range(3))
    quebra = '<div style="page-break-before: always"></div>' if indice > 1 else ""
    return f"""
{quebra}<table class="cab" width="100%"><tr>
  <td><b>{_t(titulo)}</b></td>
  <td align="right">Imóvel {indice} de {total}</td></tr>
  <tr><td>Cliente: {_t(cliente_nome)}</td>
  <td align="right">Data da visita: {_t(data_visita)}</td></tr></table>
<div class="rule"></div>
<div class="cod">{_t(visita.get("codigo"))}</div>
<div>{_t(imovel.get("titulo")) if imovel.get("titulo") else ""}</div>{fora}
{foto}
<div class="sec">DADOS DO IMÓVEL</div>
<table width="100%">
{_linha("Categoria", imovel.get("categoria"))}
{_linha("Condomínio", imovel.get("empreendimento"))}
{_linha("Endereço", endereco(imovel))}
{_linha("Bairro / cidade", local(imovel))}
{_linha("Valor", _valor(imovel))}
{_linha("Dormitórios · vagas", _quartos(imovel))}
{_linha("Áreas", _areas(imovel))}
{_linha("Captação", captacao(imovel))}
</table>{obs}
<div class="sec">PROPRIETÁRIO</div>
{_proprietarios(proprietarios)}
<div class="sec">VISITA</div>
<div>Visita realizada: {CAIXA} Sim &nbsp; {CAIXA} Não</div>
<div style="margin-top:8pt">Assinatura (cliente): ______________________________ &nbsp; Data: ___/___/_____</div>
<div class="sec">PROPOSTA</div>
<div>Gerou proposta? {CAIXA} Sim &nbsp; {CAIXA} Não</div>
<div style="margin-top:4pt">Proposta:</div>{linhas_proposta}
<div style="margin-top:6pt">{CAIXA} Permuta &nbsp;&nbsp; {CAIXA} Financiamento &nbsp;&nbsp; {CAIXA} FGTS</div>
"""


def documento(paginas: list[str], *, titulo: str) -> str:
    return (
        '<html><head><meta charset="utf-8"/>'
        f"<title>{_t(titulo)}</title><style>{_CSS}</style></head>"
        f"<body>{''.join(paginas)}</body></html>"
    )
