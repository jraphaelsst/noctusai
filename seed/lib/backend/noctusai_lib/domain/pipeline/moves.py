"""
Moving a card between stages — one implementation, every pipeline.

This module is the fix for a concrete defect. The ERP shipped two boards whose
`mover-etapa` handlers were copies of each other, and the copies had already
diverged: the Funil recorded every stage transition to a history table, and
Processos de Venda recorded nothing. Nobody decided that; it is simply what
happens to a forked handler. Because the history write now lives inside the
one function both boards call, a pipeline cannot be added without an audit
trail.

The history row is also what makes cycle-time answerable ("how long did this
sit in Assinatura?"), which no amount of reading the current `etapa_id` can
reconstruct after the fact.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from .config import PipelineConfig
from .stages import get_stage


def move_card(
    db,
    cfg: PipelineConfig,
    *,
    card_id: str,
    to_stage_id: str,
    user_id: str,
    novo_indice: int | None = None,
    nova_posicao: Decimal | None = None,
    motivo: str | None = None,
    log_action: Callable[..., Any] | None = None,
    extra_updates: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> dict:
    """Move one card to `to_stage_id`, recording the transition.

    Args:
        db: Supabase client already scoped to the caller (RLS enforces tenancy).
        cfg: The pipeline being operated on.
        card_id: Card to move.
        to_stage_id: Destination stage id — an id, never a name, so a renamed
            stage keeps working.
        user_id: Who moved it; recorded as the responsible party.
        novo_indice: Optional new `kanban_pos` written verbatim — the legacy
            integer-index form, for consumers whose column is `integer`.
        nova_posicao: Optional FRACTIONAL position from `ordering`, for
            consumers on a `numeric` column. Wins over `novo_indice`. Sent as
            a string so the driver cannot round a Decimal through float.
        motivo: Optional free-text reason, surfaced in history.
        log_action: Optional product audit-log hook.
        extra_updates: Additional columns the consumer wants written in the
            same update (e.g. keeping a legacy enum column in sync).
        org_id: Required by consumers whose client does not enforce tenancy
            (see `list_stages`). Also stamped onto the history row when the
            history table is org-scoped.

    Returns:
        The updated card row.
    """
    stage = get_stage(db, cfg, to_stage_id, org_id=org_id)

    select_cols = ["id", "etapa_id", "kanban_pos"]
    if cfg.cliente_field:
        select_cols.append(cfg.cliente_field)
    card_query = db.table(cfg.card_table).select(", ".join(select_cols)).eq("id", card_id)
    if org_id:
        card_query = card_query.eq("org_id", org_id)
    current_rows = card_query.execute().data or []
    if not current_rows:
        raise NotFoundError(cfg.entity_label.capitalize(), card_id)
    current = current_rows[0]

    de_etapa_id = current.get("etapa_id")

    updates: dict[str, Any] = {"etapa_id": to_stage_id}
    # `nova_posicao` wins when both are given: it is an already-computed
    # FRACTIONAL position (see `ordering`), while `novo_indice` is the older
    # "write the index straight into the column" form still used by consumers
    # whose `kanban_pos` is an integer column. Silently preferring one without
    # saying so is how a caller ends up debugging why its position is ignored.
    if nova_posicao is not None:
        updates["kanban_pos"] = str(nova_posicao)
    elif novo_indice is not None:
        updates["kanban_pos"] = novo_indice
    if extra_updates:
        updates.update(extra_updates)

    rows = db.table(cfg.card_table).update(updates).eq("id", card_id).execute().data or []
    if not rows:
        raise NotFoundError(cfg.entity_label.capitalize(), card_id)
    row = rows[0]

    # Only a real stage CHANGE is history. A within-column reorder carries the
    # same stage and would otherwise flood the trail with non-events, making
    # the genuine transitions unreadable.
    if de_etapa_id != to_stage_id:
        history = {
            "pipeline": cfg.pipeline,
            "entidade_id": card_id,
            "de_etapa_id": de_etapa_id,
            "para_etapa_id": to_stage_id,
            "responsavel_id": user_id,
            "motivo": motivo,
        }
        if cfg.cliente_field:
            history["cliente_id"] = current.get(cfg.cliente_field)
        if org_id:
            history["org_id"] = org_id
        db.table(cfg.history_table).insert(history).execute()

        if log_action:
            # `cfg.entity_kind`, not a hardcoded "cliente". Both ERP routers
            # previously logged "cliente" while passing a negociação/processo
            # id, so audit queries filtered by entity type mis-joined silently.
            log_action(
                user_id,
                "mover",
                cfg.entity_kind,
                card_id,
                f"Moveu {cfg.entity_label} para a etapa {stage['label']}",
                {
                    "de_etapa_id": de_etapa_id,
                    "para_etapa_id": to_stage_id,
                    "para_etapa": stage.get("slug"),
                    "motivo": motivo,
                },
            )

    return row


def resolve_initial_stage(db, cfg: PipelineConfig, *, org_id: str | None = None) -> dict:
    """The stage a card enters the board at — the first in configured order.

    Derived from `posicao` rather than a hardcoded slug, because "the first
    stage" is exactly the thing the user can now reorder.
    """
    from .stages import list_stages

    stages = list_stages(db, cfg, org_id=org_id)
    if not stages:
        raise ValidationError_(
            f"O funil '{cfg.pipeline}' não tem nenhuma etapa configurada. "
            "Configure as etapas antes de usar o quadro."
        )
    return stages[0]
