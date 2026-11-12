"""CRM presets — a market's DEFAULT funnel, which each ORG then edits.

Owner decision (2026-11-08): funnel stages are a market default, never a seed
constant. One's real-estate funnel has "Visita"; the noc funnel and Senseys' do
not. The seed owns the MECHANICS (rows, ordering, roles, seeding, the no-op
rule); the LIST lives in a `CrmPreset` the market ships.

How the pieces fit:

  * `CrmPreset.pipelines` — board key -> default `StageDefault` tuple. Seeded
    lazily per org by `ensure_preset_stages` (-> `ensure_default_stages`).
    After that the org renames / recolors / reorders / adds / removes stages
    (`PipelineStagesManager`); the `slug` stays immutable.
  * Code keys on `papel`, NEVER on slug or position. Canonical roles are the
    `ROLE_*` constants below; a market declares extra ones (`visita`, ...).
  * A feature that needs a role the org's funnel lacks is a DECLARED no-op:
    `stage_for_role` returns None and logs at info — no exception. "Visit
    scheduled" moves the card to `papel='visita'` if the org has that stage,
    else only the activity is recorded.

Dependency note: this module must not import `domain.leads` or
`domain.pipeline.funnel` (both import this package), so `LostReasonDefault` /
`OriginDefault` mirror `LostReason` / `LeadOrigin` field-for-field.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from noctusai_lib.domain.activities.types import ActivityTypeSpec as ActivityTypeDefault

from .config import PipelineConfig
from .defaults import StageDefault, ensure_default_stages
from .stages import STAGE_COLORS, stage_by_role

logger = logging.getLogger(__name__)

# -- canonical roles (every CRM) ------------------------------------------------
ROLE_ENTRADA = "entrada"
ROLE_QUALIFICADO = "qualificado"
ROLE_PROPOSTA = "proposta"
ROLE_PROPOSTA_ACEITE = "proposta_aceite"
ROLE_GANHO = "ganho"
ROLE_FINAL = "final"
CANONICAL_CRM_ROLES: tuple[str, ...] = (
    ROLE_ENTRADA,
    ROLE_QUALIFICADO,
    ROLE_PROPOSTA,
    ROLE_PROPOSTA_ACEITE,
    ROLE_GANHO,
    ROLE_FINAL,
)

# -- market roles (declared by the market, known here so presets validate) ------
ROLE_VISITA = "visita"  # real estate
ROLE_SESSAO_EXPERIMENTAL = "sessao_experimental"  # clinics
ROLE_BRIEFING = "briefing"  # agencies
ROLE_CONTATADO = "contatado"  # SaaS (core's gate keys on it today)
MARKET_CRM_ROLES: tuple[str, ...] = (
    ROLE_VISITA,
    ROLE_SESSAO_EXPERIMENTAL,
    ROLE_BRIEFING,
    ROLE_CONTATADO,
)
KNOWN_CRM_ROLES: tuple[str, ...] = CANONICAL_CRM_ROLES + MARKET_CRM_ROLES

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class LostReasonDefault:
    """Mirrors `funnel.LostReason(codigo, label, exige_texto)`."""

    codigo: str
    label: str
    exige_texto: bool = False


@dataclass(frozen=True)
class OriginDefault:
    """Mirrors `leads.LeadOrigin(slug, label)`."""

    slug: str
    label: str


@dataclass(frozen=True)
class CrmPreset:
    """One market's default CRM configuration (data, no behaviour)."""

    market: str
    pipelines: Mapping[str, tuple[StageDefault, ...]]
    lost_reasons: tuple[LostReasonDefault, ...] = ()
    lead_origins: tuple[OriginDefault, ...] = ()
    #: The market's activity types (`domain.activities`): data seeded lazily per org, which the org then edits. Empty =>
    #: the organ's generic set (tarefa / ligacao / reuniao); a market that declares any lists ALL it wants.
    activity_types: tuple[ActivityTypeDefault, ...] = ()

    def __post_init__(self) -> None:
        if not (self.market or "").strip():
            raise ValueError("CrmPreset.market must not be empty")
        if not self.pipelines:
            raise ValueError(f"CrmPreset {self.market!r}: declare at least one pipeline")
        norm = {k: tuple(v) for k, v in self.pipelines.items()}
        for board, stages in norm.items():
            if not stages:
                raise ValueError(f"CrmPreset {self.market!r}: pipeline {board!r} has no stages")
            slugs = [s.slug for s in stages]
            if len(set(slugs)) != len(slugs):
                raise ValueError(f"CrmPreset {self.market!r}/{board}: repeated slug")
            roles = [s.papel for s in stages if s.papel]
            if len(set(roles)) != len(roles):
                raise ValueError(f"CrmPreset {self.market!r}/{board}: a role sits on two stages")
            for s in stages:
                if not _SLUG.match(s.slug):
                    raise ValueError(f"CrmPreset {self.market!r}/{board}: bad slug {s.slug!r}")
                if s.cor not in STAGE_COLORS:
                    raise ValueError(f"CrmPreset {self.market!r}/{board}/{s.slug}: bad cor {s.cor!r}")
                if s.papel and s.papel not in KNOWN_CRM_ROLES:
                    raise ValueError(
                        f"CrmPreset {self.market!r}/{board}/{s.slug}: unknown role {s.papel!r}"
                    )
        object.__setattr__(self, "pipelines", norm)
        object.__setattr__(self, "lost_reasons", tuple(self.lost_reasons))
        object.__setattr__(self, "lead_origins", tuple(self.lead_origins))
        object.__setattr__(self, "activity_types", tuple(self.activity_types))
        act_slugs = [a.slug for a in self.activity_types]
        if len(set(act_slugs)) != len(act_slugs):
            raise ValueError(f"CrmPreset {self.market!r}: repeated activity-type slug")
        codes = [r.codigo for r in self.lost_reasons]
        if len(set(codes)) != len(codes):
            raise ValueError(f"CrmPreset {self.market!r}: repeated lost-reason code")
        origins = [o.slug for o in self.lead_origins]
        if len(set(origins)) != len(origins):
            raise ValueError(f"CrmPreset {self.market!r}: repeated origin slug")

    def stage_roles(self, board: str | None = None) -> tuple[str, ...]:
        """Roles an org may assign on its stages, for `PipelineConfig.stage_roles`.

        Every known role (canonical + market), not only the ones this preset's
        default uses: an org may add a "Sessão experimental" stage to a funnel
        whose market default has none. The list bounds validation; whether a
        stage exists for a role stays the org's choice (hence the no-op rule).
        """
        return KNOWN_CRM_ROLES


def ensure_preset_stages(
    db: Any,
    preset: CrmPreset,
    configs: Mapping[str, PipelineConfig],
    *,
    org_id: str,
) -> dict[str, bool]:
    """Lazily seed every board of `preset` for the org; `{board: seeded?}`.

    `configs` maps board key -> the product's `PipelineConfig`. A preset board
    without a config is a wiring bug and raises (no silent skip). Already
    configured boards (active or not) are left alone — the org's edits win.
    """
    missing = [b for b in preset.pipelines if b not in configs]
    if missing:
        raise ValueError(
            f"CrmPreset {preset.market!r}: no PipelineConfig for board(s) {', '.join(sorted(missing))}"
        )
    return {
        board: ensure_default_stages(db, configs[board], stages, org_id=org_id)
        for board, stages in preset.pipelines.items()
    }


def stage_for_role(
    db: Any,
    cfg: PipelineConfig,
    papel: str,
    *,
    org_id: str,
    feature: str,
) -> dict | None:
    """The org's active stage carrying `papel`, or None as a DECLARED no-op.

    Use for every feature that moves a card by role. When the org's funnel has
    no such stage (One has `visita`, Senseys does not) the feature skips the
    move, records the skip at info and carries on — never raises.
    """
    stage = stage_by_role(db, cfg, papel, org_id=org_id)
    if stage is not None and stage.get("ativo", True):
        return stage
    logger.info(
        "crm role no-op: feature=%s needs papel=%s but org=%s pipeline=%s has no active stage with it",
        feature,
        papel,
        org_id,
        cfg.pipeline,
    )
    return None
