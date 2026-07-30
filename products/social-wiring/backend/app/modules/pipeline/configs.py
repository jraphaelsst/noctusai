"""
social-wiring's two kanban pipelines, declared as config.

This file plus `deps.py` is the ENTIRE product-side surface of the Funil de
Vendas and Processos de Venda boards. Listing stages, creating/renaming/
reordering/deleting them, grouping cards into columns, moving a card and
recording the transition all come from `noctusai_lib.domain.pipeline`, shared
with erp-imobiliario.

The card here is a NEGOCIAÇÃO spawned from a lead — see migration 034. Unlike
erp, whose cards hang off `clientes`, a card here points at either a
`social_wiring.leads` row or a `social_wiring.meta_ads_leads` row, so the DTO
carries both nested joins and the UI renders whichever is present.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.pipeline import PipelineConfig
from noctusai_lib.primitives.phone import phone_search_digits

PIPELINE_FUNIL = PipelineConfig(
    pipeline="funil",
    card_table="negociacoes_venda",
    value_field="valor_estimado",
    entity_label="negociação",
    entity_kind="negociacao_venda",
    # No `clientes` table in this schema — the card's origin is a lead, and the
    # history row does not denormalise one. Explicitly None rather than left at
    # the default, which would make the primitive look for a column that does
    # not exist here.
    cliente_field=None,
)

PIPELINE_PROCESSOS = PipelineConfig(
    pipeline="processos_venda",
    card_table="processos_venda",
    value_field="valor",
    entity_label="processo",
    entity_kind="processo_venda",
    cliente_field=None,
)

# The projections a card needs to (a) render itself and (b) open the shared
# detail modal.
#
# A LEAD-origin card carries only the columns the CARD FACE shows; clicking it
# opens `EntityDetailDialog`, which fetches the whole lead via `GET
# /api/leads/{id}` — the exact same record the Leads table hands its own rows,
# which is what makes the two surfaces show identical data by construction
# rather than by two projections that have to be kept in step.
#
# A CAMPAIGN-origin card has no such endpoint: there IS no `leads` row for it,
# so the modal renders straight from this projection. That is why `campanha` is
# projected WIDER than `lead` here — it is the whole record, not a preview.
_LEAD_CARD_FIELDS = (
    "id, cliente_nome, contato, contato_tipo, empreendimento, regiao, "
    "data_entrada, origem_raw"
)
_CAMPANHA_CARD_FIELDS = (
    "id, full_name, email, phone, campaign_id, campaign_name, form_id, "
    "form_name, ad_id, adset_id, platform, is_organic, created_time, answers"
)
_STAGE_FIELDS = "id, slug, label, cor, papel, posicao"

NEGOCIACAO_SELECT = (
    "*,"
    f"lead:leads!negociacoes_venda_lead_id_fkey({_LEAD_CARD_FIELDS}),"
    f"campanha:meta_ads_leads!negociacoes_venda_meta_ads_lead_id_fkey({_CAMPANHA_CARD_FIELDS}),"
    f"etapa_rel:pipeline_stages!negociacoes_venda_etapa_id_fkey({_STAGE_FIELDS})"
)

# A processo card must open the SAME modal as the funil card it came from, so
# it needs the same origin joins — one hop further out, through the negociação.
# Without them the processo board could only offer a title, and "click the card
# to see the lead" would be true on one board and false on the other.
PROCESSO_SELECT = (
    "*,"
    "negociacao:negociacoes_venda!processos_venda_negociacao_venda_id_fkey"
    "(id, titulo, valor_estimado, closed_at, lead_id, meta_ads_lead_id,"
    f"lead:leads!negociacoes_venda_lead_id_fkey({_LEAD_CARD_FIELDS}),"
    f"campanha:meta_ads_leads!negociacoes_venda_meta_ads_lead_id_fkey({_CAMPANHA_CARD_FIELDS})),"
    f"etapa_rel:pipeline_stages!processos_venda_etapa_id_fkey({_STAGE_FIELDS})"
)

# Whitelists mirror the frontend types. Anything not listed is stripped, so a
# schema addition cannot silently start leaking through the API.
_NEGOCIACAO_FIELDS = (
    "id", "org_id", "lead_id", "meta_ads_lead_id", "etapa_id", "status",
    "titulo", "valor_estimado", "kanban_pos", "arquivado", "closed_at",
    "created_at", "updated_at", "lead", "campanha", "etapa_rel",
)
_PROCESSO_FIELDS = (
    "id", "org_id", "negociacao_venda_id", "etapa_id", "valor", "observacoes",
    "kanban_pos", "arquivado", "created_at", "updated_at",
    "negociacao", "etapa_rel",
)


def negociacao_to_dto(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return row
    return {k: row.get(k) for k in _NEGOCIACAO_FIELDS if k in row}


def processo_to_dto(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return row
    return {k: row.get(k) for k in _PROCESSO_FIELDS if k in row}


#: Below this, a digit run is too short to be a phone fragment; matching on it
#: would surface unrelated cards.
_MIN_PHONE_FRAGMENT_DIGITS = 4


def _origin_haystack(row: dict) -> tuple:
    """The searchable identity of a card, whichever origin it has."""
    lead = row.get("lead") or {}
    campanha = row.get("campanha") or {}
    return (
        lead.get("cliente_nome"), lead.get("contato"), lead.get("empreendimento"),
        campanha.get("full_name"), campanha.get("email"), campanha.get("phone"),
        campanha.get("campaign_name"),
    )


def _origin_phones(row: dict) -> tuple:
    lead = row.get("lead") or {}
    campanha = row.get("campanha") or {}
    return (lead.get("contato"), campanha.get("phone"))


def _matches_phone(row: dict, needle: str) -> bool:
    """Compare CANONICAL digit runs, so the number the card DISPLAYS finds the
    card.

    The card renders `lead.contato` through the platform phone seam
    (`+5511981912534`) while the row stores what arrived (`11 98191.2534`).
    Without this, copying the number off a card and pasting it into the board's
    own search box returned nothing. Strictly additive to the substring pass.
    """
    needle_digits = phone_search_digits(needle)
    if not needle_digits or len(needle_digits) < _MIN_PHONE_FRAGMENT_DIGITS:
        return False
    for value in _origin_phones(row):
        if not isinstance(value, str) or "@" in value:
            continue
        stored = phone_search_digits(value)
        if stored and needle_digits in stored:
            return True
    return False


def search_negociacoes(rows: list[dict], query: str) -> list[dict]:
    """Free-text filter across whichever origin the card has."""
    q = query.lower()

    def matches(row: dict) -> bool:
        haystack = (row.get("titulo"),) + _origin_haystack(row)
        if any(q in str(v or "").lower() for v in haystack):
            return True
        return _matches_phone(row, q)

    return [r for r in rows if matches(r)]


def search_processos(rows: list[dict], query: str) -> list[dict]:
    """Same identity fields as the funil, reached through the negociação.

    Before the origin joins existed on `PROCESSO_SELECT` this could only match
    `titulo` + `observacoes`, so searching a client's name on the Processos
    board returned nothing while the identical search on the Funil worked —
    the same query giving different answers on two boards showing the same
    deals.
    """
    q = query.lower()

    def matches(row: dict) -> bool:
        neg = row.get("negociacao") or {}
        haystack = (neg.get("titulo"), row.get("observacoes")) + _origin_haystack(neg)
        if any(q in str(v or "").lower() for v in haystack):
            return True
        return _matches_phone(neg, q)

    return [r for r in rows if matches(r)]
