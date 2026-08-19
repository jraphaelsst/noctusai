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

P1.4 COMPLETION — ONE CARD PER PERSON (lead-card-hub roadmap §1/§5)
---------------------------------------------------------------------
A Meta lead fires BOTH `spawn_funil_card_on_lead` and
`spawn_funil_card_on_meta_lead` for the same human, so `atendimentos`
can hold several rows sharing one `cliente_id` (migration `048`). Migration
`054` + `clientes_service._collapse_atendimentos` mark every loser with
`substituida_por` (never deleting a row — D3's reversibility bar). The read
path here is the other half: `obter_funil` excludes `substituida_por IS NOT
NULL` rows and `attach_colapsadas` merges the union of every folded row's
`lead`/`campanha` data onto the survivor, so the ONE card the board now
shows still carries BOTH origin field sets — `leadDetailSections` renders
from `lead`, `campanhaDetailSections` from `campanha`, exactly as before,
whichever origin the data came from. `colapsadas` additionally lists the
folded siblings for a future audit/undo UI; nothing renders from it yet.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.pipeline import PipelineConfig
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.phone import phone_search_digits

PIPELINE_FUNIL = PipelineConfig(
    pipeline="funil",
    card_table="atendimentos",
    value_field="valor_estimado",
    entity_label="negociação",
    entity_kind="atendimento",
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

ATENDIMENTO_SELECT = (
    "*,"
    f"lead:leads!atendimentos_lead_id_fkey({_LEAD_CARD_FIELDS}),"
    f"campanha:meta_ads_leads!atendimentos_meta_ads_lead_id_fkey({_CAMPANHA_CARD_FIELDS}),"
    f"etapa_rel:pipeline_stages!atendimentos_etapa_id_fkey({_STAGE_FIELDS})"
)

# A processo card must open the SAME modal as the funil card it came from, so
# it needs the same origin joins — one hop further out, through the negociação.
# Without them the processo board could only offer a title, and "click the card
# to see the lead" would be true on one board and false on the other.
PROCESSO_SELECT = (
    "*,"
    # `cliente_id` is projected so the Processos board can open the SAME card
    # dialog the Clientes board does — the card is keyed by the person, and
    # without this the processo card could only ever open the old read-only
    # field list.
    "atendimento:atendimentos!processos_venda_atendimento_id_fkey"
    "(id, titulo, valor_estimado, closed_at, lead_id, meta_ads_lead_id, cliente_id,"
    f"lead:leads!atendimentos_lead_id_fkey({_LEAD_CARD_FIELDS}),"
    f"campanha:meta_ads_leads!atendimentos_meta_ads_lead_id_fkey({_CAMPANHA_CARD_FIELDS})),"
    f"etapa_rel:pipeline_stages!processos_venda_etapa_id_fkey({_STAGE_FIELDS})"
)

# Whitelists mirror the frontend types. Anything not listed is stripped, so a
# schema addition cannot silently start leaking through the API.
_ATENDIMENTO_FIELDS = (
    "id", "org_id", "lead_id", "meta_ads_lead_id", "etapa_id", "status",
    "titulo", "valor_estimado", "kanban_pos", "arquivado", "closed_at",
    "created_at", "updated_at", "lead", "campanha", "etapa_rel",
    # P1.4 completion — see the module docstring.
    "cliente_id", "colapsadas",
)
_PROCESSO_FIELDS = (
    "id", "org_id", "atendimento_id", "etapa_id", "valor", "observacoes",
    "kanban_pos", "arquivado", "created_at", "updated_at",
    "atendimento", "etapa_rel",
)
# One entry per negociação folded into a survivor — enough for a future
# audit/undo affordance, never the whole row (`org_id`/`kanban_pos`/etc.
# would be noise once folded).
_COLAPSADA_FIELDS = (
    "id", "lead_id", "meta_ads_lead_id", "titulo", "status", "colapsada_em",
    "lead", "campanha",
)

#: PostgREST `in_` values ride in the URL query string — see
#: `clientes_service.list_review_groups`'s precedent (the same batch
#: keeps a ~200-UUID request line comfortably under the usual 8 KB limit).
_IN_FILTER_BATCH = 200


def atendimento_to_dto(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return row
    return {k: row.get(k) for k in _ATENDIMENTO_FIELDS if k in row}


def processo_to_dto(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return row
    return {k: row.get(k) for k in _PROCESSO_FIELDS if k in row}


def _batched(items: list, size: int):
    """Yield `items` in chunks of `size` — see `_IN_FILTER_BATCH`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _fetch_colapsadas(client: Any, org_id: str, survivor_ids: list[str]) -> dict[str, list[dict]]:
    """Every `atendimentos` row folded into one of `survivor_ids`,
    keyed by `substituida_por`. Batched (an unbounded `in_` overflows the
    request line — see `_IN_FILTER_BATCH`) and paginated via the seed's
    `iter_paged_rows` rather than a hand-rolled `while True: range(...)`
    loop (that loop only terminates if the backend honours `range()` —
    see that helper's module docstring for the two independent hazards
    this fleet has already hit)."""
    if not survivor_ids:
        return {}
    by_survivor: dict[str, list[dict]] = {}
    for batch in _batched(survivor_ids, _IN_FILTER_BATCH):
        def _fetch_page(start: int, end: int, _batch=batch):
            return (
                client.table("atendimentos")
                .select(ATENDIMENTO_SELECT)
                .eq("org_id", org_id)
                .in_("substituida_por", _batch)
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        for row in iter_paged_rows(
            _fetch_page, label=f"atendimentos colapsadas para org_id={org_id}",
        ):
            by_survivor.setdefault(row["substituida_por"], []).append(row)
    return by_survivor


def _merge_origem(survivor: dict, colapsadas: list[dict]) -> None:
    """Union the origin field sets across a collapsed group onto the
    survivor. A collapse folds cards, not data — BOTH `leadDetailSections`
    and `campanhaDetailSections` must still be reachable from the ONE card
    the board now shows, so a survivor missing one origin adopts it from
    the first sibling that carries it. Never overwrites data the survivor
    already has of its own."""
    if not survivor.get("lead"):
        for c in colapsadas:
            if c.get("lead"):
                survivor["lead"] = c["lead"]
                break
    if not survivor.get("campanha"):
        for c in colapsadas:
            if c.get("campanha"):
                survivor["campanha"] = c["campanha"]
                break
    survivor["colapsadas"] = [
        {k: c.get(k) for k in _COLAPSADA_FIELDS} for c in colapsadas
    ]


def attach_colapsadas(client: Any, org_id: str, rows: list[dict]) -> list[dict]:
    """Enrich each surviving `atendimentos` row with the union of
    every origin folded into it by migration `054` / `_collapse_
    atendimentos` — see the module docstring's "P1.4 completion" section.
    Mutates and returns `rows`; every row gets a `colapsadas` key (empty
    list when nothing was folded into it), so `atendimento_to_dto`'s
    whitelist lookup (`if k in row`) always finds it.
    """
    by_survivor = _fetch_colapsadas(client, org_id, [r["id"] for r in rows])
    for row in rows:
        colapsadas = by_survivor.get(row["id"], [])
        if colapsadas:
            _merge_origem(row, colapsadas)
        else:
            row.setdefault("colapsadas", [])
    return rows


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


def search_atendimentos(rows: list[dict], query: str) -> list[dict]:
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
        neg = row.get("atendimento") or {}
        haystack = (neg.get("titulo"), row.get("observacoes")) + _origin_haystack(neg)
        if any(q in str(v or "").lower() for v in haystack):
            return True
        return _matches_phone(neg, q)

    return [r for r in rows if matches(r)]
