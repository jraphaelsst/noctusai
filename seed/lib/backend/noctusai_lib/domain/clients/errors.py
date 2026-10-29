"""Clients errors -- `AppException`s so the seed handlers render `{"error": {"code", "message", "details"}}`.

The three refusal codes the contract names (`CLIENTE_COM_FINANCEIRO`, `SESSAO_COM_PAGAMENTO`,
`VALOR_EXCEDE_ABERTO`) are spelled exactly as the FE matches them; validation codes follow the leads organ.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

#: 409 -- the client has a booked receivable; deleting would orphan money (the UI suggests status `encerrado`)
CLIENTE_COM_FINANCEIRO = "CLIENTE_COM_FINANCEIRO"
#: 409 -- the session's receivable already has a settlement (no delete / un-bill / price change)
SESSAO_COM_PAGAMENTO = "SESSAO_COM_PAGAMENTO"
#: 422 -- a payment larger than what the chosen receivables still owe
VALOR_EXCEDE_ABERTO = "VALOR_EXCEDE_ABERTO"

STATUS_INVALIDO = "status_invalido"
TELEFONE_INVALIDO = "telefone_invalido"
DOCUMENTO_INVALIDO = "documento_invalido"
METODO_INVALIDO = "metodo_invalido"
FILTRO_INVALIDO = "filtro_invalido"
NOME_OBRIGATORIO = "nome_obrigatorio"
AGENDA_INVALIDA = "agenda_invalida"
LANCAMENTO_INVALIDO = "lancamento_invalido"
VALOR_INVALIDO = "valor_invalido"


class ClientsError(OrganError):
    """A clients refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(ClientsError)


class ClientConflictError(Exception):
    """The store refused an insert: a client for that lead already exists in the org (UNIQUE guard)."""


__all__ = [
    "AGENDA_INVALIDA",
    "CLIENTE_COM_FINANCEIRO",
    "ClientConflictError",
    "ClientsError",
    "DOCUMENTO_INVALIDO",
    "FILTRO_INVALIDO",
    "LANCAMENTO_INVALIDO",
    "METODO_INVALIDO",
    "NOME_OBRIGATORIO",
    "SESSAO_COM_PAGAMENTO",
    "STATUS_INVALIDO",
    "TELEFONE_INVALIDO",
    "VALOR_EXCEDE_ABERTO",
    "VALOR_INVALIDO",
    "conflict",
    "invalid",
    "not_found",
]
