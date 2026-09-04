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

from decimal import Decimal
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


# ─── Roteiros e visitas (migration 082) ─────────────────────────────────

#: Mirrors the DB CHECK in `082` and `roteiros_service.STATUS_VALIDOS`. Three
#: values, not a boolean: "hasn't happened yet" and "didn't happen" are
#: different facts, and merging them would file every future visit under
#: "did not" in the count this feature exists to produce.
_STATUS_VISITA_VALUES = {"pendente", "realizada", "nao_realizada"}


class RoteiroCreateBody(StrictHttpModel):
    #: The códigos, IN VISITING ORDER — the array index becomes `visitas.ordem`.
    #: The order is the payload, so a client that reorders and re-POSTs is
    #: doing the right thing.
    imoveis: list[str] = Field(min_length=1)
    titulo: Optional[str] = None
    #: Optional: with one open atendimento the server resolves it. Sent
    #: explicitly when the person has several, which the server REFUSES to
    #: guess at (409) rather than filing the roteiro against the wrong deal.
    atendimento_id: Optional[UUID] = None


class RoteiroPatchBody(StrictHttpModel):
    titulo: Optional[str] = None


class RoteiroOrdemBody(StrictHttpModel):
    #: The COMPLETE ordered set, not a delta. A partial reorder that silently
    #: succeeded would leave two visitas sharing a position and the route in an
    #: order nobody chose — the service refuses a mismatch with a 400.
    visita_ids: list[UUID] = Field(min_length=1)


class VisitaCreateBody(StrictHttpModel):
    codigo: str = Field(min_length=1)


class VisitaPatchBody(StrictHttpModel):
    status: Optional[str] = None
    observacao: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _STATUS_VISITA_VALUES:
            raise ValueError(
                f"status must be one of {sorted(_STATUS_VISITA_VALUES)}, got {v!r}"
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


# ─── Checklist extras (migration 083) ───────────────────────────────────
#
# The operator-authored half of the card's checklist. The mandatory half is
# code-owned (`documento_checklist_service.ITENS`) and has no create/delete
# surface at all — see `router.py`'s note there for why.


class ChecklistExtraCreateBody(StrictHttpModel):
    label: str = Field(min_length=1)
    #: Decided at creation and immutable afterwards. Flipping a line's `tipo`
    #: would either strand a `valor_texto` nothing reads or strand a document
    #: nothing points at, so the PATCH body below deliberately has no `tipo`
    #: field — a line of the wrong kind is deleted and re-added, which is one
    #: click and leaves no ambiguous row behind.
    tipo: Literal["texto", "arquivo"]


class ChecklistExtraPatchBody(StrictHttpModel):
    """Every field optional; ABSENCE means "leave alone".

    `None` is a real value here — clearing `valor_texto` unticks the line on
    purpose — so the route reads `model_fields_set` rather than
    `exclude_none`, the same way `NegociacaoPatchBody` is read.
    """

    label: Optional[str] = Field(default=None, min_length=1)
    valor_texto: Optional[str] = None
    ordem: Optional[int] = None


# ─── Documentos ─────────────────────────────────────────────────────────
#
# No body model for DELETE — contract correction: the seed `ApiClient
# .delete()` has no body parameter, and a DELETE-with-body is poorly
# supported across the stack generally. `motivo` travels as a required
# query parameter instead (see `router.py`'s `delete_documento_route`).


__all__ = [
    "ChecklistCreateBody",
    "ChecklistExtraCreateBody",
    "ChecklistExtraPatchBody",
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


class ExtracaoSugestaoBody(StrictHttpModel):
    """Which extracted field this confirm/discard decision is about.

    Optional, and omitting it means `data_nascimento`. That default exists
    because the birthdate was the only extracted field when these two routes
    shipped; a client that predates `nome_oficial` keeps working unchanged
    rather than starting to fail on a field it has never heard of.

    The valid keys are NOT re-listed here. They live in
    `identidade_extracao_service.CAMPO_POR_CHAVE`, which is the definition;
    a second copy would be a second thing to forget to update, and the
    service raises a typed 422 for an unknown key either way.
    """

    item_key: Optional[str] = None


class DocumentoChecklistPatchBody(StrictHttpModel):
    """Set or clear the human override on one canonical item.

    No `key` field: the item is the path parameter, because it identifies the
    resource rather than describing a change to it. The valid-key check lives
    in the service (against `ITENS`, the one definition) rather than being
    re-listed here — a second copy of the six keys is a second thing to forget
    to update.

    `concluido` is nullable, and null is not "unset" — it CLEARS the override
    and hands the item back to the derivation (migration 068). It stays
    REQUIRED precisely so clearing must be asked for, never inferred from an
    omitted field.
    """

    concluido: Optional[bool]


# ─── Compradores / partes do atendimento (migration 073) ─────────────────────


class CompradorCreateBody(StrictHttpModel):
    """Add another person to this card's atendimento.

    EITHER `cliente_id` (link someone already in this org — the spouse who is
    herself a lead) OR `nome` (create her). Never both: when the two disagree
    the caller's intent is unknowable, and picking one silently is how a
    contract ends up naming the wrong person. The exclusivity is checked in the
    service, which is also where the 422 is raised, so there is one rule rather
    than a validator here and a check there.

    `papel` is validated against `compradores_service.PAPEIS_POR_LADO[lado]` —
    the definition — rather than re-listed as a Literal here, for the same
    reason the checklist keys are not re-listed in
    `DocumentoChecklistPatchBody`. Omit it and the service applies the side's
    default: `comprador` for the buyer side, `proprietario` for the seller's.

    `lado` selects the side (migration 098) and defaults to `comprador`, so
    every caller written before the Vendedor tab existed keeps its meaning.

    `atendimento_id` is optional and normally omitted: the service resolves the
    person's single open atendimento. It is accepted for the case that
    resolution refuses — someone with two open deals — where only the user can
    say which one this comprador belongs to.
    """

    cliente_id: Optional[UUID] = None
    nome: Optional[str] = Field(default=None, max_length=255)
    celular: Optional[str] = Field(default=None, max_length=32)
    papel: Optional[str] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)
    atendimento_id: Optional[UUID] = None
    lado: Optional[str] = None


# ─── Negociação (migration 077) ──────────────────────────────────────────


class NegociacaoPatchBody(StrictHttpModel):
    """The commercial terms a human may set.

    Every field Optional AND nullable; absence means "leave alone" (the
    service reads `model_fields_set`), because `None` is a real value —
    clearing a valor negociado that was entered by mistake has to be possible.

    Money and percentages are `Decimal`, never `float`: a float cannot
    represent centavos, and the whole commission split is built on them being
    exact.
    """

    imovel_codigo: Optional[str] = Field(default=None, max_length=64)
    valor_negociado: Optional[Decimal] = Field(default=None, ge=0)
    pct_comissao: Optional[Decimal] = Field(default=None, ge=0, le=100)
    tem_parceria: Optional[bool] = None
    pct_parceria: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_agencia: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_agentes: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_captador: Optional[Decimal] = Field(default=None, ge=0, le=100)
    formas_pagamento: Optional[str] = Field(default=None, max_length=2000)
    parcelas: Optional[str] = Field(default=None, max_length=2000)
    financiamento: Optional[bool] = None
    #: 🔴 Not constrained to require `financiamento` — see migration 077. The
    #: UI shows it conditionally; FGTS can legitimately fund a purchase with
    #: no financing at all, so the rule is not frozen into the contract.
    fgts: Optional[bool] = None
    observacoes: Optional[str] = Field(default=None, max_length=4000)


class NegociacaoDefaultsPatchBody(StrictHttpModel):
    """The org's split rule.

    🔴 Changing this does NOT touch existing negociações — their percentages
    were copied at creation. It changes what the NEXT deal starts from.
    """

    pct_comissao: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_parceria: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_agencia: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_agentes: Optional[Decimal] = Field(default=None, ge=0, le=100)
    pct_captador: Optional[Decimal] = Field(default=None, ge=0, le=100)


# ─── Financiamento / Escritura (migration 078) ───────────────────────────


class FinanciamentoPatchBody(StrictHttpModel):
    """The financing decision and its notes.

    `situacao` is three-valued (`pendente`/`aprovado`/`recusado`) rather than a
    boolean: "not yet decided" is where an application spends most of its life
    and is not the same as a refusal.
    """

    situacao: Optional[Literal["pendente", "aprovado", "recusado"]] = None
    situacao_motivo: Optional[str] = Field(default=None, max_length=2000)
    fgts: Optional[bool] = None
    observacoes: Optional[str] = Field(default=None, max_length=4000)
    #: Which registered agent is financing this deal (migration 100). An
    #: explicit null clears the selection — "we have not decided yet" is a
    #: real state and must be reachable after one has been chosen.
    agente_financeiro_id: Optional[UUID] = None
    #: Proposal/contract number at the bank. Free text: every agent formats it
    #: differently and none of them ask us to validate it.
    numero_proposta: Optional[str] = Field(default=None, max_length=120)
