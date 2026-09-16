"""`/api/edicao-fotos/regras` — the per-agency learning loop (contract §7,
`KB § PATTERNS/backend/photo-editing-seed.md`).

AI proposes "don't do this" rules from an org's rejection comments; an
agency admin or platform admin approves/rejects (`learning.decide_rule`);
only the platform admin may override an already-decided rule. Manual
create/edit here (W7) bypass the AI proposer for a human-authored rule —
created directly APROVADA, since writing it down IS the approval.
"Archive" reuses `POST /{id}/rejeitar`: an approved rule is DECIDED, so
the SAME override authority applies whether the origin was the AI
proposer or a manual entry — no separate status/route needed.

R1 keeps every route inside the caller's OWN org — same "platform admins
stay inside their own org too" precedent `deps.py` documents for batches;
`deps.load_visible_rule` 404s (never 403s) a rule from another org so its
existence never leaks, before the engine's own decide-authority runs.

`rule_proposal_debounce_seconds` / `max_rejections_per_proposal`
(contract §7 "editable in the UI") are `fotos_platform_settings` columns
since SW 130 (W8): read and written through `GET|PUT
/configuracoes/plataforma`, read by the engine on every proposer run
(`steps.resolve_rule_proposer_tunables`)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from noctusai_lib.domain.photo_editing import (
    Actor,
    GuideNotActiveError,
    PhotoEditingPorts,
    RuleStatus,
    create_manual_rule,
    decide_rule,
    edit_rule_text,
    request_rule_proposal,
    resolve_effective_guide,
)

from app.modules.edicao_fotos.deps import get_edicao_ports, load_visible_rule, require_org_admin
from app.modules.edicao_fotos.errors import ENGINE_ERRORS, api_error, engine_error
from app.modules.edicao_fotos.presenters import guia_efetivo_out, page_out, regra_out
from app.modules.edicao_fotos.schemas import RegraCreateBody, RegraUpdateBody

router = APIRouter(prefix="/api/edicao-fotos/regras", tags=["edicao-fotos"])

_STATUS_VALUES = {s.value for s in RuleStatus}


@router.get("")
async def list_regras_route(
    status: str | None = Query(default=None),
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    parsed: RuleStatus | None = None
    if status is not None:
        if status not in _STATUS_VALUES:
            raise api_error(422, "status_invalido", f"status inválido: {status}")
        parsed = RuleStatus(status)
    rules = await ports.repo.list_rules(actor.org_id, status=parsed)
    items = [regra_out(r) for r in rules]
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_regra_route(
    body: RegraCreateBody,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    try:
        rule = await create_manual_rule(ports, org_id=actor.org_id, texto=body.texto, actor=actor)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return regra_out(rule)


@router.put("/{regra_id}")
async def update_regra_route(
    regra_id: str,
    body: RegraUpdateBody,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    await load_visible_rule(ports, actor, regra_id)
    try:
        rule = await edit_rule_text(ports, regra_id, texto=body.texto, actor=actor)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return regra_out(rule)


@router.post("/{regra_id}/aprovar")
async def aprovar_regra_route(
    regra_id: str,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    await load_visible_rule(ports, actor, regra_id)
    try:
        rule = await decide_rule(ports, regra_id, approve=True, actor=actor)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return regra_out(rule)


@router.post("/{regra_id}/rejeitar")
async def rejeitar_regra_route(
    regra_id: str,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    """Doubles as "archive" for an already-approved (manual or
    AI-proposed) rule — see module docstring."""
    await load_visible_rule(ports, actor, regra_id)
    try:
        rule = await decide_rule(ports, regra_id, approve=False, actor=actor)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return regra_out(rule)


@router.post("/propor-agora", status_code=202)
async def propor_agora_route(
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    """The "propor agora" button — enqueues `fotos.propor_regras` to run
    NOW instead of waiting for the rejection-settling debounce."""
    job = await request_rule_proposal(ports, actor.org_id, requested_by=actor.user_id)
    return {"job_id": str(job.id), "status": str(getattr(job.status, "value", job.status))}


@router.get("/guia-efetivo")
async def guia_efetivo_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    """The current effective guide (company guide + this org's approved
    rules) + its version history. `atual` is `null` while no company guide
    is active yet — a read never raises for that (unlike `submeter`,
    which 409s)."""
    try:
        atual = await resolve_effective_guide(ports, actor.org_id)
    except GuideNotActiveError:
        atual = None
    items, total = await ports.repo.list_effective_guides(
        actor.org_id, limit=page_size, offset=(page - 1) * page_size
    )
    return {
        "atual": guia_efetivo_out(atual) if atual is not None else None,
        "historico": page_out(
            [guia_efetivo_out(g) for g in items], page=page, page_size=page_size, total=total
        ),
    }
