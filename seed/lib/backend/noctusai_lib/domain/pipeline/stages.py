"""
Stage definitions — the CRUD behind user-editable pipelines.

Pure-ish service layer: takes an already-scoped supabase client (RLS does the
tenant isolation), returns plain dicts, raises `AppException` subclasses so the
existing handlers render them. No FastAPI imports — `domain/` must not depend
on `api/`.

WHY THE GUARDS LIVE HERE AND NOT IN THE DATABASE
------------------------------------------------
Two rules cannot be expressed as constraints without losing the ability to
explain themselves:

  * "you may not delete a stage that still holds cards" — a foreign key can
    only ON DELETE RESTRICT (an opaque 23503) or CASCADE (silently deleting
    the user's deals). Neither is acceptable, and neither can offer to move
    the cards somewhere first.
  * "you may not delete a stage that carries a role" — the role is what the
    accept-proposal seam resolves against, so deleting it breaks a feature in
    a different part of the app. A CHECK cannot see that.

Both therefore live in code, and both return a message that says what to do.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from noctusai_lib.primitives.exceptions import (
    AppException,
    NotFoundError,
    ValidationError_,
)

from .config import PipelineConfig

# Mirrors the `cor` CHECK constraint in erp migration 042. Duplicated
# deliberately and kept small: the API should reject a bad token with a usable
# 400 rather than surfacing a raw 23514 from the database.
STAGE_COLORS: tuple[str, ...] = (
    "primary",
    "secondary",
    "success",
    "warning",
    "destructive",
    "muted",
)

# Semantic roles the CODE keys on. See migration 042's header.
STAGE_ROLE_ACCEPT = "proposta_aceite"
STAGE_ROLE_FINAL = "final"
STAGE_ROLES: tuple[str, ...] = (STAGE_ROLE_ACCEPT, STAGE_ROLE_FINAL)

# Fields a caller may set. `org_id`/`pipeline` are assigned by the server, and
# `slug` is immutable after creation — it is the stable machine key that makes
# renaming safe, so letting it be edited would reintroduce exactly the breakage
# the slug/label split exists to prevent.
_CREATABLE = ("slug", "label", "cor", "posicao", "papel", "ativo")
_UPDATABLE = ("label", "cor", "posicao", "papel", "ativo")


def slugify(label: str) -> str:
    """Derive a stable machine key from a human label.

    Accent-folding matters here: "Qualificação" must yield `qualificacao`, not
    `qualifica_o`, because the seeded defaults use the unaccented forms and a
    consumer re-creating a deleted stage should land on the same slug.
    """
    folded = unicodedata.normalize("NFKD", label or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "etapa"


def _validate(payload: dict[str, Any], *, partial: bool) -> None:
    if not partial or "label" in payload:
        label = (payload.get("label") or "").strip()
        if not label:
            raise ValidationError_("O nome da etapa não pode ficar vazio.", field="label")
        if len(label) > 60:
            raise ValidationError_(
                "O nome da etapa deve ter no máximo 60 caracteres.", field="label"
            )

    cor = payload.get("cor")
    if cor is not None and cor not in STAGE_COLORS:
        raise ValidationError_(
            f"Cor inválida. Use uma de: {', '.join(STAGE_COLORS)}.", field="cor"
        )

    papel = payload.get("papel")
    if papel is not None and papel not in STAGE_ROLES:
        raise ValidationError_(
            f"Papel inválido. Use um de: {', '.join(STAGE_ROLES)}.", field="papel"
        )


def list_stages(
    db,
    cfg: PipelineConfig,
    *,
    incluir_inativas: bool = False,
    org_id: str | None = None,
) -> list[dict]:
    """Ordered stages for this pipeline.

    `org_id` is OPTIONAL and must be passed by any consumer whose client does
    not enforce tenancy itself. The ERP hands in an RLS-scoped user client, so
    the database filters for it; social-wiring uses a schema-scoped ADMIN
    client (RLS as defense-in-depth, org filtering explicit in the query), and
    for that caller omitting `org_id` would read EVERY tenant's stages. Making
    it a parameter rather than assuming RLS keeps both shapes honest.
    """
    query = db.table(cfg.stages_table).select("*").eq("pipeline", cfg.pipeline)
    if org_id:
        query = query.eq("org_id", org_id)
    if not incluir_inativas:
        query = query.eq("ativo", True)
    rows = query.execute().data or []
    # Sort in Python, not SQL: `posicao` ties are legal (a reorder is a
    # best-effort rewrite), and slug is the stable tiebreak that keeps column
    # order deterministic across requests instead of flickering.
    rows.sort(key=lambda r: (r.get("posicao", 0), r.get("slug") or ""))
    return rows


def get_stage(db, cfg: PipelineConfig, stage_id: str, *, org_id: str | None = None) -> dict:
    query = (
        db.table(cfg.stages_table)
        .select("*")
        .eq("id", stage_id)
        .eq("pipeline", cfg.pipeline)
    )
    if org_id:
        query = query.eq("org_id", org_id)
    rows = query.execute().data or []
    if not rows:
        raise NotFoundError("Etapa", stage_id)
    return rows[0]


def stage_by_role(
    db, cfg: PipelineConfig, papel: str, *, org_id: str | None = None
) -> dict | None:
    """The stage carrying a semantic role, or None.

    This is how features find the stage they depend on. `aceitar_proposta` asks
    for `proposta_aceite` instead of comparing against the literal string
    'proposta', so the user may rename or reposition that column freely.
    """
    query = (
        db.table(cfg.stages_table)
        .select("*")
        .eq("pipeline", cfg.pipeline)
        .eq("papel", papel)
    )
    if org_id:
        query = query.eq("org_id", org_id)
    rows = query.execute().data or []
    return rows[0] if rows else None


def create_stage(db, cfg: PipelineConfig, payload: dict[str, Any], *, org_id: str) -> dict:
    _validate(payload, partial=False)

    label = payload["label"].strip()
    slug = (payload.get("slug") or slugify(label)).strip().lower()

    existing = list_stages(db, cfg, incluir_inativas=True, org_id=org_id)
    if any(s.get("slug") == slug for s in existing):
        raise ValidationError_(
            f"Já existe uma etapa com o identificador '{slug}'. Escolha outro nome.",
            field="label",
        )

    papel = payload.get("papel")
    if papel and any(s.get("papel") == papel for s in existing):
        raise ValidationError_(
            f"Já existe uma etapa com o papel '{papel}' neste funil.", field="papel"
        )

    # Append to the end unless told otherwise — a new stage silently landing in
    # the middle of someone's funnel is a surprise.
    posicao = payload.get("posicao")
    if posicao is None:
        posicao = max((s.get("posicao", 0) for s in existing), default=-1) + 1

    row = {
        "org_id": org_id,
        "pipeline": cfg.pipeline,
        "slug": slug,
        "label": label,
        "cor": payload.get("cor") or "secondary",
        "posicao": posicao,
        "papel": papel,
        "ativo": payload.get("ativo", True),
    }
    created = db.table(cfg.stages_table).insert(row).execute().data or []
    if not created:
        raise AppException(
            code="STAGE_CREATE_FAILED",
            message="Não foi possível criar a etapa.",
            status_code=500,
        )
    return created[0]


def update_stage(
    db, cfg: PipelineConfig, stage_id: str, payload: dict[str, Any],
    *, org_id: str | None = None,
) -> dict:
    """Edit a stage. Renaming is just this — no card is touched.

    That is the whole design: cards reference the stage by id, so changing
    `label` re-labels every past and present card in one write. Nothing is
    copied, so nothing can drift out of sync.
    """
    get_stage(db, cfg, stage_id, org_id=org_id)  # 404s before validating a no-op edit
    _validate(payload, partial=True)

    updates = {k: payload[k] for k in _UPDATABLE if k in payload}
    if "label" in updates:
        updates["label"] = updates["label"].strip()
    if not updates:
        raise ValidationError_("Nenhum campo editável foi enviado.")

    if updates.get("papel"):
        conflict = stage_by_role(db, cfg, updates["papel"], org_id=org_id)
        if conflict and conflict["id"] != stage_id:
            raise ValidationError_(
                f"A etapa '{conflict['label']}' já tem o papel '{updates['papel']}'. "
                "Remova o papel dela primeiro.",
                field="papel",
            )

    rows = (
        db.table(cfg.stages_table).update(updates).eq("id", stage_id).execute().data or []
    )
    if not rows:
        raise NotFoundError("Etapa", stage_id)
    return rows[0]


def count_cards_in_stage(
    db, cfg: PipelineConfig, stage_id: str, *, org_id: str | None = None
) -> int:
    query = db.table(cfg.card_table).select("id").eq("etapa_id", stage_id)
    if org_id:
        query = query.eq("org_id", org_id)
    return len(query.execute().data or [])


def delete_stage(
    db,
    cfg: PipelineConfig,
    stage_id: str,
    *,
    reassign_to: str | None = None,
    org_id: str | None = None,
) -> dict:
    """Delete a stage, refusing the two cases that would lose data or break a feature.

    When the stage still holds cards the caller must nominate `reassign_to`;
    the cards move first, then the stage goes. The alternative — deleting the
    cards with the column — is the kind of "obvious" cascade that quietly
    destroys a user's pipeline.
    """
    stage = get_stage(db, cfg, stage_id, org_id=org_id)

    if stage.get("papel"):
        raise ValidationError_(
            f"A etapa '{stage['label']}' não pode ser excluída porque tem o papel "
            f"'{stage['papel']}', do qual outras funcionalidades dependem. "
            "Atribua o papel a outra etapa antes de excluí-la.",
            field="papel",
        )

    remaining = [
        s for s in list_stages(db, cfg, incluir_inativas=True, org_id=org_id)
        if s["id"] != stage_id
    ]
    if not remaining:
        raise ValidationError_("Um funil precisa de pelo menos uma etapa.")

    total = count_cards_in_stage(db, cfg, stage_id, org_id=org_id)
    if total:
        if not reassign_to:
            raise ValidationError_(
                f"A etapa '{stage['label']}' tem {total} "
                f"{cfg.entity_label}{'s' if total != 1 else ''}. "
                "Escolha para qual etapa mover antes de excluir.",
                field="reassign_to",
            )
        destino = get_stage(db, cfg, reassign_to, org_id=org_id)
        if destino["id"] == stage_id:
            raise ValidationError_("Não é possível mover as cartas para a própria etapa.")
        db.table(cfg.card_table).update({"etapa_id": destino["id"]}).eq(
            "etapa_id", stage_id
        ).execute()

    db.table(cfg.stages_table).delete().eq("id", stage_id).execute()
    return {"id": stage_id, "cards_movidos": total, "movidos_para": reassign_to}


def reorder_stages(
    db, cfg: PipelineConfig, ordered_ids: list[str], *, org_id: str | None = None
) -> list[dict]:
    """Rewrite `posicao` from an ordered id list.

    Takes the FULL order rather than a (id, new_index) pair: a partial reorder
    has to infer what happened to every other stage, and two clients inferring
    differently is how column order starts flickering between users.
    """
    if not ordered_ids:
        raise ValidationError_("Envie a ordem completa das etapas.")

    known = {s["id"]: s for s in list_stages(db, cfg, incluir_inativas=True, org_id=org_id)}
    unknown = [sid for sid in ordered_ids if sid not in known]
    if unknown:
        raise ValidationError_(
            f"Etapas desconhecidas neste funil: {', '.join(unknown)}.", field="ordem"
        )
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ValidationError_("A ordem enviada contém etapas repetidas.", field="ordem")
    if len(ordered_ids) != len(known):
        raise ValidationError_(
            "Envie todas as etapas do funil na ordem desejada "
            f"({len(known)} esperadas, {len(ordered_ids)} recebidas).",
            field="ordem",
        )

    for posicao, stage_id in enumerate(ordered_ids):
        db.table(cfg.stages_table).update({"posicao": posicao}).eq("id", stage_id).execute()

    return list_stages(db, cfg, incluir_inativas=True, org_id=org_id)
