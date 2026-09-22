"""Request bodies for the card-hub routes.

`StrictHttpModel` (`extra="forbid"`) throughout — the HTTP-boundary defence
against silent-drop misroutes. Responses are plain dicts (the lifted
contract's own convention; correctness is pinned by tests, not by a parallel
response-schema declaration).

Two bodies depend on the config and are BUILT per router
(`entity_tags_body` / `membros_body`): the member list's field name is part of
the HTTP contract (social-wiring: `lead_corretor_ids`), and the tag-set body's
schema name carries the entity (`ClienteTagsSetBody`) — both must come out
byte-identical for a product adopting the factory.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, create_model, field_validator

from noctusai_lib.api import StrictHttpModel

from .config import CardHubConfig

_HEX_COLOR_LEN = 7  # "#rrggbb"


def _validate_hex_color(value: str) -> str:
    if (
        len(value) != _HEX_COLOR_LEN
        or not value.startswith("#")
        or not all(c in "0123456789abcdefABCDEF" for c in value[1:])
    ):
        raise ValueError(f"cor must be a hex colour like #a1b2c3, got {value!r}")
    return value


# ─── Notas ───────────────────────────────────────────────────────────────


class NotaCreateBody(StrictHttpModel):
    corpo: str = Field(min_length=1)
    # Descrição (one per card) and Comentários (many) are distinct concepts;
    # `comentario` is the common case and the default.
    tipo: Literal["descricao", "comentario"] = "comentario"


class NotaUpdateBody(StrictHttpModel):
    corpo: str = Field(min_length=1)


# ─── Tags ────────────────────────────────────────────────────────────────


class TagCreateBody(StrictHttpModel):
    nome: str = Field(min_length=1)
    cor: str

    _validate_cor = field_validator("cor")(_validate_hex_color)


class TagUpdateBody(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1)
    cor: Optional[str] = None

    _validate_cor = field_validator("cor")(
        lambda v: _validate_hex_color(v) if v is not None else v
    )


def entity_tags_body(cfg: CardHubConfig) -> type[StrictHttpModel]:
    """`PUT /{id}/tags` body — `{"tag_ids": [...]}`, named
    `<Entity>TagsSetBody`."""
    return create_model(
        f"{cfg.entity_kind[:1].upper()}{cfg.entity_kind[1:]}TagsSetBody",
        __base__=StrictHttpModel,
        tag_ids=(list[UUID], Field(default_factory=list)),
    )


# ─── Membros ─────────────────────────────────────────────────────────────


def membros_body(cfg: CardHubConfig) -> type[StrictHttpModel]:
    """`PUT /{id}/membros` body — `{"<member_source.body_key>": [...]}`."""
    return create_model(
        "MembrosSetBody",
        __base__=StrictHttpModel,
        **{cfg.member_source.body_key: (list[UUID], Field(default_factory=list))},
    )


# ─── Checklists ──────────────────────────────────────────────────────────


class ChecklistCreateBody(StrictHttpModel):
    titulo: str = Field(min_length=1)


class ChecklistUpdateBody(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, min_length=1)
    posicao: Optional[int] = None


class ChecklistItemCreateBody(StrictHttpModel):
    texto: str = Field(min_length=1)


class ChecklistItemUpdateBody(StrictHttpModel):
    texto: Optional[str] = Field(default=None, min_length=1)
    concluido: Optional[bool] = None
    posicao: Optional[int] = None


# ─── Checklist extras ────────────────────────────────────────────────────


class ChecklistExtraCreateBody(StrictHttpModel):
    label: str = Field(min_length=1)
    #: Decided at creation and immutable — the PATCH body has no `tipo`: a
    #: flipped line would strand a `valor_texto` or a document.
    tipo: Literal["texto", "arquivo"]


class ChecklistExtraPatchBody(StrictHttpModel):
    """Every field optional; ABSENCE means "leave alone". `None` is a real
    value (clearing `valor_texto` unticks the line), so the route reads
    `model_fields_set`, never `exclude_none`."""

    label: Optional[str] = Field(default=None, min_length=1)
    valor_texto: Optional[str] = None
    ordem: Optional[int] = None


__all__ = [
    "ChecklistCreateBody",
    "ChecklistExtraCreateBody",
    "ChecklistExtraPatchBody",
    "ChecklistItemCreateBody",
    "ChecklistItemUpdateBody",
    "ChecklistUpdateBody",
    "NotaCreateBody",
    "NotaUpdateBody",
    "TagCreateBody",
    "TagUpdateBody",
    "entity_tags_body",
    "membros_body",
]
