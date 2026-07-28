"""
The ERP's two kanban pipelines, declared as config.

This module is the entire product-side difference between the Funil de Vendas
board and the Processos de Venda board. Everything else — listing stages,
creating/renaming/reordering/deleting them, grouping cards into columns, moving
a card and recording the transition — is `noctusai_lib.domain.pipeline`.

Before this, each board owned a private copy of that machinery, and the copies
had drifted: the Funil wrote stage transitions to a history table and Processos
wrote none, so the newer board had no audit trail. Two config literals cannot
drift the way two forked handlers do.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.domain.pipeline import PipelineConfig

from app.services.negociacoes_venda_service import ETAPAS_FUNIL
from app.services.processos_venda_service import ETAPAS_PROCESSO

PIPELINE_FUNIL = PipelineConfig(
    pipeline="funil",
    card_table="negociacoes_venda",
    value_field="valor_estimado",
    entity_label="negociação",
    entity_kind="negociacao_venda",
)

PIPELINE_PROCESSOS = PipelineConfig(
    pipeline="processos_venda",
    card_table="processos_venda",
    value_field="valor",
    entity_label="processo",
    entity_kind="processo_venda",
)

# The legacy enum columns (`negociacoes_venda.etapa`, `processos_venda.etapa`)
# are RETAINED but no longer authoritative — migration 042 dropped their NOT
# NULL because a user-created stage has no enum value to write.
#
# They are still written opportunistically, whenever the destination stage's
# slug happens to be a legal enum label, for exactly one reason: they are the
# rollback landing zone. If 042 has to be reversed, a board whose enum column
# kept tracking reality reverts to working code; one that stopped writing it
# reverts to a board full of stale stages. Removal is the sibling of roadmap Q8
# and follows the same trigger — one stable release on the `etapa_id` read path.
_LEGACY_ENUM_VALUES = {
    "funil": set(ETAPAS_FUNIL),
    "processos_venda": set(ETAPAS_PROCESSO),
}


def legacy_etapa_update(cfg: PipelineConfig, stage: dict) -> dict:
    """`{"etapa": <slug>}` when the slug is a legal enum label, else `{}`.

    Returning an empty dict rather than writing NULL is deliberate: a
    user-created stage leaves the legacy column holding its previous value,
    which is stale but *parseable*, instead of NULL, which the pre-042 code
    path would reject outright.
    """
    slug = stage.get("slug")
    if slug and slug in _LEGACY_ENUM_VALUES.get(cfg.pipeline, ()):
        return {"etapa": slug}
    return {}


def resolve_stage_org(get_org_id, user) -> Optional[str]:
    """Adapter matching the seed router factory's `resolve_org_id(db, user)`.

    The seed passes `db` because a consumer might need it; the ERP resolves the
    org from `public.noctus_users` — the same row RLS's `current_org_id()`
    reads — so the client is unused here. Kept in the signature rather than
    special-cased in the seed, because "some consumers need the db" is the
    general case.
    """
    return get_org_id(user)
