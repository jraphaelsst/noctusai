"""
PDF Router — Generate and download PDF documents.

Endpoints for contracts, proposals, financial reports, and DIMOB.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import io
from app.dependencies import get_current_user, get_user_client, log_action
from app.services.pdf_service import PDFService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pdf", tags=["pdf"])

pdf_service = PDFService()


@router.get("/contrato/{contrato_id}")
async def gerar_pdf_contrato(
    contrato_id: str,
    authorization: Optional[str] = Header(None),
):
    """Generate a PDF for a contract with its installments."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch contract
    result = db.table("contratos").select("*").eq("id", contrato_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    # Fetch parcelas
    parcelas_result = db.table("parcelas_contrato").select("*").eq(
        "contrato_id", contrato_id
    ).order("numero").execute()
    parcelas = parcelas_result.data or []

    pdf_bytes = pdf_service.gerar_contrato(result.data, parcelas)

    log_action(user.id, "pdf_gerado", "contrato", contrato_id, "PDF do contrato gerado")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=contrato_{contrato_id[:8]}.pdf"},
    )


@router.get("/proposta/{proposta_id}")
async def gerar_pdf_proposta(
    proposta_id: str,
    authorization: Optional[str] = Header(None),
):
    """Generate a PDF for a proposal."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("propostas").select("*").eq("id", proposta_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    pdf_bytes = pdf_service.gerar_proposta(result.data)

    log_action(user.id, "pdf_gerado", "proposta", proposta_id, "PDF da proposta gerado")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=proposta_{proposta_id[:8]}.pdf"},
    )


@router.get("/financeiro")
async def gerar_pdf_financeiro(
    periodo_inicio: Optional[str] = None,
    periodo_fim: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Generate a financial report PDF."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch lancamentos
    query = db.table("lancamentos").select("*")
    if periodo_inicio:
        query = query.gte("data_vencimento", periodo_inicio)
    if periodo_fim:
        query = query.lte("data_vencimento", periodo_fim)
    result = query.order("data_vencimento", desc=True).execute()
    lancamentos = result.data or []

    # Calculate summary
    receita_total = sum(float(l.get("valor", 0)) for l in lancamentos
                        if l.get("tipo") == "receita" and l.get("status") == "pago")
    despesa_total = sum(float(l.get("valor", 0)) for l in lancamentos
                        if l.get("tipo") == "despesa" and l.get("status") == "pago")
    previsao = sum(float(l.get("valor", 0)) for l in lancamentos
                   if l.get("tipo") == "receita" and l.get("status") == "pendente")

    dados = {
        "receita_total": receita_total,
        "despesa_total": despesa_total,
        "saldo": receita_total - despesa_total,
        "previsao_receita": previsao,
        "lancamentos": lancamentos,
        "periodo_inicio": periodo_inicio,
        "periodo_fim": periodo_fim,
    }

    pdf_bytes = pdf_service.gerar_relatorio_financeiro(dados)

    log_action(user.id, "pdf_gerado", "financeiro", descricao="Relatório financeiro gerado")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=relatorio_financeiro.pdf"},
    )


@router.get("/dimob/{ano}")
async def gerar_pdf_dimob(
    ano: int,
    authorization: Optional[str] = Header(None),
):
    """Generate a DIMOB declaration report PDF."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch relevant data for DIMOB
    contratos_result = db.table("contratos_locacao").select("*").execute()
    contratos = contratos_result.data or []

    vendas_result = db.table("contratos").select("*").eq("tipo", "venda").execute()
    vendas = vendas_result.data or []

    secoes = []

    # Section: Locações
    locacoes_ano = [c for c in contratos if str(c.get("data_inicio", ""))[:4] <= str(ano)
                    and (not c.get("data_fim") or str(c.get("data_fim", ""))[:4] >= str(ano))]
    if locacoes_ano:
        secoes.append({
            "titulo": f"Locações ativas em {ano}",
            "itens": [
                f"Contrato {c.get('id', '')[:8]} - Valor: R$ {c.get('valor_aluguel', 0)}"
                for c in locacoes_ano
            ],
        })

    # Section: Vendas
    vendas_ano = [v for v in vendas if str(v.get("data_inicio", ""))[:4] == str(ano)]
    if vendas_ano:
        secoes.append({
            "titulo": f"Vendas em {ano}",
            "itens": [
                f"Contrato {v.get('id', '')[:8]} - Valor: R$ {v.get('valor_total', 0)}"
                for v in vendas_ano
            ],
        })

    if not secoes:
        secoes.append({"titulo": "Sem movimentações", "itens": [f"Nenhuma operação registrada em {ano}"]})

    dados = {"ano": ano, "secoes": secoes}
    pdf_bytes = pdf_service.gerar_dimob(dados)

    log_action(user.id, "pdf_gerado", "dimob", descricao=f"DIMOB {ano} gerado")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=dimob_{ano}.pdf"},
    )
