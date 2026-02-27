"""
PDF Service — Generate PDF documents for contracts, proposals, reports, and DIMOB.

Uses a simple HTML-to-text approach with Python's built-in libraries.
For production, consider integrating WeasyPrint or a headless browser.
"""
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _format_currency(value: float) -> str:
    """Format value as Brazilian currency."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_date(date_str: Optional[str]) -> str:
    """Format ISO date string to dd/mm/yyyy."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return date_str[:10] if date_str else "N/A"


class PDFService:
    """
    PDF generation service.

    Generates PDFs using reportlab when available, falls back to
    plain-text representation as bytes for environments without reportlab.
    """

    def __init__(self):
        self._has_reportlab = False
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate
            self._has_reportlab = True
        except ImportError:
            logger.info("[PDF] reportlab not installed, using text-based PDF fallback")

    def gerar_contrato(self, contrato: Dict[str, Any],
                       parcelas: List[Dict] = None) -> bytes:
        """Generate a contract PDF."""
        if self._has_reportlab:
            return self._gerar_contrato_reportlab(contrato, parcelas or [])
        return self._gerar_contrato_texto(contrato, parcelas or [])

    def gerar_proposta(self, proposta: Dict[str, Any]) -> bytes:
        """Generate a proposal PDF."""
        if self._has_reportlab:
            return self._gerar_proposta_reportlab(proposta)
        return self._gerar_proposta_texto(proposta)

    def gerar_relatorio_financeiro(self, dados: Dict[str, Any]) -> bytes:
        """Generate a financial report PDF."""
        if self._has_reportlab:
            return self._gerar_financeiro_reportlab(dados)
        return self._gerar_financeiro_texto(dados)

    def gerar_dimob(self, dados: Dict[str, Any]) -> bytes:
        """Generate a DIMOB declaration report."""
        if self._has_reportlab:
            return self._gerar_dimob_reportlab(dados)
        return self._gerar_dimob_texto(dados)

    # ── reportlab implementations ───────────────────────────────

    def _gerar_contrato_reportlab(self, contrato: Dict, parcelas: List[Dict]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=12)
        elements = []

        tipo = contrato.get("tipo", "venda").upper()
        elements.append(Paragraph(f"CONTRATO DE {tipo}", title_style))
        elements.append(Spacer(1, 12))

        info_lines = [
            f"<b>Contrato:</b> {contrato.get('id', 'N/A')[:8]}...",
            f"<b>Tipo:</b> {contrato.get('tipo', 'N/A')}",
            f"<b>Status:</b> {contrato.get('status', 'N/A')}",
            f"<b>Valor Total:</b> {_format_currency(float(contrato.get('valor_total', 0)))}",
            f"<b>Data Início:</b> {_format_date(contrato.get('data_inicio'))}",
            f"<b>Data Fim:</b> {_format_date(contrato.get('data_fim'))}",
        ]
        for line in info_lines:
            elements.append(Paragraph(line, styles["Normal"]))
            elements.append(Spacer(1, 4))

        if contrato.get("observacoes"):
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("<b>Observações:</b>", styles["Normal"]))
            elements.append(Paragraph(contrato["observacoes"], styles["Normal"]))

        if parcelas:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("<b>Parcelas:</b>", styles["Heading3"]))
            data = [["#", "Valor", "Vencimento", "Status"]]
            for p in parcelas:
                data.append([
                    str(p.get("numero", "")),
                    _format_currency(float(p.get("valor", 0))),
                    _format_date(p.get("data_vencimento")),
                    p.get("status", ""),
                ])
            t = Table(data, colWidths=[40, 120, 100, 100])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ]))
            elements.append(t)

        elements.append(Spacer(1, 40))
        elements.append(Paragraph("_" * 40, styles["Normal"]))
        elements.append(Paragraph("Assinatura do Contratante", styles["Normal"]))
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("_" * 40, styles["Normal"]))
        elements.append(Paragraph("Assinatura do Contratado", styles["Normal"]))

        doc.build(elements)
        return buf.getvalue()

    def _gerar_proposta_reportlab(self, proposta: Dict) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=12)
        elements = []

        elements.append(Paragraph("PROPOSTA COMERCIAL", title_style))
        elements.append(Spacer(1, 12))

        info_lines = [
            f"<b>Proposta:</b> {proposta.get('id', 'N/A')[:8]}...",
            f"<b>Status:</b> {proposta.get('status', 'N/A')}",
            f"<b>Valor:</b> {_format_currency(float(proposta.get('valor_proposta', 0)))}",
            f"<b>Data:</b> {_format_date(proposta.get('created_at'))}",
        ]
        if proposta.get("condicoes"):
            info_lines.append(f"<b>Condições:</b> {proposta['condicoes']}")

        for line in info_lines:
            elements.append(Paragraph(line, styles["Normal"]))
            elements.append(Spacer(1, 4))

        doc.build(elements)
        return buf.getvalue()

    def _gerar_financeiro_reportlab(self, dados: Dict) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=12)
        elements = []

        elements.append(Paragraph("RELATÓRIO FINANCEIRO", title_style))
        elements.append(Spacer(1, 12))

        summary = [
            ["Receita Total", _format_currency(float(dados.get("receita_total", 0)))],
            ["Despesa Total", _format_currency(float(dados.get("despesa_total", 0)))],
            ["Saldo", _format_currency(float(dados.get("saldo", 0)))],
            ["Previsão Receita", _format_currency(float(dados.get("previsao_receita", 0)))],
        ]
        t = Table(summary, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ]))
        elements.append(t)

        if dados.get("lancamentos"):
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("<b>Lançamentos:</b>", styles["Heading3"]))
            data = [["Descrição", "Tipo", "Valor", "Vencimento", "Status"]]
            for l in dados["lancamentos"][:50]:
                data.append([
                    (l.get("descricao") or "")[:30],
                    l.get("tipo", ""),
                    _format_currency(float(l.get("valor", 0))),
                    _format_date(l.get("data_vencimento")),
                    l.get("status", ""),
                ])
            t = Table(data, colWidths=[140, 60, 100, 80, 70])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ]))
            elements.append(t)

        doc.build(elements)
        return buf.getvalue()

    def _gerar_dimob_reportlab(self, dados: Dict) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=12)
        elements = []

        elements.append(Paragraph("DIMOB — Declaração de Informações sobre Atividades Imobiliárias", title_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"<b>Ano-calendário:</b> {dados.get('ano', 'N/A')}", styles["Normal"]))
        elements.append(Spacer(1, 8))

        for secao in dados.get("secoes", []):
            elements.append(Paragraph(f"<b>{secao.get('titulo', '')}</b>", styles["Heading3"]))
            for item in secao.get("itens", []):
                elements.append(Paragraph(f"  - {item}", styles["Normal"]))
            elements.append(Spacer(1, 8))

        doc.build(elements)
        return buf.getvalue()

    # ── Text-based fallback ─────────────────────────────────────

    def _gerar_contrato_texto(self, contrato: Dict, parcelas: List[Dict]) -> bytes:
        lines = [
            "=" * 60,
            f"CONTRATO DE {contrato.get('tipo', 'VENDA').upper()}",
            "=" * 60,
            "",
            f"Contrato: {contrato.get('id', 'N/A')}",
            f"Tipo: {contrato.get('tipo', 'N/A')}",
            f"Status: {contrato.get('status', 'N/A')}",
            f"Valor Total: {_format_currency(float(contrato.get('valor_total', 0)))}",
            f"Data Início: {_format_date(contrato.get('data_inicio'))}",
            f"Data Fim: {_format_date(contrato.get('data_fim'))}",
            "",
        ]
        if contrato.get("observacoes"):
            lines.append(f"Observações: {contrato['observacoes']}")
            lines.append("")

        if parcelas:
            lines.append("PARCELAS:")
            lines.append("-" * 50)
            for p in parcelas:
                lines.append(
                    f"  #{p.get('numero', '')} | "
                    f"{_format_currency(float(p.get('valor', 0)))} | "
                    f"{_format_date(p.get('data_vencimento'))} | "
                    f"{p.get('status', '')}"
                )
            lines.append("")

        lines.extend(["", "_" * 40, "Assinatura do Contratante", "", "_" * 40, "Assinatura do Contratado"])
        return "\n".join(lines).encode("utf-8")

    def _gerar_proposta_texto(self, proposta: Dict) -> bytes:
        lines = [
            "=" * 60,
            "PROPOSTA COMERCIAL",
            "=" * 60,
            "",
            f"Proposta: {proposta.get('id', 'N/A')}",
            f"Status: {proposta.get('status', 'N/A')}",
            f"Valor: {_format_currency(float(proposta.get('valor_proposta', 0)))}",
            f"Data: {_format_date(proposta.get('created_at'))}",
        ]
        if proposta.get("condicoes"):
            lines.append(f"Condições: {proposta['condicoes']}")
        return "\n".join(lines).encode("utf-8")

    def _gerar_financeiro_texto(self, dados: Dict) -> bytes:
        lines = [
            "=" * 60,
            "RELATÓRIO FINANCEIRO",
            "=" * 60,
            "",
            f"Receita Total: {_format_currency(float(dados.get('receita_total', 0)))}",
            f"Despesa Total: {_format_currency(float(dados.get('despesa_total', 0)))}",
            f"Saldo: {_format_currency(float(dados.get('saldo', 0)))}",
            f"Previsão: {_format_currency(float(dados.get('previsao_receita', 0)))}",
        ]
        return "\n".join(lines).encode("utf-8")

    def _gerar_dimob_texto(self, dados: Dict) -> bytes:
        lines = [
            "=" * 60,
            "DIMOB",
            "=" * 60,
            "",
            f"Ano: {dados.get('ano', 'N/A')}",
        ]
        for secao in dados.get("secoes", []):
            lines.append(f"\n{secao.get('titulo', '')}")
            for item in secao.get("itens", []):
                lines.append(f"  - {item}")
        return "\n".join(lines).encode("utf-8")
