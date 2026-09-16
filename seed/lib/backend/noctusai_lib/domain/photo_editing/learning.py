"""Per-agency learning loop ("A now, B later").

A: the AI proposes "don't do this" rules from an agency's rejection
comments; a human approves; approved rules join that agency's effective
guide. B (a trainable model) consumes ``fotos_dataset`` later.

Decision authority (contract §1, mirrored by the consumer's DB trigger):
an agency admin of the rule's org, or a platform admin, may decide a
PROPOSED rule; only a platform admin may flip an already-decided one
(recorded as ``override_platform_admin``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from noctusai_lib.domain.photo_editing.costs import CATEGORY_OPENAI_TEXT, record_ai_cost
from noctusai_lib.domain.photo_editing.guide import normalize_text
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
from noctusai_lib.domain.photo_editing.prompts import render_rule_proposer_prompt
from noctusai_lib.domain.photo_editing.types import (
    AGENCY_ADMIN_ROLES,
    JobType,
    OrgRule,
    ProposalCursor,
    RuleStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Actor:
    """Server-resolved identity of whoever is acting (never SSO metadata)."""

    user_id: str
    org_id: str | None
    org_role: str | None
    is_platform_admin: bool = False

    @property
    def is_agency_admin(self) -> bool:
        return self.org_role in AGENCY_ADMIN_ROLES


class RuleNotFoundError(LookupError):
    code = "regra_nao_encontrada"


class RuleDecisionForbiddenError(PermissionError):
    code = "decisao_regra_proibida"


class InvalidModelOutputError(ValueError):
    """The model answered outside its schema — retryable."""

    code = "resposta_invalida_modelo"


_DECIDED = (RuleStatus.APROVADA, RuleStatus.REJEITADA)


def rule_key(texto: str) -> str:
    """Duplicate-detection key: whitespace- and case-insensitive."""
    return " ".join(normalize_text(texto).split()).casefold()


def can_decide_rule(actor: Actor, rule: OrgRule, target: RuleStatus) -> bool:
    if actor.is_platform_admin:
        return True
    if actor.org_id != rule.org_id or not actor.is_agency_admin:
        return False
    # An agency admin may decide a proposal, or repeat the same decision;
    # flipping a decided rule is a platform-admin override.
    return rule.status is RuleStatus.PROPOSTA or rule.status is target


async def decide_rule(
    ports: PhotoEditingPorts, regra_id: str, *, approve: bool, actor: Actor
) -> OrgRule:
    rule = await ports.repo.get_rule(regra_id)
    if rule is None:
        raise RuleNotFoundError(f"regra {regra_id} não encontrada")
    target = RuleStatus.APROVADA if approve else RuleStatus.REJEITADA
    if not can_decide_rule(actor, rule, target):
        raise RuleDecisionForbiddenError("sem permissão para decidir esta regra")
    if rule.status is target:
        return rule  # idempotent
    override = rule.status in _DECIDED
    return await ports.repo.update_rule(
        regra_id,
        status=target,
        decidido_por=actor.user_id,
        decidido_em=ports.clock(),
        override_platform_admin=override or rule.override_platform_admin,
    )


def _parse_proposals(data: dict[str, Any], n_comments: int) -> list[tuple[str, list[int]]]:
    regras = data.get("regras")
    if not isinstance(regras, list):
        raise InvalidModelOutputError("campo 'regras' ausente ou inválido")
    out: list[tuple[str, list[int]]] = []
    for item in regras:
        if not isinstance(item, dict):
            raise InvalidModelOutputError("regra proposta não é um objeto")
        texto = item.get("texto")
        refs = item.get("comentarios")
        if not isinstance(texto, str) or not texto.strip():
            raise InvalidModelOutputError("regra proposta sem texto")
        if not isinstance(refs, list) or not all(isinstance(i, int) for i in refs):
            raise InvalidModelOutputError("regra proposta sem comentários de origem")
        bad = [i for i in refs if not 1 <= i <= n_comments]
        if bad:
            raise InvalidModelOutputError(f"índices de comentário inválidos: {bad}")
        out.append((texto.strip(), refs))
    return out


async def propose_rules(ports: PhotoEditingPorts, org_id: str) -> list[OrgRule]:
    """Run the rule proposer over the org's rejections since the cursor.

    Cursor semantics: ``ultima_execucao_em`` is the WATERMARK — the
    ``created_at`` of the newest rejection already processed — so a
    rejection written during a run is never skipped.
    """
    repo = ports.repo
    cfg = ports.config
    cursor = await repo.get_cursor(org_id) or ProposalCursor(org_id=org_id)
    rejections = await repo.list_rejections(
        org_id, after=cursor.ultima_execucao_em, limit=cfg.max_rejections_per_proposal
    )
    if not rejections:
        return []
    existing = [
        r
        for r in await repo.list_rules(org_id)
        if r.status in (RuleStatus.PROPOSTA, RuleStatus.APROVADA)
    ]
    comments = [d.comentario or "" for d in rejections]
    rendered = render_rule_proposer_prompt(comments, [r.texto for r in existing])
    result = await ports.llm.analyze(
        images=[],
        prompt=rendered.text,
        response_schema=rendered.response_schema or {},
        model=cfg.rule_proposer_model,
        org_id=org_id,
        schema_name="propor_regras",
    )
    proposals = _parse_proposals(result.data, len(rejections))
    if result.usage is not None:
        await record_ai_cost(
            ports,
            org_id=org_id,
            step=JobType.PROPOR_REGRAS,
            category=CATEGORY_OPENAI_TEXT,
            operation="chat",
            kind="chat",
            model=cfg.rule_proposer_model,
            usage=result.usage,
            model_version=result.model_version,
        )
    else:
        logger.warning(
            "photo_editing.learning.cost_not_recorded org_id=%s reason=usage_unavailable",
            org_id,
        )

    seen = {rule_key(r.texto) for r in existing}
    created: list[OrgRule] = []
    for texto, refs in proposals:
        key = rule_key(texto)
        if key in seen:
            continue
        seen.add(key)
        origem = tuple(
            {
                "decisao_id": rejections[i - 1].id,
                "foto_id": rejections[i - 1].foto_id,
                "comentario": rejections[i - 1].comentario,
            }
            for i in refs
        )
        created.append(await repo.add_rule(org_id=org_id, texto=texto, origem_comentarios=origem))

    newest = rejections[-1]
    await repo.save_cursor(
        ProposalCursor(
            org_id=org_id,
            ultima_decisao_id=newest.id,
            ultima_execucao_em=newest.created_at,
            rejeicoes_desde_ultima=0,
        )
    )
    return created


__all__ = [
    "Actor",
    "InvalidModelOutputError",
    "RuleDecisionForbiddenError",
    "RuleNotFoundError",
    "can_decide_rule",
    "decide_rule",
    "propose_rules",
    "rule_key",
]
