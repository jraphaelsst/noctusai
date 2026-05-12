"""
Locacoes Service — Business logic for rental/lease contract management.

Handles rent adjustment calculations and monthly charge generation.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Standard readjustment indices (sample annual rates — real-world values
# would be fetched from an external API such as the IBGE SIDRA service)
DEFAULT_INDICES = {
    "IGPM": 4.52,   # placeholder annual %
    "IPCA": 4.62,
    "INPC": 4.47,
    "fixo": 0.0,
}


# ---------------------------------------------------------------------------
# DTO mapper (Phase 3b — operational contract, NOT response_model)
# ---------------------------------------------------------------------------
# Whitelist mirrors `frontend/src/types/locacoes.ts → interface ContratoLocacao`.
# response_model=PydanticDTO rollout deferred per PROJECT.md §7 Q-E.
_CONTRATO_LOCACAO_DTO_FIELDS: tuple = (
    "id",
    "org_id",
    "imovel_id",
    "locatario_id",
    "proprietario_id",
    "valor_aluguel",
    "dia_vencimento",
    "data_inicio",
    "data_fim",
    "indice_reajuste",
    "percentual_reajuste",
    "status",
    "taxa_administracao",
    "valor_caucao",
    "observacoes",
    "created_at",
    "updated_at",
)


def contrato_locacao_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a raw DB row to the operational ContratoLocacao DTO contract."""
    if not row:
        return row
    return {k: row.get(k) for k in _CONTRATO_LOCACAO_DTO_FIELDS if k in row}


def contrato_locacao_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of raw DB rows to ContratoLocacao DTO shape."""
    if not rows:
        return []
    return [contrato_locacao_row_to_dto(r) for r in rows]


def calculate_reajuste(
    valor_atual: float,
    indice: str,
    percentual: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate the adjusted rent value.

    If the index is 'fixo', `percentual` is used directly.
    Otherwise the standard rate for the index is used, and `percentual`
    can override it.

    Returns a dict with calculation details.
    """
    if indice == "fixo":
        taxa = percentual if percentual is not None else 0.0
    else:
        taxa = percentual if percentual is not None else DEFAULT_INDICES.get(indice, 0.0)

    valor_novo = round(valor_atual * (1 + taxa / 100), 2)
    diferenca = round(valor_novo - valor_atual, 2)

    return {
        "valor_anterior": valor_atual,
        "valor_novo": valor_novo,
        "diferenca": diferenca,
        "indice": indice,
        "percentual_aplicado": taxa,
    }


def generate_monthly_charges(
    contrato: Dict[str, Any],
    supabase,
) -> List[Dict[str, Any]]:
    """
    Create monthly rent charge entries (lancamentos) for a lease contract.

    Generates one entry per month from data_inicio to data_fim.
    Returns the list of created charge records.
    """
    contrato_id = contrato["id"]
    org_id = contrato["org_id"]
    valor = float(contrato["valor_aluguel"])
    dia_vencimento = int(contrato.get("dia_vencimento", 10))

    data_inicio = _parse_date(contrato["data_inicio"])
    data_fim = _parse_date(contrato["data_fim"])

    charges: List[Dict[str, Any]] = []

    current = date(data_inicio.year, data_inicio.month, 1)
    end = date(data_fim.year, data_fim.month, 1)

    while current <= end:
        # Clamp day to the last day of the month
        last_day = _last_day_of_month(current.year, current.month)
        dia = min(dia_vencimento, last_day)
        vencimento = date(current.year, current.month, dia)

        charges.append({
            "org_id": org_id,
            "contrato_id": contrato_id,
            "tipo": "aluguel",
            "valor": valor,
            "data_vencimento": vencimento.isoformat(),
            "status": "pendente",
            "descricao": f"Aluguel ref. {current.strftime('%m/%Y')}",
        })

        # Advance to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if charges:
        try:
            result = supabase.table("lancamentos").insert(charges).execute()
            return result.data or charges
        except Exception as e:
            logger.warning(f"Failed to insert lancamentos: {e}")
            return charges

    return charges


def _parse_date(value) -> date:
    """Parse a date string (YYYY-MM-DD) or return as-is if already a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _last_day_of_month(year: int, month: int) -> int:
    """Return the last day of the given month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
