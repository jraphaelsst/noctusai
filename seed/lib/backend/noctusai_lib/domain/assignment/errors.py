"""Assignment errors -- `AppException`s so the seed handlers render `{"error": {"code", "message", "details"}}` (pt-BR)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

EQUIPE_INVALIDA = "equipe_invalida"
EQUIPE_DUPLICADA = "equipe_duplicada"
MEMBRO_INVALIDO = "membro_invalido"
MEMBRO_DUPLICADO = "membro_duplicado"
MEMBRO_NAO_ENCONTRADO = "membro_nao_encontrado"
ORDEM_INVALIDA = "ordem_invalida"
REGRA_INVALIDA = "regra_invalida"
ESTRATEGIA_INVALIDA = "estrategia_invalida"
CAPACIDADE_ESGOTADA = "capacidade_esgotada"
SEM_CANDIDATO = "sem_candidato"
ATRIBUICAO_NAO_ENCONTRADA = "atribuicao_nao_encontrada"
FILTRO_INVALIDO = "filtro_invalido"
SEM_PERMISSAO_CODE = "sem_permissao"


class AssignmentError(OrganError):
    """An assignment refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(AssignmentError)


class CapacityFull(Exception):
    """The ledger refused an assignment: the member is at capacity (checked under a per-member lock, not in Python)."""


class SubjectNotFound(Exception):
    """The ledger could not write the owner onto the subject's card (no such row for this org)."""


__all__ = [
    "ATRIBUICAO_NAO_ENCONTRADA", "AssignmentError", "CAPACIDADE_ESGOTADA", "CapacityFull", "EQUIPE_DUPLICADA", "EQUIPE_INVALIDA",
    "ESTRATEGIA_INVALIDA", "FILTRO_INVALIDO", "MEMBRO_DUPLICADO", "MEMBRO_INVALIDO", "MEMBRO_NAO_ENCONTRADO", "ORDEM_INVALIDA",
    "REGRA_INVALIDA", "SEM_CANDIDATO", "SEM_PERMISSAO_CODE", "SubjectNotFound", "conflict", "invalid", "not_found",
]
