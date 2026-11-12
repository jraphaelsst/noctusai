"""Activities errors -- `AppException` subclasses (stable pt-BR `code`s, rendered by the seed handlers).

The RPC refusal codes (raised inside Postgres) are the same constants: the service maps
`{"status": "refused", "code": ...}` straight onto `ActivitiesError(code, ...)`.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

TIPO_INVALIDO = "tipo_invalido"
TIPO_DUPLICADO = "tipo_duplicado"
RESPONSAVEL_INVALIDO = "responsavel_invalido"
DESFECHO_INVALIDO = "desfecho_invalido"
TITULO_INVALIDO = "titulo_invalido"
ATIVIDADE_ENCERRADA = "atividade_encerrada"
ATIVIDADE_INEXISTENTE = "atividade_inexistente"
FILTRO_INVALIDO = "filtro_invalido"

#: Codes the RPCs may answer with; anything else is a bug and surfaces loudly.
RPC_REFUSAL_CODES = frozenset({TIPO_INVALIDO, DESFECHO_INVALIDO, TITULO_INVALIDO, ATIVIDADE_ENCERRADA, ATIVIDADE_INEXISTENTE})

_MESSAGES = {
    TIPO_INVALIDO: "Tipo de atividade inexistente ou inativo.",
    TIPO_DUPLICADO: "Já existe um tipo de atividade com este código.",
    RESPONSAVEL_INVALIDO: "O responsável precisa ser um membro ativo da organização.",
    DESFECHO_INVALIDO: "Desfecho inválido.",
    TITULO_INVALIDO: "Informe o título da atividade.",
    ATIVIDADE_ENCERRADA: "A atividade já foi encerrada (concluída ou cancelada).",
    FILTRO_INVALIDO: "Filtro inválido.",
}


class ActivitiesError(OrganError):
    """An activities refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(ActivitiesError)


def from_refusal(payload: dict):
    """Map an RPC `{"status": "refused", "code"}` onto the right HTTP error (404 missing, 409 closed, 422 input)."""
    code = str(payload.get("code") or "")
    if code not in RPC_REFUSAL_CODES:
        raise RuntimeError(f"activities RPC answered an unknown refusal code {code!r}: {payload!r}")
    if code == ATIVIDADE_INEXISTENTE:
        return not_found("Atividade")
    return ActivitiesError(code, _MESSAGES[code], 409 if code == ATIVIDADE_ENCERRADA else 422)


__all__ = [
    "ATIVIDADE_ENCERRADA",
    "ATIVIDADE_INEXISTENTE",
    "ActivitiesError",
    "DESFECHO_INVALIDO",
    "FILTRO_INVALIDO",
    "RESPONSAVEL_INVALIDO",
    "RPC_REFUSAL_CODES",
    "TIPO_DUPLICADO",
    "TIPO_INVALIDO",
    "TITULO_INVALIDO",
    "conflict",
    "from_refusal",
    "invalid",
    "not_found",
]
