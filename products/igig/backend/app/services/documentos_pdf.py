"""The two client-facing PDFs of the comercial flow — orçamento and contrato.

Both are ONE self-contained HTML document rendered by the seed's
`noctusai_lib.integrations.documents.render_html_pdf` (xhtml2pdf — owner
requirement 2026-09-14 "Use xhtml2pdf on all PDFs"; nothing is fetched, so no
remote logo/CSS). The layout is IgIg's: brand header, clean tables, a totals
box. Everything user-typed passes through :func:`_t` (HTML-escaped and reduced
to what the core fonts can draw — an emoji would otherwise render as nothing).

INTERNAL NUMBERS NEVER REACH THESE DOCUMENTS. `custo_estimado`,
`margem_estimada` and `horas_estimadas` are the agency's own economics; the
PDF goes to the lead.
"""
from __future__ import annotations

import html
import logging
from datetime import date, datetime
from typing import Any, Iterable

from noctusai_lib.integrations.documents import cp1252_safe, render_html_pdf

from app.services.orcamentos import frequencia_texto

logger = logging.getLogger(__name__)

__all__ = [
    "AGENCIA_PADRAO",
    "nome_da_agencia",
    "brl",
    "renderizar_orcamento_pdf",
    "renderizar_contrato_pdf",
    "VIAS_POR_EXTENSO",
]

COR_MARCA = "#4C1D95"
COR_ACENTO = "#7C3AED"
COR_SUAVE = "#F5F3FF"
COR_TEXTO = "#1F2937"
COR_MUTED = "#6B7280"
COR_LINHA = "#E5E7EB"

SECAO_ROTULO = {"criacao_conteudo": "Criação de conteúdo", "gestao_conta": "Gestão de conta"}
VIAS_POR_EXTENSO = {
    1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
    6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
}
_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


#: Shown only when the org row cannot be read — logged, never silent.
AGENCIA_PADRAO = "IgIg"


def nome_da_agencia(core_db: Any, org_id: str) -> str:
    """The agency's display name — core's `public.organizations.nome`."""
    linhas = (
        core_db.table("organizations").select("id, nome").eq("id", org_id).execute().data or []
    )
    nome = (linhas[0].get("nome") or "").strip() if linhas else ""
    if not nome:
        logger.warning("organizations.nome ausente para org=%s — usando %r no PDF",
                       org_id, AGENCIA_PADRAO)
        return AGENCIA_PADRAO
    return nome


def _t(valor: Any) -> str:
    """User text → safe HTML: escaped and restricted to core-font glyphs."""
    if valor is None:
        return ""
    return html.escape(cp1252_safe(str(valor)), quote=True)


def brl(valor: Any) -> str:
    """`1234.5` → `R$ 1.234,50`."""
    numero = float(valor or 0)
    sinal = "-" if numero < 0 else ""
    inteiro, _, centavos = f"{abs(numero):,.2f}".partition(".")
    return f"{sinal}R$ {inteiro.replace(',', '.')},{centavos}"


def _data_br(valor: Any) -> str:
    if not valor:
        return ""
    if isinstance(valor, (date, datetime)):
        d = valor if isinstance(valor, date) else valor.date()
    else:
        d = date.fromisoformat(str(valor)[:10])
    return d.strftime("%d/%m/%Y")


def _data_extenso(d: date) -> str:
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


_CSS = f"""
@page {{
  size: a4 portrait;
  margin: 1.6cm 1.6cm 2cm 1.6cm;
  @frame rodape {{
    -pdf-frame-content: rodape;
    left: 1.6cm; width: 17.8cm; bottom: 0.7cm; height: 0.9cm;
  }}
}}
body {{ font-family: Helvetica; font-size: 9.5pt; color: {COR_TEXTO}; line-height: 1.35; }}
.marca {{ font-size: 20pt; font-weight: bold; color: {COR_MARCA}; }}
.doc-tipo {{ font-size: 9pt; color: {COR_ACENTO}; text-transform: uppercase; letter-spacing: 1px; }}
.meta {{ font-size: 8.5pt; color: {COR_MUTED}; text-align: right; }}
.meta b {{ color: {COR_TEXTO}; }}
.faixa {{ background-color: {COR_MARCA}; height: 4px; font-size: 1pt; }}
.faixa-acento {{ background-color: {COR_ACENTO}; height: 4px; font-size: 1pt; }}
.titulo {{ font-size: 14pt; font-weight: bold; color: {COR_TEXTO}; margin-top: 14px; }}
.rotulo {{ font-size: 7.5pt; color: {COR_MUTED}; text-transform: uppercase; letter-spacing: 1px; }}
.cartao {{ background-color: {COR_SUAVE}; padding: 8px 10px 6px 10px; }}
h2 {{ font-size: 11pt; color: {COR_MARCA}; margin: 16px 0 6px 0; }}
table.itens {{ width: 100%; }}
table.itens th {{
  background-color: {COR_MARCA}; color: #FFFFFF; font-size: 8pt; font-weight: bold;
  padding: 5px 6px 4px 6px; text-align: left;
}}
table.itens td {{ padding: 5px 6px 4px 6px; border-bottom: 0.5px solid {COR_LINHA}; }}
table.itens tr.par td {{ background-color: #FAFAFB; }}
table.itens td.num, table.itens th.num {{ text-align: right; }}
table.itens tr.subtotal td {{ font-weight: bold; background-color: {COR_SUAVE}; border-bottom: 0; }}
.freq {{ color: {COR_ACENTO}; font-size: 8.5pt; }}
table.totais td {{ padding: 4px 8px 3px 8px; }}
table.totais td.valor {{ text-align: right; }}
table.totais tr.total td {{
  background-color: {COR_MARCA}; color: #FFFFFF; font-size: 12pt; font-weight: bold;
  padding: 7px 8px 6px 8px;
}}
.nota {{ font-size: 8.5pt; color: {COR_MUTED}; }}
p.clausula {{ text-align: justify; margin: 0 0 6px 0; }}
.assinatura td {{ padding-top: 34px; font-size: 8.5pt; text-align: center; }}
.linha-assinatura {{ border-top: 0.8px solid {COR_TEXTO}; padding-top: 3px; }}
#rodape {{ font-size: 7.5pt; color: {COR_MUTED}; text-align: center; }}
"""


def _documento(corpo: str, *, rodape: str) -> str:
    return (
        "<html><head><meta charset='utf-8'/><style>" + _CSS + "</style></head><body>"
        f"<div id='rodape'>{rodape} &nbsp;·&nbsp; página <pdf:pagenumber/> de "
        "<pdf:pagecount/></div>"
        + corpo + "</body></html>"
    )


def _cabecalho(agencia: str, tipo: str, meta_linhas: Iterable[str]) -> str:
    meta = "<br/>".join(meta_linhas)
    return (
        "<table width='100%'><tr>"
        f"<td width='62%' valign='bottom'><div class='marca'>{_t(agencia)}</div>"
        f"<div class='doc-tipo'>{_t(tipo)}</div></td>"
        f"<td width='38%' valign='bottom' class='meta'>{meta}</td>"
        "</tr></table>"
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        "<td width='80%' class='faixa'>&nbsp;</td><td width='20%' class='faixa-acento'>&nbsp;</td>"
        "</tr></table>"
        "<p style='font-size:8pt; margin:0'>&nbsp;</p>"
    )


def _tabela_itens(itens: list[dict]) -> str:
    """One table per section, each with its subtotal row."""
    blocos = []
    for secao, rotulo in SECAO_ROTULO.items():
        da_secao = [i for i in itens if i.get("secao") == secao]
        if not da_secao:
            continue
        linhas = []
        for n, item in enumerate(da_secao):
            classe = " class='par'" if n % 2 else ""
            linhas.append(
                f"<tr{classe}><td width='38%'>{_t(item.get('descricao'))}</td>"
                f"<td width='22%'><span class='freq'>{_t(frequencia_texto(item))}</span></td>"
                f"<td width='10%' class='num'>{int(item.get('quantidade_mensal') or 0)}</td>"
                f"<td width='15%' class='num'>{brl(item.get('preco_unitario'))}</td>"
                f"<td width='15%' class='num'>{brl(item.get('subtotal'))}</td></tr>"
            )
        subtotal = sum(float(i.get("subtotal") or 0) for i in da_secao)
        blocos.append(
            f"<h2>{rotulo}</h2>"
            "<table class='itens' cellspacing='0'>"
            "<tr><th width='38%'>Item</th><th width='22%'>Frequência</th>"
            "<th width='10%' class='num'>Qtd/mês</th><th width='15%' class='num'>Unitário</th>"
            "<th width='15%' class='num'>Subtotal</th></tr>"
            + "".join(linhas)
            + f"<tr class='subtotal'><td colspan='4'>Subtotal — {rotulo.lower()}</td>"
            f"<td class='num'>{brl(subtotal)}</td></tr></table>"
        )
    if not blocos:
        blocos.append("<p class='nota'>Nenhum item neste orçamento.</p>")
    return "".join(blocos)


def renderizar_orcamento_pdf(orcamento: dict, *, agencia: str, emitido_em: date) -> bytes:
    """The proposal the lead receives: items by section, totals, scope limits."""
    lead = orcamento.get("lead") or {}
    validade = orcamento.get("validade")
    meta = [
        f"Proposta <b>v{int(orcamento.get('versao') or 1)}</b>",
        f"Emitida em <b>{_data_br(emitido_em)}</b>",
        f"Válida até <b>{_data_br(validade)}</b>" if validade else "Sem prazo de validade",
    ]
    destinatario = "".join(
        f"<br/>{_t(v)}" for v in (lead.get("empresa"), lead.get("email")) if v
    )
    limites = orcamento.get("limites_escopo") or {}
    desconto = float(orcamento.get("desconto") or 0)
    linhas_totais = [
        ("Criação de conteúdo", orcamento.get("subtotal_criacao")),
        ("Gestão de conta", orcamento.get("subtotal_gestao")),
    ]
    if desconto:
        linhas_totais.append(("Desconto", -desconto))
    totais = "".join(
        f"<tr><td>{rotulo}</td><td class='valor'>{brl(valor)}</td></tr>"
        for rotulo, valor in linhas_totais
    )
    escopo = (
        f"<div><b>{int(limites.get('revisoes_incluidas') or 0)}</b> rodada(s) de revisão "
        "incluída(s) por peça.</div>"
        f"<div>Peças ou revisões além do escopo: <b>{brl(limites.get('valor_excedente'))}</b> "
        "por unidade.</div>"
    )
    if limites.get("observacoes"):
        escopo += f"<div class='nota'>{_t(limites['observacoes'])}</div>"
    observacoes = (
        f"<h2>Observações</h2><p class='clausula'>{_t(orcamento['observacoes'])}</p>"
        if orcamento.get("observacoes") else ""
    )
    corpo = (
        _cabecalho(agencia, "Proposta comercial", meta)
        + "<table width='100%'><tr><td width='60%' valign='top'>"
        f"<div class='titulo'>{_t(orcamento.get('titulo'))}</div></td>"
        "<td width='40%' valign='top' class='cartao'><span class='rotulo'>Para</span><br/>"
        f"<b>{_t(lead.get('nome'))}</b>{destinatario}</td></tr></table>"
        + _tabela_itens(orcamento.get("itens") or [])
        + "<table width='100%'><tr><td width='50%' valign='top'>"
        f"<h2>Escopo</h2>{escopo}</td>"
        "<td width='50%' valign='top'><h2>Investimento mensal</h2>"
        f"<table class='totais' width='100%' cellspacing='0'>{totais}"
        f"<tr class='total'><td>Total mensal</td><td class='valor'>"
        f"{brl(orcamento.get('total_mensal'))}</td></tr></table></td></tr></table>"
        + observacoes
    )
    return render_html_pdf(_documento(corpo, rodape=_t(agencia) + " · Proposta comercial"))


def renderizar_contrato_pdf(
    *,
    agencia: str,
    cliente: dict,
    orcamento: dict,
    contrato: dict,
    modalidade: str,
    vias: int,
    emitido_em: date,
) -> bytes:
    """The service contract generated from an accepted orçamento.

    `fisica` ends with the "N vias" closing and hand-signature lines (parties +
    two witnesses) — it is printed and signed on paper, no e-signature (R12).
    `digital` ends with the electronic-signature acknowledgement instead.
    """
    limites = orcamento.get("limites_escopo") or {}
    dia = contrato.get("dia_vencimento")
    vencimento = f"todo dia {int(dia)} de cada mês" if dia else "em data acordada entre as partes"
    inicio = contrato.get("data_inicio") or emitido_em.isoformat()
    meta = [
        f"Referente à proposta <b>v{int(orcamento.get('versao') or 1)}</b>",
        f"Emitido em <b>{_data_br(emitido_em)}</b>",
        "Assinatura <b>física</b>" if modalidade == "fisica" else "Assinatura <b>digital</b>",
    ]
    clausulas = [
        ("Do objeto",
         "A CONTRATADA prestará à CONTRATANTE os serviços de marketing digital descritos "
         "no quadro a seguir, conforme a proposta comercial aceita."),
        ("Do valor e do pagamento",
         f"Pelos serviços, a CONTRATANTE pagará à CONTRATADA o valor mensal de "
         f"<b>{brl(contrato.get('valor_mensal'))}</b>, com vencimento {vencimento}."),
        ("Do escopo e das revisões",
         f"Estão incluídas <b>{int(limites.get('revisoes_incluidas') or 0)}</b> rodada(s) de "
         "revisão por peça. Peças ou revisões que excedam o escopo mensal serão cobradas à parte, "
         f"ao valor de <b>{brl(contrato.get('valor_excedente'))}</b> por unidade."),
        ("Da vigência",
         f"Este contrato vigora por 12 (doze) meses a partir de {_data_br(inicio)}, renovando-se "
         "automaticamente por iguais períodos, salvo manifestação contrária de qualquer das partes."),
        ("Da rescisão",
         "Qualquer das partes poderá rescindir este contrato mediante aviso prévio por escrito de "
         "30 (trinta) dias, sem prejuízo dos valores devidos pelos serviços já prestados."),
        ("Da confidencialidade e dos dados pessoais",
         "As partes manterão sigilo sobre as informações a que tiverem acesso em razão deste "
         "contrato e tratarão dados pessoais em conformidade com a Lei nº 13.709/2018 (LGPD)."),
    ]
    def _clausulas(inicio: int, lista: list[tuple[str, str]]) -> str:
        return "".join(
            f"<p class='clausula'><b>Cláusula {n}ª — {titulo}.</b> {texto}</p>"
            for n, (titulo, texto) in enumerate(lista, start=inicio)
        )

    partes = (
        "<table width='100%' cellspacing='6'><tr>"
        "<td width='50%' valign='top' class='cartao'><span class='rotulo'>Contratada</span><br/>"
        f"<b>{_t(agencia)}</b></td>"
        "<td width='50%' valign='top' class='cartao'><span class='rotulo'>Contratante</span><br/>"
        f"<b>{_t(cliente.get('nome'))}</b>"
        + "".join(f"<br/>{_t(v)}" for v in (cliente.get("email"), cliente.get("telefone")) if v)
        + "</td></tr></table>"
    )
    if modalidade == "fisica":
        n_vias = int(vias)
        extenso = VIAS_POR_EXTENSO.get(n_vias, str(n_vias))
        fecho = (
            # ONE outer table row around the closing + every signature line:
            # reportlab never splits a table row across pages, so the block
            # moves to the next page whole instead of leaving the witnesses
            # orphaned on a page of their own (a split signature block invites
            # a page swap).
            "<table width='100%'><tr><td>"
            "<p class='clausula'>E, por estarem assim justos e contratados, as partes firmam o "
            f"presente instrumento em {n_vias} ({extenso}) vias de igual teor e forma, na presença "
            "das testemunhas abaixo.</p>"
            "<p class='clausula'>&nbsp;</p>"
            "<p class='clausula'>"
            "_______________________________, _____ de _______________ de ________.</p>"
            "<table width='100%' class='assinatura'><tr>"
            "<td width='46%'><div class='linha-assinatura'>CONTRATANTE<br/>"
            f"{_t(cliente.get('nome'))}</div></td><td width='8%'></td>"
            "<td width='46%'><div class='linha-assinatura'>CONTRATADA<br/>"
            f"{_t(agencia)}</div></td></tr>"
            "<tr><td><div class='linha-assinatura'>Testemunha 1<br/>Nome:<br/>CPF:</div></td><td></td>"
            "<td><div class='linha-assinatura'>Testemunha 2<br/>Nome:<br/>CPF:</div></td></tr>"
            "</table></td></tr></table>"
        )
    else:
        fecho = (
            "<p class='clausula'>As partes reconhecem a validade, a autenticidade e a integridade "
            "da assinatura eletrônica deste instrumento, nos termos da Medida Provisória nº "
            "2.200-2/2001 e da Lei nº 14.063/2020.</p>"
            f"<p class='nota'>Emitido em {_data_extenso(emitido_em)} para assinatura digital.</p>"
        )
    corpo = (
        _cabecalho(agencia, "Contrato de prestação de serviços", meta)
        + "<div class='titulo'>Contrato de prestação de serviços de marketing digital</div>"
        + partes
        + _clausulas(1, clausulas[:1])
        + _tabela_itens(orcamento.get("itens") or [])
        + "<table class='totais' width='100%' cellspacing='0'><tr class='total'>"
        f"<td>Valor mensal</td><td class='valor'>{brl(contrato.get('valor_mensal'))}</td>"
        "</tr></table><p style='font-size:6pt; margin:0'>&nbsp;</p>"
        + _clausulas(2, clausulas[1:])
        + fecho
    )
    return render_html_pdf(_documento(corpo, rodape=_t(agencia) + " · Contrato de prestação de serviços"))
