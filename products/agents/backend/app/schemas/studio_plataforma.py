"""Schemas of the platform-definition routes (``/api/studio/plataforma/agents``): a platform definition is DATA
(049), created/read/updated through the Studio API; see ``app.studio.plataforma``."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.studio_geracao import Briefing, GeracaoOut
from noctusai_lib.api import StrictHttpModel

PLATAFORMA_KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
_ATRIBUTO_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"


class PlataformaAgentCreateRequest(StrictHttpModel):
    """Create the platform DEFINITION of any valid ``key`` (idempotent). Everything the old code registry carried is
    DATA here: set it now or later through ``PATCH /plataforma/agents/{key}``."""

    key: str = Field(..., pattern=PLATAFORMA_KEY_PATTERN)
    #: Required for a NEW key (422 ``nome_obrigatorio``); ignored for an existing one.
    nome: str | None = Field(default=None, min_length=1, max_length=80)
    descricao: str | None = Field(default=None, max_length=500)
    runtime: Literal["llm", "claude_sdk"] = "llm"
    owner_product: str | None = Field(default=None, min_length=1, max_length=64)
    escopo_qualificacao: str | None = Field(default=None, pattern=_ATRIBUTO_PATTERN)
    padrao_qualificacao: str | None = Field(default=None, pattern=_ATRIBUTO_PATTERN)
    #: Settings the first draft starts with (provider / model / effort / max_turns / idioma / tool_policy).
    rascunho_padrao: dict[str, Any] | None = None
    #: A published definition is instantiated in every org only when true (opt-in: an internal agent such as the
    #: draft generator must not appear in every org).
    instanciavel: bool = False
    papel: Literal["gerador", "exemplar"] | None = None
    #: When sent, an AI generation of the new draft starts right away (all areas, ``forcar=false``).
    briefing: Briefing | None = None
    limite_usd: float = Field(default=5.0, gt=0, le=5.0)


class PlataformaAgentUpdateRequest(StrictHttpModel):
    """Partial update (``exclude_unset``) of the DATA a platform definition carries."""

    nome: str | None = Field(default=None, min_length=1, max_length=80)
    descricao: str | None = Field(default=None, max_length=500)
    runtime: Literal["llm", "claude_sdk"] | None = None
    owner_product: str | None = Field(default=None, min_length=1, max_length=64)
    escopo_qualificacao: str | None = Field(default=None, pattern=_ATRIBUTO_PATTERN)
    padrao_qualificacao: str | None = Field(default=None, pattern=_ATRIBUTO_PATTERN)
    rascunho_padrao: dict[str, Any] | None = None
    instanciavel: bool | None = None
    papel: Literal["gerador", "exemplar"] | None = None


class PlataformaAgentOut(BaseModel):
    id: UUID
    key: str
    org_id: UUID
    nome: str
    descricao: str | None
    definition_scope: str
    conteudo_modo: str
    runtime: str
    owner_product: str | None
    usa_canais: bool
    escopo_qualificacao: str | None
    padrao_qualificacao: str | None
    rascunho_padrao: dict[str, Any] | None
    instanciavel: bool
    papel: str | None
    #: The generation started by ``briefing`` (``null`` when none was sent).
    geracao: GeracaoOut | None = None


class PlataformaGrantRequest(StrictHttpModel):
    """Grant ONE org the right to hold an instance of a closed (non-``instanciavel``) platform definition."""

    org_id: UUID


class PlataformaGrantsOut(BaseModel):
    """The orgs granted a definition (``instanciavel`` shown so a caller sees whether the grants even matter)."""

    key: str
    instanciavel: bool
    org_ids: list[UUID]
    #: ``True`` when this call created the grant (``False`` = it already existed).
    created: bool | None = None
