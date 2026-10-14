"""Purchasing errors -- `AppException` subclasses (stable pt-BR `code`s, rendered by the seed handlers).

RPC refusals (raised inside Postgres, returned as `{"status": "refused", "code"}`) use the same constants.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found
from noctusai_lib.primitives.exceptions import AppException

PEDIDO_INEXISTENTE = "pedido_inexistente"
PEDIDO_NAO_EDITAVEL = "pedido_nao_editavel"
TRANSICAO_INVALIDA = "transicao_invalida"
PEDIDO_COM_RECEBIMENTO = "pedido_com_recebimento"
PEDIDO_NAO_RECEBIVEL = "pedido_nao_recebivel"
PEDIDO_JA_RECEBIDO = "pedido_ja_recebido"
PEDIDO_CANCELADO = "pedido_cancelado"
PEDIDO_NAO_APROVADO = "pedido_nao_aprovado"
RECEBIMENTO_EXCEDE_PEDIDO = "recebimento_excede_pedido"
LINHA_INVALIDA = "linha_invalida"
SEM_LINHAS = "sem_linhas"
PEDIDO_SEM_VALOR = "pedido_sem_valor"
VALOR_INVALIDO = "valor_invalido"
DESCONTO_EXCEDE = "desconto_excede"
PARCELAS_INVALIDAS = "parcelas_invalidas"
PRAZO_INVALIDO = "prazo_invalido"
FORNECEDOR_INVALIDO = "fornecedor_invalido"
DEPOSITO_INVALIDO = "deposito_invalido"
ITEM_INVALIDO = "item_invalido"
ITEM_OBRIGATORIO = "item_obrigatorio"
QUANTIDADE_INVALIDA = "quantidade_invalida"
CHAVE_REUTILIZADA = "chave_reutilizada"
SEM_PERMISSAO_APROVAR = "sem_permissao_aprovar"
APROVACAO_ACIMA_DO_LIMITE = "aprovacao_acima_do_limite"
LIMITE_EM_CARENCIA = "limite_em_carencia"
SEM_PERMISSAO_LIMITE = "sem_permissao_limite"
USUARIO_INVALIDO = "usuario_invalido"

#: Codes the RPCs may answer with; anything else is a bug and surfaces loudly.
RPC_REFUSAL_CODES = frozenset(
    {
        PEDIDO_INEXISTENTE, PEDIDO_NAO_EDITAVEL, TRANSICAO_INVALIDA, PEDIDO_COM_RECEBIMENTO, PEDIDO_NAO_RECEBIVEL,
        PEDIDO_JA_RECEBIDO, PEDIDO_CANCELADO, PEDIDO_NAO_APROVADO, RECEBIMENTO_EXCEDE_PEDIDO, LINHA_INVALIDA, SEM_LINHAS,
        PEDIDO_SEM_VALOR, VALOR_INVALIDO, DESCONTO_EXCEDE, PARCELAS_INVALIDAS, PRAZO_INVALIDO, FORNECEDOR_INVALIDO,
        DEPOSITO_INVALIDO, ITEM_INVALIDO, ITEM_OBRIGATORIO, QUANTIDADE_INVALIDA, CHAVE_REUTILIZADA, APROVACAO_ACIMA_DO_LIMITE,
        LIMITE_EM_CARENCIA, USUARIO_INVALIDO,
    }
)

_MESSAGES = {
    PEDIDO_INEXISTENTE: "Pedido de compra não encontrado.",
    PEDIDO_NAO_EDITAVEL: "Só é possível editar um pedido em rascunho.",
    TRANSICAO_INVALIDA: "O pedido não pode mudar para este status a partir do atual.",
    PEDIDO_COM_RECEBIMENTO: "O pedido já tem recebimento e não pode ser cancelado.",
    PEDIDO_NAO_RECEBIVEL: "O pedido não está em um status que aceite recebimento.",
    PEDIDO_JA_RECEBIDO: "O pedido já foi recebido por completo.",
    PEDIDO_CANCELADO: "O pedido está cancelado.",
    PEDIDO_NAO_APROVADO: "O pedido ainda não foi aprovado.",
    RECEBIMENTO_EXCEDE_PEDIDO: "A quantidade recebida excede o saldo do pedido.",
    LINHA_INVALIDA: "Linha do pedido inválida.",
    SEM_LINHAS: "Informe ao menos uma linha.",
    PEDIDO_SEM_VALOR: "O pedido precisa ter valor maior que zero.",
    VALOR_INVALIDO: "Valor inválido.",
    DESCONTO_EXCEDE: "O desconto excede o total do pedido.",
    PARCELAS_INVALIDAS: "Número de parcelas inválido.",
    PRAZO_INVALIDO: "Prazo de pagamento inválido.",
    FORNECEDOR_INVALIDO: "Fornecedor não encontrado.",
    DEPOSITO_INVALIDO: "Depósito não encontrado.",
    ITEM_INVALIDO: "Item não encontrado.",
    ITEM_OBRIGATORIO: "Toda linha precisa de um item do cadastro (o recebimento dá entrada no estoque).",
    QUANTIDADE_INVALIDA: "Quantidade inválida.",
    CHAVE_REUTILIZADA: "Esta chave de idempotência já foi usada em outro pedido.",
    APROVACAO_ACIMA_DO_LIMITE: "Pedidos acima do limite de aprovação só podem ser aprovados por um aprovador.",
    LIMITE_EM_CARENCIA: "O limite de aprovação foi alterado há pouco; pedidos acima do menor limite vigente aguardam o fim da carência.",
    USUARIO_INVALIDO: "Usuário inválido.",
}

_CONFLICT = {
    PEDIDO_NAO_EDITAVEL, TRANSICAO_INVALIDA, PEDIDO_COM_RECEBIMENTO, PEDIDO_NAO_RECEBIVEL, PEDIDO_JA_RECEBIDO,
    PEDIDO_CANCELADO, PEDIDO_NAO_APROVADO, RECEBIMENTO_EXCEDE_PEDIDO, CHAVE_REUTILIZADA, LIMITE_EM_CARENCIA,
}
_FORBIDDEN = {APROVACAO_ACIMA_DO_LIMITE}


class PurchasingError(OrganError):
    """A purchasing refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(PurchasingError)


def forbidden(code: str, message: str) -> PurchasingError:
    return PurchasingError(code, message, 403)


def from_refusal(payload: dict) -> AppException:
    """Map an RPC `{"status": "refused", "code"}` onto the right HTTP error (404 / 409 state / 422 input)."""
    code = str(payload.get("code") or "")
    if code not in RPC_REFUSAL_CODES:
        raise RuntimeError(f"purchasing RPC answered an unknown refusal code {code!r}: {payload!r}")
    if code == PEDIDO_INEXISTENTE:
        return not_found("Pedido de compra")
    status = 403 if code in _FORBIDDEN else 409 if code in _CONFLICT else 422
    details = {k: payload[k] for k in ("order_line_id", "item_id") if payload.get(k)}
    return PurchasingError(code, _MESSAGES.get(code, code), status, details=details)


__all__ = [
    "APROVACAO_ACIMA_DO_LIMITE",
    "LIMITE_EM_CARENCIA",
    "SEM_PERMISSAO_LIMITE",
    "PurchasingError",
    "RPC_REFUSAL_CODES",
    "SEM_PERMISSAO_APROVAR",
    "conflict",
    "forbidden",
    "from_refusal",
    "invalid",
    "not_found",
]
