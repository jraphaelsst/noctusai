"""A business-rule refusal with a MACHINE code — the shape the boards' UI keys on.

The pipeline services refuse moves for reasons the frontend must react to
differently ("which orçamento was accepted?" dialog vs "type a reason" prompt),
so a free-text message is not enough. Services raise :class:`RegraViolada`;
routers translate it with :func:`http_de`, which produces the seed's
flat machine-error body ``{"detail": "<pt-BR message>", "code": "<code>"}``
(passed through verbatim by `noctusai_lib.primitives.exceptions.
http_exception_handler`).

Services stay FastAPI-free on purpose — they are called from routers, jobs and
tests alike.
"""
from __future__ import annotations

from fastapi import HTTPException

__all__ = ["RegraViolada", "http_de"]


class RegraViolada(Exception):
    """A request the domain refuses. `status` is the HTTP status to answer."""

    def __init__(self, status: int, code: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status
        self.code = code
        self.mensagem = mensagem


def http_de(erro: RegraViolada) -> HTTPException:
    return HTTPException(
        status_code=erro.status, detail={"detail": erro.mensagem, "code": erro.code}
    )
