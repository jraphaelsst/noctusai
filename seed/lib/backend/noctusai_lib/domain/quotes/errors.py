"""Quote errors -- `AppException` subclasses (stable pt-BR `code`s, rendered by the seed handlers)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

ORCAMENTO_VAZIO = "orcamento_vazio"
ORCAMENTO_BLOQUEADO = "orcamento_bloqueado"
ORCAMENTO_EXPIRADO = "orcamento_expirado"
ORCAMENTO_ENCERRADO = "orcamento_encerrado"
ORCAMENTO_SUBSTITUIDO = "orcamento_substituido"
TRANSICAO_INVALIDA = "transicao_invalida"
DESCONTO_INVALIDO = "desconto_invalido"
CLIENTE_INVALIDO = "cliente_invalido"
ITEM_INVALIDO = "item_invalido"
LINHA_INVALIDA = "linha_invalida"
VALIDADE_INVALIDA = "validade_invalida"
CONSENTIMENTO_OBRIGATORIO = "consentimento_obrigatorio"
NOME_OBRIGATORIO = "nome_obrigatorio"
MOTIVO_OBRIGATORIO = "motivo_obrigatorio"
LINK_INVALIDO = "link_invalido"
LINK_INDISPONIVEL = "link_indisponivel"
EMAIL_INDISPONIVEL = "email_indisponivel"
ENVIO_FALHOU = "envio_falhou"
MODELO_INVALIDO = "modelo_invalido"
ASSINATURA_INVALIDA = "assinatura_invalida"
ASSINATURA_INDISPONIVEL = "assinatura_indisponivel"
CONVERSAO_INDISPONIVEL = "conversao_indisponivel"
NUMERACAO_FALHOU = "numeracao_falhou"


class QuotesError(OrganError):
    """A quotes refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(QuotesError)


def bad_link() -> QuotesError:
    """ONE answer for a forged, expired, foreign-org or wrong-purpose token -- never says which."""
    return QuotesError(LINK_INVALIDO, "Link inválido ou expirado.", 404)


__all__ = [name for name in dir() if name.isupper() and not name.startswith("_")] + [
    "QuotesError",
    "bad_link",
    "conflict",
    "invalid",
    "not_found",
]
