"""Style guides — company guide versions and the per-org effective guide.

Effective guide = the ACTIVE company guide + that org's APPROVED rules,
rendered to deterministic text and identified by its sha256. It is
resolved and snapshotted onto the batch at submit (``guia_efetivo_id`` +
``guia_efetivo_sha256``), so an in-flight batch never changes mid-run.

Company guide versions are immutable: regeneration creates a new DRAFT,
"restore" clones an old version as a new draft, and only an explicit
activation (platform admin or curator — enforced by the consumer's route)
makes a version the one in use.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from noctusai_lib.domain.photo_editing.ports import ImageInput, PhotoEditingPorts
from noctusai_lib.domain.photo_editing.prompts import render_style_guide_prompt
from noctusai_lib.domain.photo_editing.types import (
    EffectiveGuide,
    OrgRule,
    ReferencePair,
    RuleStatus,
    StyleGuide,
    sha256_text,
)

logger = logging.getLogger(__name__)


class GuideNotActiveError(RuntimeError):
    """No company guide is active — batches cannot be submitted."""

    code = "guia_nao_ativo"


class GuideVersionNotFoundError(LookupError):
    code = "guia_versao_inexistente"


def normalize_text(text: str) -> str:
    """Line endings → ``\\n``, trailing spaces stripped, one final newline."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def order_rules(rules: Sequence[OrgRule]) -> list[OrgRule]:
    """Canonical rule order: approval time, then id — stable across reads."""
    return sorted(
        rules,
        key=lambda r: (
            (r.decidido_em or r.created_at).isoformat() if (r.decidido_em or r.created_at) else "",
            r.id,
        ),
    )


def rule_set_sha256(regra_ids: Sequence[str]) -> str:
    return sha256_text("\n".join(regra_ids))


@dataclass(frozen=True)
class ComposedGuide:
    texto: str
    sha256: str
    regra_ids: tuple[str, ...]


def compose_effective_guide(guide: StyleGuide, rules: Sequence[OrgRule]) -> ComposedGuide:
    """Pure + deterministic. Only APPROVED rules are included."""
    approved = order_rules([r for r in rules if r.status is RuleStatus.APROVADA])
    parts = [
        f"# Guia de estilo da empresa (versão {guide.versao})",
        "",
        normalize_text(guide.texto).rstrip("\n"),
    ]
    if approved:
        parts += ["", "# Regras desta imobiliária (não faça)"]
        parts += [f"{i}. {normalize_text(r.texto).strip()}" for i, r in enumerate(approved, 1)]
    texto = normalize_text("\n".join(parts))
    return ComposedGuide(
        texto=texto,
        sha256=sha256_text(texto),
        regra_ids=tuple(r.id for r in approved),
    )


async def resolve_effective_guide(ports: PhotoEditingPorts, org_id: str) -> EffectiveGuide:
    """Compose, version the org's rule set if it changed, persist (idempotent
    by ``(org_id, sha256)``) and return the effective guide to snapshot."""
    repo = ports.repo
    guide = await repo.get_active_guide()
    if guide is None:
        raise GuideNotActiveError("nenhum guia de estilo ativo")
    rules = await repo.list_rules(org_id, status=RuleStatus.APROVADA)
    composed = compose_effective_guide(guide, rules)
    rule_set_id: str | None = None
    if composed.regra_ids:
        sha = rule_set_sha256(composed.regra_ids)
        latest = await repo.latest_rule_set(org_id)
        if latest is not None and latest.sha256 == sha:
            rule_set_id = latest.id
        else:
            created = await repo.create_rule_set(
                org_id=org_id,
                versao=(latest.versao + 1) if latest else 1,
                regra_ids=composed.regra_ids,
                sha256=sha,
            )
            rule_set_id = created.id
    return await repo.get_or_create_effective_guide(
        org_id=org_id,
        guia_estilo_id=guide.id,
        conjunto_regras_id=rule_set_id,
        texto=composed.texto,
        sha256=composed.sha256,
    )


async def create_draft(
    ports: PhotoEditingPorts,
    *,
    texto: str,
    gerado_de_versao: int | None,
    criado_por: str | None,
) -> StyleGuide:
    texto = normalize_text(texto)
    versao = await ports.repo.latest_guide_version() + 1
    return await ports.repo.create_guide(
        versao=versao,
        texto=texto,
        sha256=sha256_text(texto),
        gerado_de_versao=gerado_de_versao,
        criado_por=criado_por,
    )


async def restore_version(ports: PhotoEditingPorts, versao: int, *, criado_por: str) -> StyleGuide:
    """Clone ``versao`` as a NEW draft (versions stay immutable)."""
    old = await ports.repo.get_guide(versao)
    if old is None:
        raise GuideVersionNotFoundError(f"versão {versao} não existe")
    return await create_draft(
        ports, texto=old.texto, gerado_de_versao=old.versao, criado_por=criado_por
    )


async def activate_version(ports: PhotoEditingPorts, versao: int, *, ativado_por: str) -> StyleGuide:
    if await ports.repo.get_guide(versao) is None:
        raise GuideVersionNotFoundError(f"versão {versao} não existe")
    return await ports.repo.activate_guide(versao, ativado_por=ativado_por, at=ports.clock())


async def reference_images(
    ports: PhotoEditingPorts, pairs: Sequence[ReferencePair]
) -> list[ImageInput]:
    """``[antes, depois]`` per pair, in order: bytes read from
    ``ports.reference_storage`` when it is wired (private bucket keys),
    else the stored URLs as-is. A missing object RAISES — a guide built
    from a partial pool would silently misrepresent the standard."""
    storage = ports.reference_storage
    images: list[ImageInput] = []
    for p in pairs:
        for ref in (p.antes_url, p.depois_url):
            images.append(await storage.get(ref) if storage is not None else ref)
    return images


async def generate_draft_from_pool(ports: PhotoEditingPorts) -> StyleGuide | None:
    """Style-guide builder: pool pairs → AI-written DRAFT. ``None`` when the
    pool is empty (nothing to learn from; logged, not an error).

    Platform-scope call: there is no org to bill, so the cost is recorded
    only through the llm organ's process-wide usage sink, never
    ``cost_ledger`` (whose ``org_id`` is NOT NULL).
    """
    cfg = ports.config
    pairs = await ports.repo.list_active_references(limit=cfg.max_reference_pairs_per_guide)
    if not pairs:
        logger.info("photo_editing.guide.regen_skipped reason=empty_pool")
        return None
    rendered = render_style_guide_prompt(pairs)
    images = await reference_images(ports, pairs)
    result = await ports.llm.analyze(
        images=images,
        prompt=rendered.text,
        response_schema=rendered.response_schema or {},
        model=cfg.style_guide_model,
        org_id=None,
        schema_name="guia_estilo",
    )
    texto = result.data.get("guia")
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("style-guide builder returned an empty guide")
    active = await ports.repo.get_active_guide()
    return await create_draft(
        ports,
        texto=texto,
        gerado_de_versao=active.versao if active else None,
        criado_por=None,
    )


__all__ = [
    "ComposedGuide",
    "GuideNotActiveError",
    "GuideVersionNotFoundError",
    "activate_version",
    "compose_effective_guide",
    "create_draft",
    "generate_draft_from_pool",
    "normalize_text",
    "order_rules",
    "reference_images",
    "resolve_effective_guide",
    "restore_version",
    "rule_set_sha256",
]
