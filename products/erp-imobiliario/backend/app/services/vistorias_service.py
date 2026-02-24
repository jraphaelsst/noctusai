"""
Vistorias Service — Business logic for property inspections.

Provides default checklist templates and inspection utilities.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Default checklist template with common inspection items for Brazilian
# real-estate move-in / move-out inspections.
DEFAULT_CHECKLIST: List[Dict[str, Any]] = [
    {"item": "Paredes", "estado": "bom", "observacao": ""},
    {"item": "Teto / Forro", "estado": "bom", "observacao": ""},
    {"item": "Piso", "estado": "bom", "observacao": ""},
    {"item": "Portas", "estado": "bom", "observacao": ""},
    {"item": "Janelas", "estado": "bom", "observacao": ""},
    {"item": "Fechaduras / Maçanetas", "estado": "bom", "observacao": ""},
    {"item": "Instalação Elétrica", "estado": "bom", "observacao": ""},
    {"item": "Interruptores / Tomadas", "estado": "bom", "observacao": ""},
    {"item": "Instalação Hidráulica", "estado": "bom", "observacao": ""},
    {"item": "Torneiras / Registros", "estado": "bom", "observacao": ""},
    {"item": "Vasos Sanitários", "estado": "bom", "observacao": ""},
    {"item": "Pia / Lavatório", "estado": "bom", "observacao": ""},
    {"item": "Box / Chuveiro", "estado": "bom", "observacao": ""},
    {"item": "Armários Embutidos", "estado": "NA", "observacao": ""},
    {"item": "Bancadas / Tampos", "estado": "bom", "observacao": ""},
    {"item": "Pintura", "estado": "bom", "observacao": ""},
    {"item": "Vidros", "estado": "bom", "observacao": ""},
    {"item": "Interfone / Campainha", "estado": "bom", "observacao": ""},
    {"item": "Ar Condicionado", "estado": "NA", "observacao": ""},
    {"item": "Área Externa / Quintal", "estado": "NA", "observacao": ""},
    {"item": "Garagem / Vaga", "estado": "NA", "observacao": ""},
    {"item": "Limpeza Geral", "estado": "bom", "observacao": ""},
]

VALID_ESTADOS = {"bom", "regular", "ruim", "NA"}


def get_default_checklist() -> List[Dict[str, Any]]:
    """Return a fresh copy of the default checklist template."""
    import copy
    return copy.deepcopy(DEFAULT_CHECKLIST)


def validate_checklist(checklist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and normalise checklist items.

    Each item must have 'item' (str), 'estado' (one of VALID_ESTADOS),
    and optionally 'observacao'.
    """
    validated = []
    for entry in checklist:
        if not isinstance(entry, dict) or "item" not in entry:
            continue
        estado = entry.get("estado", "bom")
        if estado not in VALID_ESTADOS:
            estado = "bom"
        validated.append({
            "item": str(entry["item"]),
            "estado": estado,
            "observacao": str(entry.get("observacao", "")),
        })
    return validated


def summarise_checklist(checklist: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return a count of items per estado."""
    summary: Dict[str, int] = {"bom": 0, "regular": 0, "ruim": 0, "NA": 0}
    for entry in checklist:
        estado = entry.get("estado", "bom")
        if estado in summary:
            summary[estado] += 1
    return summary
