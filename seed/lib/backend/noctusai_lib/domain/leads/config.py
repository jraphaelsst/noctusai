"""`LeadsConfig` -- the funnel's stages and origins are DATA the product supplies, never an enum.

A stage is `(slug, label, color, tag)`; leads reference it by `slug`, which is the stable machine key
(a relabel is one edit here and every card follows). Origins work the same way. Nothing in the
database constrains either column, so changing the lists later needs no migration -- a lead whose
stage was removed from the config is still listed and shows up in the board's "Sem etapa" column
(`service.ORPHAN_STAGE`) instead of vanishing.

`stages` / `origins` accept plain strings (label = the slug capitalised) for convenience.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence, Union

from noctusai_lib.domain.pipeline.stages import STAGE_COLORS

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class LeadStage:
    slug: str
    label: str
    #: one of the pipeline organ's colour tokens (`STAGE_COLORS`), or None
    color: Optional[str] = None
    #: the coloured status-tag label a card shows for this stage (None => the stage `label`). Two stages may share a
    #: tag ("Em atendimento" over both "Atendimento" and "Negociação").
    tag: Optional[str] = None

    def __post_init__(self) -> None:
        if not _SLUG.match(self.slug or ""):
            raise ValueError(f"LeadStage.slug must be a lowercase identifier, got {self.slug!r}")
        if not (self.label or "").strip():
            raise ValueError(f"LeadStage {self.slug!r}: label must not be empty")
        if self.color is not None and self.color not in STAGE_COLORS:
            raise ValueError(f"LeadStage {self.slug!r}: color must be one of {STAGE_COLORS}, got {self.color!r}")
        if self.tag is not None and not self.tag.strip():
            raise ValueError(f"LeadStage {self.slug!r}: tag must not be blank (use None for the label)")

    def as_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label, "color": self.color, "tag": self.tag or self.label}


@dataclass(frozen=True)
class LeadOrigin:
    slug: str
    label: str

    def __post_init__(self) -> None:
        if not _SLUG.match(self.slug or ""):
            raise ValueError(f"LeadOrigin.slug must be a lowercase identifier, got {self.slug!r}")
        if not (self.label or "").strip():
            raise ValueError(f"LeadOrigin {self.slug!r}: label must not be empty")

    def as_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label}


#: The contract's name for a funnel stage.
Stage = LeadStage


def _stage(x: Union[LeadStage, str]) -> LeadStage:
    return x if isinstance(x, LeadStage) else LeadStage(slug=x, label=x.replace("_", " ").capitalize())


def _origin(x: Union[LeadOrigin, str]) -> LeadOrigin:
    return x if isinstance(x, LeadOrigin) else LeadOrigin(slug=x, label=x.replace("_", " ").capitalize())


@dataclass(frozen=True)
class LeadsConfig:
    """
    Attributes:
        stages: the funnel columns, left to right. The FIRST one receives new leads.
        origins: where a lead can come from.
        whatsapp_origin: slug stamped on leads born from an inbound WhatsApp chat (must be in `origins`).
        default_origin: slug used when a manual create names none (default: `whatsapp_origin`'s sibling
            `outro` when present, else the first origin).
        table: physical table name inside the product schema.
        board_stage_limit: cards a board response carries per column (`total` still counts them all).
        on_stage_entered: optional host hook `(org_id, lead, stage_slug) -> Any`, fired AFTER a lead is saved on a
            stage it was not on before (create, WhatsApp-born create, update that changes `stage`, move across
            columns). Sync; called in the request thread. A raise is LOGGED and surfaced on the returned lead as
            `stage_hook_error` -- it never rolls the lead write back (the lead move is the user's fact).
    """

    stages: Sequence[Union[LeadStage, str]]
    origins: Sequence[Union[LeadOrigin, str]]
    whatsapp_origin: str = "whatsapp"
    default_origin: Optional[str] = None
    table: str = "leads"
    board_stage_limit: int = 100
    on_stage_entered: Optional[Callable[[str, dict, str], Any]] = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        stages = tuple(_stage(s) for s in self.stages)
        origins = tuple(_origin(o) for o in self.origins)
        if not stages:
            raise ValueError("LeadsConfig needs at least one stage")
        if not origins:
            raise ValueError("LeadsConfig needs at least one origin")
        for what, items in (("stage", stages), ("origin", origins)):
            slugs = [i.slug for i in items]
            if len(set(slugs)) != len(slugs):
                raise ValueError(f"LeadsConfig: duplicate {what} slug in {slugs}")
        origin_slugs = {o.slug for o in origins}
        if self.whatsapp_origin not in origin_slugs:
            raise ValueError(f"LeadsConfig.whatsapp_origin {self.whatsapp_origin!r} is not one of the origins {sorted(origin_slugs)}")
        default = self.default_origin or ("outro" if "outro" in origin_slugs else origins[0].slug)
        if default not in origin_slugs:
            raise ValueError(f"LeadsConfig.default_origin {default!r} is not one of the origins {sorted(origin_slugs)}")
        if not _IDENT.match(self.table or ""):
            raise ValueError(f"LeadsConfig.table must be a bare lowercase identifier, got {self.table!r}")
        if self.board_stage_limit < 1:
            raise ValueError("LeadsConfig.board_stage_limit must be >= 1")
        object.__setattr__(self, "stages", stages)
        object.__setattr__(self, "origins", origins)
        object.__setattr__(self, "default_origin", default)

    @property
    def stage_slugs(self) -> tuple[str, ...]:
        return tuple(s.slug for s in self.stages)  # type: ignore[union-attr]

    @property
    def origin_slugs(self) -> tuple[str, ...]:
        return tuple(o.slug for o in self.origins)  # type: ignore[union-attr]

    @property
    def first_stage(self) -> str:
        return self.stage_slugs[0]

    def stage(self, slug: str) -> Optional[LeadStage]:
        return next((s for s in self.stages if s.slug == slug), None)  # type: ignore[union-attr]

    def as_dict(self) -> dict:
        return {
            "stages": [s.as_dict() for s in self.stages],  # type: ignore[union-attr]
            "origins": [o.as_dict() for o in self.origins],  # type: ignore[union-attr]
            "whatsapp_origin": self.whatsapp_origin,
            "default_origin": self.default_origin,
        }


def stages_of(items: Iterable[Union[LeadStage, str]]) -> tuple[LeadStage, ...]:
    return tuple(_stage(i) for i in items)


__all__ = ["LeadOrigin", "LeadStage", "LeadsConfig", "Stage"]
