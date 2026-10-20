"""The 422 envelope of the agents app, without ever echoing the caller's input (Julia v2 IP/LGPD hygiene).

The seed's ``request_validation_exception_handler`` returns pydantic's raw ``msg`` per field; for a custom
validator (``value_error``) that text is whatever the validator wrote, and it can carry the offending value.
Agents' bodies hold lead text, secrets and prompt content, so this handler keeps the seed's envelope
(``VALIDATION_ERROR`` + ``details.errors[{field, message, type}]``) but builds every ``message`` from the
error TYPE alone: no ``input``, no ``ctx`` of a custom validator, no ``msg``.

NOC-REMEDIATE[seed-422-no-input-echo]: the same fix belongs in ``noctusai_lib.primitives.exceptions``
(``_validation_errors_response``) so every product gets it; until then agents overrides the handler in its app
setup (:func:`install_validation_handler`) -- 2026-10-20.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from noctusai_lib.primitives.exceptions import (
    _pt_br_validation_message,
    _validation_field,
    format_error_response,
)

__all__ = ["install_validation_handler", "request_validation_handler"]

_GENERICO = "Valor inválido"


def _mensagem(error: dict[str, Any]) -> str:
    tipo = error.get("type", "")
    # A custom validator's text/ctx is free-form (may carry the value): only fixed per-type templates speak.
    if tipo.startswith("value_error") or tipo.startswith("assertion"):
        return _GENERICO
    seguro = {"type": tipo, "ctx": {k: v for k, v in (error.get("ctx") or {}).items() if isinstance(v, (int, float))}}
    texto = _pt_br_validation_message({**seguro, "msg": _GENERICO})
    return texto or _GENERICO


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors, partes = [], []
    for e in exc.errors():
        campo = _validation_field(tuple(e["loc"]))
        msg = _mensagem(e)
        errors.append({"field": campo, "message": msg, "type": e["type"]})
        partes.append(f"{campo}: {msg}")
    return JSONResponse(
        status_code=422,
        content=format_error_response(
            code="VALIDATION_ERROR",
            message="; ".join(partes) or "Erro de validação nos dados enviados",
            details={"errors": errors},
        ),
    )


def install_validation_handler(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, request_validation_handler)
