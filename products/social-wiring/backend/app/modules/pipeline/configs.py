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

# Nested joins. Both origins are projected so the board can render a card
# without a second round trip, and so the UI can deep-link back to the Leads
# page for whichever origin the card actually has.
NEGOCIACAO_SELECT = (
    "*,"
    "lead:leads!negociacoes_venda_lead_id_fkey"
    "(id, cliente_nome, contato, contato_tipo, empreendimento, regiao, data_entrada, origem_raw),"
    "campanha:meta_ads_leads!negociacoes_venda_meta_ads_lead_id_fkey"
    "(id, full_name, email, phone, campaign_id, form_id, created_time),"
    "etapa_rel:pipeline_stages!negociacoes_venda_etapa_id_fkey"
    "(id, slug, label, cor, papel, posicao)"
)

PROCESSO_SELECT = (
    "*,"
    "negociacao:negociacoes_venda!processos_venda_negociacao_venda_id_fkey"
    "(id, titulo, valor_estimado, closed_at, lead_id, meta_ads_lead_id),"
    "etapa_rel:pipeline_stages!processos_venda_etapa_id_fkey"
    "(id, slug, label, cor, papel, posicao)"
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


def search_negociacoes(rows: list[dict], query: str) -> list[dict]:
    """Free-text filter across whichever origin the card has."""
    q = query.lower()

    def matches(row: dict) -> bool:
        lead = row.get("lead") or {}
        campanha = row.get("campanha") or {}
        haystack = (
            row.get("titulo"),
            lead.get("cliente_nome"), lead.get("contato"), lead.get("empreendimento"),
            campanha.get("full_name"), campanha.get("email"), campanha.get("phone"),
        )
        return any(q in str(v or "").lower() for v in haystack)

    return [r for r in rows if matches(r)]


def search_processos(rows: list[dict], query: str) -> list[dict]:
    q = query.lower()

    def matches(row: dict) -> bool:
        neg = row.get("negociacao") or {}
        return any(q in str(v or "").lower() for v in (neg.get("titulo"), row.get("observacoes")))

    return [r for r in rows if matches(r)]
