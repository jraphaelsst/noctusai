"""
DIMOB Tax Compliance Service — Declaracao de Informacoes sobre Atividades Imobiliarias.

Generates DIMOB XML for Receita Federal (Brazilian IRS) with the following record types:
- R01: Declarant identification
- R02: Intermediation operations (sales)
- R03: Rental operations
- R04: Summary
"""
import logging
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

logger = logging.getLogger(__name__)


def validate_dimob_data(data: dict) -> list[dict]:
    """
    Validate that required fields are present for DIMOB generation.
    Returns a list of warning dicts: {campo, mensagem, referencia_id?}.
    """
    warnings = []

    org = data.get("organizacao", {})
    if not org.get("cnpj"):
        warnings.append({
            "campo": "cnpj",
            "mensagem": "CNPJ da organização não informado",
        })
    if not org.get("razao_social"):
        warnings.append({
            "campo": "razao_social",
            "mensagem": "Razão social da organização não informada",
        })

    vendas = data.get("vendas", [])
    for venda in vendas:
        venda_id = venda.get("id", "?")
        if not venda.get("cpf_comprador"):
            warnings.append({
                "campo": "cpf_comprador",
                "mensagem": f"CPF do comprador não informado na venda",
                "referencia_id": venda_id,
            })
        if not venda.get("valor"):
            warnings.append({
                "campo": "valor",
                "mensagem": f"Valor da venda não informado",
                "referencia_id": venda_id,
            })
        if not venda.get("data_operacao"):
            warnings.append({
                "campo": "data_operacao",
                "mensagem": f"Data da operação não informada na venda",
                "referencia_id": venda_id,
            })

    locacoes = data.get("locacoes", [])
    for loc in locacoes:
        loc_id = loc.get("id", "?")
        if not loc.get("cpf_locatario"):
            warnings.append({
                "campo": "cpf_locatario",
                "mensagem": f"CPF do locatário não informado na locação",
                "referencia_id": loc_id,
            })
        if not loc.get("valor_aluguel"):
            warnings.append({
                "campo": "valor_aluguel",
                "mensagem": f"Valor do aluguel não informado na locação",
                "referencia_id": loc_id,
            })

    return warnings


def _fetch_dimob_data(org_id: str, ano: int, supabase) -> dict:
    """Fetch all data needed for DIMOB from database."""

    # Organization info — use first profile as declarant fallback
    org_data = {}
    try:
        org_result = supabase.table("profiles").select(
            "id, nome, email"
        ).limit(1).execute()
        org_data = org_result.data[0] if org_result.data else {}
    except Exception:
        logger.debug("Could not fetch profile for DIMOB declarant")

    # Sales (closed deals from funil with etapa 'fechado' in the target year)
    vendas = []
    try:
        vendas_query = supabase.table("clientes").select(
            "id, nome, email, valor_estimado, etapa_atual, updated_at"
        ).eq("etapa_atual", "fechado").gte(
            "updated_at", f"{ano}-01-01T00:00:00"
        ).lte(
            "updated_at", f"{ano}-12-31T23:59:59"
        )
        vendas_result = vendas_query.execute()
        vendas = vendas_result.data or []
    except Exception:
        logger.debug("Could not fetch sales data for DIMOB")

    # Rental operations (from contratos_locacao table)
    locacoes = []
    try:
        loc_result = supabase.table("contratos_locacao").select("*").gte(
            "data_inicio", f"{ano}-01-01"
        ).lte("data_inicio", f"{ano}-12-31").execute()
        locacoes = loc_result.data or []
    except Exception:
        logger.debug("contratos_locacao table not available, skipping rental data")

    return {
        "organizacao": org_data,
        "vendas": [
            {
                "id": v.get("id"),
                "nome_comprador": v.get("nome", ""),
                "cpf_comprador": "",
                "valor": v.get("valor_estimado", 0),
                "data_operacao": v.get("updated_at", ""),
            }
            for v in vendas
        ],
        "locacoes": [
            {
                "id": loc.get("id"),
                "cpf_locatario": "",
                "nome_locatario": "",
                "valor_aluguel": loc.get("valor_aluguel", 0),
                "data_inicio": loc.get("data_inicio", ""),
                "data_fim": loc.get("data_fim", ""),
            }
            for loc in locacoes
        ],
        "ano": ano,
    }


def preview_dimob(org_id: str, ano: int, supabase) -> dict:
    """
    Return data that would be included in the DIMOB declaration.
    Used for preview before generating the XML.
    """
    data = _fetch_dimob_data(org_id, ano, supabase)
    warnings = validate_dimob_data(data)

    return {
        "ano": ano,
        "total_vendas": len(data["vendas"]),
        "total_locacoes": len(data["locacoes"]),
        "valor_total_vendas": sum(float(v.get("valor") or 0) for v in data["vendas"]),
        "valor_total_locacoes": sum(
            float(loc.get("valor_aluguel") or 0) * 12 for loc in data["locacoes"]
        ),
        "vendas": data["vendas"],
        "locacoes": data["locacoes"],
        "avisos": warnings,
        "organizacao": data["organizacao"],
    }


def generate_dimob_xml(org_id: str, ano: int, supabase) -> str:
    """
    Generate complete DIMOB XML declaration.
    Returns the XML as a formatted string.
    """
    data = _fetch_dimob_data(org_id, ano, supabase)
    org = data.get("organizacao", {})

    # Root element
    root = Element("DIMOB")
    root.set("xmlns", "http://www.receita.fazenda.gov.br/dimob")
    root.set("ano_referencia", str(ano))

    # R01 — Declarant identification
    r01 = SubElement(root, "R01")
    SubElement(r01, "tipo_registro").text = "R01"
    SubElement(r01, "cnpj").text = _clean_doc(org.get("cnpj", ""))
    SubElement(r01, "razao_social").text = org.get("razao_social") or org.get("nome", "")
    SubElement(r01, "ano_calendario").text = str(ano)
    SubElement(r01, "situacao_especial").text = "N"

    # R02 — Intermediation operations (sales)
    for i, venda in enumerate(data.get("vendas", []), 1):
        r02 = SubElement(root, "R02")
        SubElement(r02, "tipo_registro").text = "R02"
        SubElement(r02, "sequencial").text = str(i).zfill(5)
        SubElement(r02, "cpf_comprador").text = _clean_doc(venda.get("cpf_comprador", ""))
        SubElement(r02, "nome_comprador").text = venda.get("nome_comprador", "")
        SubElement(r02, "data_operacao").text = _format_date(venda.get("data_operacao", ""))
        SubElement(r02, "valor_operacao").text = _format_money(venda.get("valor", 0))
        SubElement(r02, "valor_comissao").text = _format_money(
            float(venda.get("valor", 0)) * 0.06  # 6% commission default
        )

    # R03 — Rental operations
    for i, loc in enumerate(data.get("locacoes", []), 1):
        r03 = SubElement(root, "R03")
        SubElement(r03, "tipo_registro").text = "R03"
        SubElement(r03, "sequencial").text = str(i).zfill(5)
        SubElement(r03, "cpf_locatario").text = _clean_doc(loc.get("cpf_locatario", ""))
        SubElement(r03, "nome_locatario").text = loc.get("nome_locatario", "")

        # Monthly values (simplified — same value for all active months)
        valor_mensal = float(loc.get("valor_aluguel") or 0)
        for mes in range(1, 13):
            mes_el = SubElement(r03, f"valor_mes_{mes:02d}")
            mes_el.text = _format_money(valor_mensal)

    # R04 — Summary
    r04 = SubElement(root, "R04")
    SubElement(r04, "tipo_registro").text = "R04"
    SubElement(r04, "total_registros_r02").text = str(len(data.get("vendas", [])))
    SubElement(r04, "total_registros_r03").text = str(len(data.get("locacoes", [])))
    SubElement(r04, "valor_total_vendas").text = _format_money(
        sum(float(v.get("valor") or 0) for v in data.get("vendas", []))
    )
    SubElement(r04, "valor_total_locacoes").text = _format_money(
        sum(float(loc.get("valor_aluguel") or 0) * 12 for loc in data.get("locacoes", []))
    )

    # Pretty print
    xml_str = tostring(root, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    try:
        dom = parseString(xml_str)
        return dom.toprettyxml(indent="  ", encoding=None)
    except Exception:
        return xml_str


def _clean_doc(doc: str) -> str:
    """Remove formatting from CPF/CNPJ."""
    return "".join(c for c in (doc or "") if c.isdigit())


def _format_date(dt_str: str) -> str:
    """Format datetime string to DD/MM/YYYY."""
    if not dt_str:
        return ""
    try:
        from datetime import datetime
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return dt_str[:10] if len(dt_str) >= 10 else dt_str


def _format_money(value) -> str:
    """Format monetary value as string with 2 decimal places."""
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return "0.00"
