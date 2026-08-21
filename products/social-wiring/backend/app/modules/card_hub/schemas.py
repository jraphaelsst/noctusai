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


# ─── Agendamentos (many per atendimento — migration 061) ────────────────

#: Mirrors the DB CHECK in `061`. Both exist on purpose: the schema protects
#: the API surface, the CHECK protects every other writer (a migration, a
#: script, a future job). Neither is redundant with the other.
_TIPO_AGENDAMENTO_VALUES = {"visita", "ligacao", "reuniao", "outro"}


class AgendamentoCreateBody(StrictHttpModel):
    quando: str
    tipo: str = "outro"
    nota: Optional[str] = None
    #: `None` = no reminder wanted; `0` = "at the time". Kept distinct — a
    #: default of 0 would schedule a notification for every appointment ever
    #: created, which is how a reminder feature becomes a thing people mute.
    lembrete_minutos_antes: Optional[int] = Field(default=None, ge=0)
    #: Optional: with one open atendimento the server resolves it. Sent
    #: explicitly when the person has several, which the server REFUSES to
    #: guess at (409) rather than filing the appointment against the wrong deal.
    atendimento_id: Optional[UUID] = None

    @field_validator("tipo")
    @classmethod
    def _validate_tipo(cls, v: str) -> str:
        if v not in _TIPO_AGENDAMENTO_VALUES:
            raise ValueError(
                f"tipo must be one of {sorted(_TIPO_AGENDAMENTO_VALUES)}, got {v!r}"
            )
        return v


class AgendamentoPatchBody(StrictHttpModel):
    quando: Optional[str] = None
    tipo: Optional[str] = None
    nota: Optional[str] = None
    lembrete_minutos_antes: Optional[int] = Field(default=None, ge=0)

    @field_validator("tipo")
    @classmethod
    def _validate_tipo(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TIPO_AGENDAMENTO_VALUES:
            raise ValueError(
                f"tipo must be one of {sorted(_TIPO_AGENDAMENTO_VALUES)}, got {v!r}"
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


# ─── Documento checklist (migration 067 — canonical items, per-client ticks) ──


class DocumentoChecklistPatchBody(StrictHttpModel):
    """Tick or untick one canonical item.

    No `key` field: the item is the path parameter, because it identifies the
    resource rather than describing a change to it. The valid-key check lives
    in the service (against `ITENS`, the one definition) rather than being
    re-listed here — a second copy of the six keys is a second thing to forget
    to update.
    """

    concluido: bool
