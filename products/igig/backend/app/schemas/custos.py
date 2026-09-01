"""Pydantic contracts for the custo/hora surface (funções + profissionais).

The spec (`PROJETO-IGIG-ERP.md` § Módulo 1) says the calculadora prices from
"a tabela de custo/hora dos profissionais cadastrados" but never says how that
table is filled. Migration `008` settled the model — role default plus an
optional per-person override, resolved by
``ProfissionalRepository.custo_hora_efetivo`` — and this module is the HTTP
boundary that finally makes it reachable.

Why it matters beyond Módulo 1: the same rate feeds M5's BI de eficiência
(custo real do job) and M6's DRE (margem por conta). With no way to enter it,
all three report R$ 0,00 — which reads as a real answer rather than as missing
input. That is the failure this surface removes.

``StrictHttpModel`` on the request side per
``KB § PATTERNS/backend/pydantic-strict-http.md``: an unknown key is a 422,
not a silently ignored field.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "FuncaoCreate",
    "FuncaoUpdate",
    "FuncaoOut",
    "ProfissionalCreate",
    "ProfissionalUpdate",
    "ProfissionalOut",
]


# ─── Função ────────────────────────────────────────────────────────────────

class FuncaoCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=120)
    # 0 is allowed and meaningful (an unpaid role); negative is not.
    custo_hora_padrao: float = Field(default=0, ge=0)


class FuncaoUpdate(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    custo_hora_padrao: float | None = Field(default=None, ge=0)


class FuncaoOut(BaseModel):
    """Tolerant of extra columns so a schema addition doesn't break the
    endpoint before the model catches up."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    nome: str
    custo_hora_padrao: float = 0
    created_at: str | None = None
    updated_at: str | None = None


# ─── Profissional ──────────────────────────────────────────────────────────

class ProfissionalCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=200)
    funcao_id: str | None = None
    # NULL means "inherit the função's default"; 0 is a real rate. The two
    # must stay distinguishable, so this is Optional rather than defaulted.
    custo_hora_override: float | None = Field(default=None, ge=0)
    usuario_id: str | None = None
    ativo: bool = True


class ProfissionalUpdate(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    funcao_id: str | None = None
    custo_hora_override: float | None = Field(default=None, ge=0)
    usuario_id: str | None = None
    ativo: bool | None = None


class ProfissionalOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    nome: str
    funcao_id: str | None = None
    custo_hora_override: float | None = None
    usuario_id: str | None = None
    ativo: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    #: Resolved rate (override → função default). Computed, not stored — the
    #: UI needs to show what a person ACTUALLY costs without re-implementing
    #: the resolution rule and drifting from `custo_hora_efetivo`.
    custo_hora_efetivo: float | None = None
    #: NULL rate with no função and no override. Surfaced as a field rather
    #: than hidden, so the UI can flag the row that silently zeroes the DRE.
    custo_hora_indefinido: bool = False
