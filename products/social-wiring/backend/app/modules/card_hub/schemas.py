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

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

# The card's generic bodies are the seed's (`noctusai_lib.domain.card_hub`,
# lifted from this file — wave A, 2026-09-22). Re-exported so this module stays
# the one place the card_hub routes' bodies are importable from. The two
# config-shaped ones (`ClienteTagsSetBody`, `MembrosSetBody` — their schema
# name / field name come from `CARD_HUB`) are built by the seed router factory.
from noctusai_lib.domain.card_hub.schemas import (  # noqa: F401 — re-export
    ChecklistCreateBody,
    ChecklistExtraCreateBody,
    ChecklistExtraPatchBody,
    ChecklistItemCreateBody,
    ChecklistItemUpdateBody,
    ChecklistUpdateBody,
    NotaCreateBody,
    NotaUpdateBody,
    TagCreateBody,
    TagUpdateBody,
)


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


class VisitaPropostaBody(StrictHttpModel):
    """The proposta axis (migration 104) — deliberately its own body.

    Not folded into `VisitaPatchBody` for the same reason 104 does not fold
    these into `status`: "did the visit happen" and "did it produce an offer
    that was accepted" are orthogonal facts, and one body carrying both invites
    a client that sends `status` and `aceita` together and cannot say which of
    the two it meant to change.

    Both fields are tri-state via `exclude_unset`: absent = leave alone,
    `true` = record, `false` = undo. `false` is a real operation here, not a
    default — undoing an acceptance is what the service unwinds the deal's
    `imovel_codigo` for.
    """

    proposta: Optional[bool] = None
    aceita: Optional[bool] = None


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
    "DatasPatchBody",
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


class DecidirConflitoBody(StrictHttpModel):
    """An admin's decision on a `cliente_campo_conflitos` row (migration
    138). `aceitar=True` overwrites `clientes.<campo>` with the extracted
    value (the prior value stays on the conflict row, permanently);
    `aceitar=False` leaves `clientes` untouched — the value already there
    keeps prevailing."""

    aceitar: bool


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


class PartePapelPatchBody(StrictHttpModel):
    """Correct what a party IS to their side.

    🔴 `lado` IS DELIBERATELY NOT ACCEPTED. The validation this drives is
    `PAPEIS_POR_LADO[lado]`, so a caller able to name the side would be naming
    its own vocabulary — a vendedor could be made a `fiador` by claiming the
    buyer side. The stored row already knows which side it is on, and that is
    what the service reads.

    `papel` is REQUIRED rather than Optional-means-leave-alone (the convention
    `NegociacaoPatchBody` follows). That convention exists to let one form save
    many fields without asserting the ones it did not touch; this endpoint has
    exactly one field and is driven by picking a value from a list, so an
    omitted `papel` is a request that means nothing.

    Not validated as a `Literal` here for the same reason `CompradorCreateBody`
    is not: the per-side vocabulary lives in `compradores_service`, next to the
    dropdown that offers it, and a second copy is a second thing to forget.
    """

    papel: str = Field(min_length=1, max_length=64)


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
    #: Possession terms (migration 108). `posse_data` is a date STRING
    #: ("YYYY-MM-DD"), matching every other date field on this module's
    #: bodies (`DatasPatchBody`, `AgendamentoCreateBody`'s `quando`) — never a
    #: Pydantic `date`, so PostgREST's own string round-trip is the only
    #: coercion in play.
    posse_data: Optional[str] = Field(default=None, max_length=10)
    posse_condicoes: Optional[str] = Field(default=None, max_length=2000)
    #: Which permuta_ativos (101) row is the swap component of this deal, if
    #: any. An explicit null clears it — see `imovel_codigo`'s identical
    #: contract just above.
    permuta_ativo_id: Optional[UUID] = None


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


# ─── Contratos (migration 106) ────────────────────────────────────────────


class ContratoPatchBody(StrictHttpModel):
    """Title, model and status — a contract's editable metadata.

    A `status` change alone (no `titulo`/`modelo`) is the common case, but
    all three are independently optional: `model_fields_set` is what the
    service reads, so this mirrors `FinanciamentoPatchBody`'s "absence means
    leave alone" contract. Any status-to-any-status transition is allowed —
    operators fix mistakes.
    """

    titulo: Optional[str] = Field(default=None, min_length=1, max_length=200)
    modelo: Optional[
        Literal[
            "compra_venda",
            "compra_venda_permuta",
            "compra_venda_a_vista",
            "outro",
        ]
    ] = None
    status: Optional[
        Literal[
            "rascunho",
            "em_revisao",
            "enviado_assinatura",
            "assinado",
            "cancelado",
        ]
    ] = None
    #: Migration 114. ISO date (AAAA-MM-DD); null clears it. Parsed by the
    #: service so a malformed date is a named 400, not a 422.
    assinatura_data: Optional[str] = Field(default=None, max_length=32)
    #: Migration 157 — the signing GATE. 'fisica' while an e-signature
    #: envelope is live is the service's typed 409
    #: `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO`.
    modalidade_assinatura: Optional[Literal["digital", "fisica"]] = None
    #: Migration 114. Per-contract override of the office deadline to resolve
    #: pendências; null = the office default (10). > 0 when set — a service
    #: 400, not a 422.
    prazo_pendencias_dias: Optional[int] = None


class ProcessoLegadoBody(StrictHttpModel):
    """Migration 151 — admin-only "processo anterior à plataforma" flag
    (owner directive 2026-09-22). `ativo=True` dispenses the contract
    gate's certidão TIME rules (emission age / validade) for THIS
    contract only; `ativo=False` restores them. `motivo` is the admin's
    own account of why — required (3..500 chars) only when turning the
    flag ON; omitted/ignored when turning it off, since there is nothing
    left to explain once the dispensation is lifted."""

    ativo: bool
    motivo: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _motivo_required_when_ativo(self) -> "ProcessoLegadoBody":
        if self.ativo:
            texto = (self.motivo or "").strip()
            if len(texto) < 3:
                raise ValueError(
                    "motivo é obrigatório (3 a 500 caracteres) ao marcar o "
                    "processo como anterior à plataforma"
                )
        return self


# ─── Negociação estruturada (migration 108) ──────────────────────────────


class ParcelaCreateBody(StrictHttpModel):
    """One structured installment. `favorecido_id` is validated in the
    service against THIS atendimento — see migration 108's header for why
    that is not a DB-level composite FK."""

    tipo: Literal[
        "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta",
        "permuta",
    ]
    valor: Decimal = Field(ge=0)
    vencimento: Optional[str] = Field(default=None, max_length=10)
    evento: Optional[str] = Field(default=None, max_length=200)
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)
    favorecido_id: Optional[UUID] = None
    confissao_divida: bool = False
    #: Payment of this parcela triggers the brokerage payment (114).
    dispara_corretagem: bool = False
    #: `tipo='permuta'` only — the `permuta_ativos` (natureza permuta_imovel)
    #: this parcela is paid with. One swap can hand over several matrículas.
    permuta_ativo_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ParcelaPatchBody(StrictHttpModel):
    """Every field optional; absence means "leave alone" — same
    `model_fields_set` contract `NegociacaoPatchBody` uses.
    `permuta_ativo_ids`, when sent, REPLACES the parcela's linked set."""

    tipo: Optional[
        Literal[
            "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta",
            "permuta",
        ]
    ] = None
    valor: Optional[Decimal] = Field(default=None, ge=0)
    vencimento: Optional[str] = Field(default=None, max_length=10)
    evento: Optional[str] = Field(default=None, max_length=200)
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)
    favorecido_id: Optional[UUID] = None
    confissao_divida: Optional[bool] = None
    dispara_corretagem: Optional[bool] = None
    permuta_ativo_ids: Optional[list[UUID]] = Field(default=None, max_length=20)
    ordem: Optional[int] = None


class ParcelasDividirBody(StrictHttpModel):
    """Auto-suggest an even split of the current `saldo_nao_alocado` across
    `num_parcelas` — a starting point the operator edits afterward, never a
    save that blocks on completeness (see migration 108's header and
    `noctusai_lib.domain.real_estate.parcelamento`)."""

    num_parcelas: int = Field(ge=1, le=360)
    tipo: Literal[
        "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta"
    ] = "direta"
    forma_pagamento: Optional[str] = Field(default=None, max_length=50)
    favorecido_id: Optional[UUID] = None
    #: First due date; each subsequent parcela lands one month later. `None`
    #: leaves every generated parcela's `vencimento` unset — the split is
    #: about the AMOUNTS, a due-date schedule is a separate decision.
    vencimento_inicial: Optional[str] = Field(default=None, max_length=10)


class FavorecidoCreateBody(StrictHttpModel):
    """Financial PII (migration 108) — RLS org-scoped, never logged."""

    nome: str = Field(min_length=1, max_length=255)
    cpf_cnpj: Optional[str] = Field(default=None, max_length=32)
    banco: Optional[str] = Field(default=None, max_length=120)
    agencia: Optional[str] = Field(default=None, max_length=32)
    conta: Optional[str] = Field(default=None, max_length=32)
    pix: Optional[str] = Field(default=None, max_length=140)


class FavorecidoPatchBody(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    cpf_cnpj: Optional[str] = Field(default=None, max_length=32)
    banco: Optional[str] = Field(default=None, max_length=120)
    agencia: Optional[str] = Field(default=None, max_length=32)
    conta: Optional[str] = Field(default=None, max_length=32)
    pix: Optional[str] = Field(default=None, max_length=140)


class _IntermediarioQualificacao(StrictHttpModel):
    """PF/PJ qualification of an intermediário (migration 114) — personal
    data, RLS org-scoped, never logged. Lengths here are only abuse caps: the
    real rules (CPF/CNPJ check digits, pf↔CPF / pj↔CNPJ, e-mail, UF, CEP) are
    the service's named 400s, so a caller gets a pt-BR message instead of a
    422. `documento`'s `pessoa_tipo` is inferred when omitted."""

    #: Which of THIS deal's favorecidos receives the commission.
    favorecido_id: Optional[UUID] = None
    pessoa_tipo: Optional[Literal["pf", "pj"]] = None
    documento: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=254)
    endereco_cep: Optional[str] = Field(default=None, max_length=16)
    endereco_logradouro: Optional[str] = Field(default=None, max_length=255)
    endereco_numero: Optional[str] = Field(default=None, max_length=32)
    endereco_complemento: Optional[str] = Field(default=None, max_length=120)
    endereco_bairro: Optional[str] = Field(default=None, max_length=120)
    endereco_cidade: Optional[str] = Field(default=None, max_length=120)
    endereco_uf: Optional[str] = Field(default=None, max_length=8)
    representante_nome: Optional[str] = Field(default=None, max_length=255)
    representante_cpf: Optional[str] = Field(default=None, max_length=32)


class IntermediarioCreateBody(_IntermediarioQualificacao):
    """`nome`/`creci` are always accepted directly — `corretor_id` is an
    optional pointer into `lead_corretores` when the intermediary happens to
    be in-house (migration 108's header)."""

    corretor_id: Optional[UUID] = None
    nome: str = Field(min_length=1, max_length=255)
    creci: Optional[str] = Field(default=None, max_length=64)
    tipo: Literal["percentual", "valor_fixo"] = "percentual"
    valor: Optional[Decimal] = Field(default=None, ge=0)


class IntermediarioPatchBody(_IntermediarioQualificacao):
    corretor_id: Optional[UUID] = None
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    creci: Optional[str] = Field(default=None, max_length=64)
    tipo: Optional[Literal["percentual", "valor_fixo"]] = None
    valor: Optional[Decimal] = Field(default=None, ge=0)


# ─── Termos do negócio (migration 114) ────────────────────────────────────

PosseMarco = Literal["assinatura", "parcela", "protocolo_registro"]


class TermosNegocioPutBody(StrictHttpModel):
    """The deal's contract clauses, replaced as a WHOLE (PUT) — an absent key
    is stored as null. Every field nullable: clauses are drafted over several
    sittings. Ranges (prazos ≥ 0, corretagem_num_parcelas ≥ 1, juros 0–100%
    a.m.) and the `*_marco = 'parcela'` ⇔ `*_marco_parcela_id` rule are the
    service's named 400s, not 422s."""

    posse_prazo_dias: Optional[int] = None
    posse_marco: Optional[PosseMarco] = None
    posse_marco_parcela_id: Optional[UUID] = None

    permuta_posse_prazo_dias: Optional[int] = None
    permuta_posse_marco: Optional[PosseMarco] = None
    permuta_posse_marco_parcela_id: Optional[UUID] = None
    permuta_obrigacoes_entrega: Optional[str] = Field(default=None, max_length=4000)

    itens_integrantes: Optional[str] = Field(default=None, max_length=4000)
    #: [Migration 163] `True` = a human confirmed this deal genuinely has no
    #: itens integrantes — the only way an unset `itens_integrantes` stops
    #: blocking generation (see that migration's header).
    itens_integrantes_ausente_confirmado: Optional[bool] = None
    ad_corpus: Optional[bool] = None
    obrigacoes_vendedor: Optional[str] = Field(default=None, max_length=4000)

    onus_quitacao: Optional[
        Literal["compradores_prazo", "interveniente_quitante", "parcela", "ja_quitado"]
    ] = None
    onus_prazo_dias: Optional[int] = None

    #: % ao mês.
    confissao_juros_am: Optional[Decimal] = None
    confissao_garantia: Optional[str] = Field(default=None, max_length=4000)

    corretagem_contratantes: Optional[
        Literal["vendedores", "compradores", "partes"]
    ] = None
    corretagem_num_parcelas: Optional[int] = None
