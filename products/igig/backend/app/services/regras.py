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

__all__ = ["RegraViolada", "http_de", "formatar_horas", "mensagem_horas_perdidas"]


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


def formatar_horas(minutos: int) -> str:
    """`125` → `"2h05"`; `40` → `"40 min"` — the same shape the FE's
    `formatarMinutos` (`components/esteira/formatos.ts`) renders, so a 409's
    message and the tela's own numbers never disagree."""
    horas, resto = divmod(max(0, minutos), 60)
    return f"{horas}h{resto:02d}" if horas else f"{resto} min"


def mensagem_horas_perdidas(minutos: int, quantidade_apontamentos: int) -> str:
    """The exact pt-BR sentence the delete-with-hours 409 carries.

    Named so the two call sites (excluir tarefa, remover pauta) say the same
    thing instead of hand-writing a slightly different sentence each.
    """
    unidade = "apontamento" if quantidade_apontamentos == 1 else "apontamentos"
    return (
        f"Isto tem {formatar_horas(minutos)} de horas apontadas em "
        f"{quantidade_apontamentos} {unidade}. Confirme a exclusão para perder esses registros."
    )
