"""Per-step AI model selection (edicao-fotos W8).

Four engine steps call a text/vision model; each has its own setting on
``PlatformSettings`` (platform admin, from the UI) and falls back to the
owner's plan §1 default on ``PhotoEditingConfig`` when unset. The image
editor is NOT here — it is per org (``OrgSettings.modelo_editor_id``).

Every step resolves its model AT CALL TIME (one settings read), so a change
in the UI reaches the next job without a restart; the model actually used
is recorded on each cost row / evaluation, as before.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from noctusai_lib.domain.photo_editing.ports import PhotoEditingConfig, PhotoEditingPorts
from noctusai_lib.domain.photo_editing.types import PlatformSettings
from noctusai_lib.integrations.llm.models import ModelKind, is_priced, models_for


class Step(str, Enum):
    GUIA = "guia"  # style-guide builder (reads the reference images)
    AVALIADOR = "avaliador"  # evaluator (reads original + edited)
    REGRAS = "regras"  # rule proposer (text)
    NOTAS = "notas"  # daily model-note writer (text)


#: The catalog kind each step's model must have.
STEP_KIND: dict[Step, ModelKind] = {
    Step.GUIA: "vision",
    Step.AVALIADOR: "vision",
    Step.REGRAS: "chat",
    Step.NOTAS: "chat",
}

#: `PlatformSettings` field per step.
STEP_SETTING: dict[Step, str] = {
    Step.GUIA: "modelo_guia",
    Step.AVALIADOR: "modelo_avaliador",
    Step.REGRAS: "modelo_regras",
    Step.NOTAS: "modelo_notas",
}

_CONFIG_DEFAULT: dict[Step, str] = {
    Step.GUIA: "style_guide_model",
    Step.AVALIADOR: "evaluator_model",
    Step.REGRAS: "rule_proposer_model",
    Step.NOTAS: "note_writer_model",
}


class StepModelError(ValueError):
    """A model that cannot serve a step (unknown / disabled / unpriced)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def default_step_model(config: PhotoEditingConfig, step: Step) -> str:
    return getattr(config, _CONFIG_DEFAULT[step])


def step_model(platform: PlatformSettings, config: PhotoEditingConfig, step: Step) -> str:
    return getattr(platform, STEP_SETTING[step]) or default_step_model(config, step)


async def resolve_step_model(ports: PhotoEditingPorts, step: Step) -> str:
    platform = await ports.repo.get_platform_settings()
    return step_model(platform, ports.config, step)


def validate_step_model(config: PhotoEditingConfig, step: Step, model: str) -> None:
    """Refuse a model the step could not bill: it must be an ENABLED
    catalog row of the step's kind, with every rate set."""
    kind = STEP_KIND[step]
    entry = next((m for m in models_for(config.llm_provider, kind) if m.id == model), None)
    if entry is None:
        raise StepModelError(
            "modelo_desconhecido",
            f"{model} não é um modelo {kind} habilitado no catálogo",
        )
    if not is_priced(entry):
        raise StepModelError("modelo_sem_preco", f"{model} não tem preço cadastrado")


# ---------------------------------------------------------------------------
# Rule-proposer tunables (settings override → engine default), read at call time
# ---------------------------------------------------------------------------

#: Bounds the admin UI may set (validated at the route and in SQL).
RULE_PROPOSAL_DEBOUNCE_RANGE = (0, 7 * 86_400)
REJECTIONS_PER_PROPOSAL_RANGE = (1, 500)


def rule_proposal_window(platform: PlatformSettings, config: PhotoEditingConfig) -> int:
    value = platform.rule_proposal_debounce_seconds
    return config.rule_proposal_debounce_seconds if value is None else int(value)


def rejections_per_proposal(platform: PlatformSettings, config: PhotoEditingConfig) -> int:
    value = platform.max_rejections_per_proposal
    return config.max_rejections_per_proposal if value is None else int(value)


async def resolve_rule_proposer_tunables(ports: PhotoEditingPorts) -> tuple[int, int]:
    """``(debounce_seconds, max_rejections)`` for the next run — one read."""
    platform = await ports.repo.get_platform_settings()
    return rule_proposal_window(platform, ports.config), rejections_per_proposal(platform, ports.config)


@dataclass(frozen=True)
class StepModelView:
    step: Step
    kind: ModelKind
    modelo: str
    padrao: str
    personalizado: bool


def step_models_view(platform: PlatformSettings, config: PhotoEditingConfig) -> list[StepModelView]:
    return [
        StepModelView(
            step=step,
            kind=STEP_KIND[step],
            modelo=step_model(platform, config, step),
            padrao=default_step_model(config, step),
            personalizado=getattr(platform, STEP_SETTING[step]) is not None,
        )
        for step in Step
    ]


__all__ = [
    "REJECTIONS_PER_PROPOSAL_RANGE",
    "RULE_PROPOSAL_DEBOUNCE_RANGE",
    "STEP_KIND",
    "STEP_SETTING",
    "Step",
    "StepModelError",
    "StepModelView",
    "default_step_model",
    "rejections_per_proposal",
    "resolve_rule_proposer_tunables",
    "resolve_step_model",
    "rule_proposal_window",
    "step_model",
    "step_models_view",
    "validate_step_model",
]
