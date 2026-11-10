"""Typed refusals of the roteiro lifecycle (CONTRACT roteiro-ciclo §3).

One small module so the roteiro service, the feedback service and the PDF route raise the SAME typed errors without
importing each other (they already depend on `roteiros_service`). Every error is a `RoteiroErro`, so the wire shape
is `{detail, code, message, details?}` (see `RoteiroErro`); the FE shows `message`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

MSG_SEM_IMOVEIS = "Adicione ao menos um imóvel."
MSG_SEM_DATA = "Informe a data da visita."
MSG_RASCUNHO_PDF = "Este roteiro ainda é um rascunho. Gere o roteiro para baixar o PDF."
MSG_SEM_PERMISSAO_REABRIR = (
    "Só supervisores, administradores e o proprietário da conta podem reabrir."
)


class RoteiroErro(HTTPException):
    """A typed refusal of the roteiro routes: `{code, message}` (+ `details`), pt-BR `message` (amendment v1.1 §4).

    Raised as an `HTTPException` whose detail is the seed's flat error shape `{detail, code}` — the ONE shape the
    seed's `http_exception_handler` passes through verbatim (a dict WITHOUT both keys would be stringified into
    `HTTP_ERROR`). The body is therefore `{"detail": <message>, "code": <code>, "message": <message>,
    "details"?: {...}}`: `ApiError.code` reads `code`, the toast reads `message`. Only these routes use it."""

    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict] = None) -> None:
        corpo: dict = {"detail": message, "code": code, "message": message}
        if details:
            corpo["details"] = details
        super().__init__(status_code=status_code, detail=corpo)
        self.code = code
        self.message = message
        self.details = details or {}


class RoteiroConflito(RoteiroErro):
    """409 — the roteiro is in the wrong state for this operation."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None) -> None:
        super().__init__(409, code, message, details)


class RoteiroInvalido(RoteiroErro):
    """422 — the request is well-formed but this roteiro / visita cannot take it."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None) -> None:
        super().__init__(422, code, message, details)


class RoteiroSemPermissao(RoteiroErro):
    """403 — the caller's role does not allow it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(403, code, message)


def roteiro_gerado() -> RoteiroConflito:
    return RoteiroConflito(
        "roteiro_gerado",
        "Este roteiro já foi gerado: não é possível adicionar, remover ou reordenar imóveis.",
    )


def roteiro_rascunho(acao: str = "registrar o resultado da visita") -> RoteiroConflito:
    return RoteiroConflito(
        "roteiro_rascunho",
        f"Este roteiro ainda é um rascunho. Gere o roteiro para {acao}.",
    )


def roteiro_rascunho_pdf() -> RoteiroConflito:
    return RoteiroConflito("roteiro_rascunho", MSG_RASCUNHO_PDF)


def roteiro_sem_data() -> RoteiroInvalido:
    return RoteiroInvalido("roteiro_sem_data", MSG_SEM_DATA)


def cancelada_incompleta() -> RoteiroInvalido:
    return RoteiroInvalido(
        "cancelada_incompleta",
        "Informe quem cancelou e o motivo do cancelamento.",
    )
