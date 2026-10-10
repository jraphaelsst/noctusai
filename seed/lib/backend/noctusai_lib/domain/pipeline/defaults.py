"""Default stages — lazily seeded per org on the first read of a pipeline.

Stages are per-org configuration rows. An org that has never opened a board has
none, and a board with no columns cannot even receive its first card. Seeding
on the first stages/board read (idempotent: the upsert ignores duplicates on
the `(org_id, pipeline, slug)` unique key) means no org-creation trigger in
another product's schema and no race: two concurrent first reads both upsert
and the unique key keeps one row per slug.

"Never configured" includes INACTIVE rows: an org that deactivated or deleted
every stage made a choice, and re-seeding would undo it.

Lifted from igig `garantir_etapas_padrao` once a second consumer (the
social-wiring Esteira) needed it (recurrence rule N=2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from .config import PipelineConfig
from .stages import list_stages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StageDefault:
    """One default stage. `papel` is the semantic role code keys on."""

    slug: str
    label: str
    cor: str
    papel: str | None = None


def ensure_default_stages(
    db: Any,
    cfg: PipelineConfig,
    defaults: Iterable[StageDefault],
    *,
    org_id: str,
) -> bool:
    """Seed `defaults` for `cfg` when the org's pipeline has no rows at all.

    Returns True when it seeded, False when the pipeline was already
    configured (active or not).
    """
    if list_stages(db, cfg, incluir_inativas=True, org_id=org_id):
        return False
    linhas = [
        {
            "org_id": org_id,
            "pipeline": cfg.pipeline,
            "slug": s.slug,
            "label": s.label,
            "cor": s.cor,
            "posicao": posicao,
            "papel": s.papel,
            "ativo": True,
        }
        for posicao, s in enumerate(defaults)
    ]
    db.table(cfg.stages_table).upsert(
        linhas, on_conflict="org_id,pipeline,slug", ignore_duplicates=True
    ).execute()
    logger.info("default stages created org=%s pipeline=%s", org_id, cfg.pipeline)
    return True
