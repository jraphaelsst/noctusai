"""Request/response schemas for the `card_hub` module.

Contract: `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md` §3.
Request bodies are `StrictHttpModel` (`extra="forbid"`) — the HTTP-boundary
defense against silent-drop misroutes. Response shapes are plain `dict`
(mirroring `app/routers/clientes_router.py::get_cliente_route`'s
established, pragmatic house convention — this product does not require a
`response_model=` on every read route; correctness is enforced by tests,
not by a second parallel schema declaration for every read shape).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

_HEX_COLOR_LEN = 7  # "#rrggbb"


def _validate_hex_color(value: str) -> str:
    if (
        len(value) != _HEX_COLOR_LEN
        or not value.startswith("#")
        or not all(c in "0123456789abcdefABCDEF" for c in value[1:])
    ):
        raise ValueError(f"cor must be a hex colour like #a1b2c3, got {value!r}")
    return value


# ─── Notas ──────────────────────────────────────────────────────────────


class NotaCreateBody(StrictHttpModel):
    corpo: str = Field(min_length=1)
    # Contract correction (surfaced by the frontend engineer): Descrição
    # (one per card) and Comentários (many, chronological) are distinct
    # Trello concepts the original contract conflated. Defaults to
    # 'comentario' — the common case, and the one every existing caller
    # (built before this correction) already assumes.
    tipo: Literal["descricao", "comentario"] = "comentario"


class NotaUpdateBody(StrictHttpModel):
    corpo: str = Field(min_length=1)


# ─── Tags ───────────────────────────────────────────────────────────────


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


class ClienteTagsSetBody(StrictHttpModel):
    tag_ids: list[UUID] = Field(default_factory=list)


# ─── Membros ────────────────────────────────────────────────────────────


class MembrosSetBody(StrictHttpModel):
    lead_corretor_ids: list[UUID] = Field(default_factory=list)


# ─── Datas + lembretes ──────────────────────────────────────────────────

_RECORRENCIA_VALUES = {None, "diaria", "semanal", "mensal", "anual"}


class DatasPatchBody(StrictHttpModel):
    data_inicio: Optional[str] = None
    data_entrega: Optional[str] = None
    entrega_concluida: Optional[bool] = None
    lembrete_minutos_antes: Optional[int] = Field(default=None, ge=0)
    recorrencia: Optional[str] = None

    @field_validator("recorrencia")
    @classmethod
    def _validate_recorrencia(cls, v: Optional[str]) -> Optional[str]:
        if v not in _RECORRENCIA_VALUES:
            raise ValueError(
                f"recorrencia must be one of {sorted(x for x in _RECORRENCIA_VALUES if x)} or null, got {v!r}"
            )
        return v


# ─── Checklists ─────────────────────────────────────────────────────────


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


# ─── Documentos ─────────────────────────────────────────────────────────
#
# No body model for DELETE — contract correction: the seed `ApiClient
# .delete()` has no body parameter, and a DELETE-with-body is poorly
# supported across the stack generally. `motivo` travels as a required
# query parameter instead (see `router.py`'s `delete_documento_route`).


__all__ = [
    "ChecklistCreateBody",
    "ChecklistItemCreateBody",
    "ChecklistItemUpdateBody",
    "ChecklistUpdateBody",
    "ClienteTagsSetBody",
    "DatasPatchBody",
    "MembrosSetBody",
    "NotaCreateBody",
    "NotaUpdateBody",
    "TagCreateBody",
    "TagUpdateBody",
]
