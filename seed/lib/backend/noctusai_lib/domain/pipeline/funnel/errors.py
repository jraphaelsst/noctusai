"""The funnel organ's refusals — one `AppException` per contract error code.

They ride the platform's standard error envelope
(`noctusai_lib.primitives.exceptions.app_exception_handler`:
``{"error": {"code", "message", "details"}}``), so every product's existing
handler renders them and the frontend's one error parser reads them. The
machine `code` is the funnel contract's (`card_not_found`, `gate_refused`, ...).
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.primitives.exceptions import AppException


class FunnelError(AppException):
    def __init__(self, code: str, message: str, status_code: int, details: Optional[dict[str, Any]] = None):
        super().__init__(code=code, message=message, status_code=status_code, details=details)


def card_not_found(card_id: Any) -> FunnelError:
    return FunnelError("card_not_found", "Card não encontrado.", 404, {"id": str(card_id)})


def stage_not_found(stage_id: Any) -> FunnelError:
    return FunnelError("stage_not_found", "Etapa não encontrada.", 404, {"id": str(stage_id)})


def acao_desconhecida(codigo: str) -> FunnelError:
    return FunnelError("acao_desconhecida", "Ação indisponível para este card.", 404, {"acao": codigo})


def card_fechado(status: Any) -> FunnelError:
    return FunnelError(
        "card_fechado", "O card está fechado; reabra-o antes de alterá-lo.", 409, {"status": str(status)}
    )


def etapa_inativa(stage_id: Any = None) -> FunnelError:
    return FunnelError(
        "etapa_inativa",
        "A etapa está inativa.",
        409,
        {"id": str(stage_id)} if stage_id else None,
    )


def motivo_obrigatorio(field: str) -> FunnelError:
    return FunnelError("motivo_obrigatorio", "Informe o motivo.", 422, {"field": field})


def motivo_desconhecido(codigo: Any) -> FunnelError:
    return FunnelError("motivo_desconhecido", "Motivo de perda desconhecido.", 422, {"motivo_codigo": str(codigo)})


def campo_nao_editavel(campo: str) -> FunnelError:
    return FunnelError("campo_nao_editavel", "Campo não editável.", 422, {"campo": campo})


__all__ = [
    "FunnelError",
    "acao_desconhecida",
    "campo_nao_editavel",
    "card_fechado",
    "card_not_found",
    "etapa_inativa",
    "motivo_desconhecido",
    "motivo_obrigatorio",
    "stage_not_found",
]
