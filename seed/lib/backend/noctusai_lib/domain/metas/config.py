"""`MetasConfig` -- what a product decides about its metas organ; everything else is the seed's.

Event types, modalities and goal categories are DATA the product supplies (changing them never needs a migration: the
columns are plain TEXT). A real-estate house says `venda / locacao / captacao`, a clinic `consulta / retorno`.

A goal category says where its REALIZED number comes from (`source`):
    "value"        sum of the events' `value` (money: VGV, revenue)
    "points"       sum of the events' points
    "count:<type>" number of events of that type
    "manual"       the goal's own `current` (contributions) -- the personal-goal case
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


@dataclass(frozen=True)
class EventType:
    slug: str
    label: str

    def __post_init__(self) -> None:
        if not _SLUG.match(self.slug):
            raise ValueError(f"EventType.slug {self.slug!r} must be a lower_snake slug")


@dataclass(frozen=True)
class Modality:
    slug: str
    label: str

    def __post_init__(self) -> None:
        if not _SLUG.match(self.slug):
            raise ValueError(f"Modality.slug {self.slug!r} must be a lower_snake slug")


@dataclass(frozen=True)
class GoalCategory:
    slug: str
    label: str
    source: str = "manual"

    def __post_init__(self) -> None:
        if not _SLUG.match(self.slug):
            raise ValueError(f"GoalCategory.slug {self.slug!r} must be a lower_snake slug")
        if not (self.source in ("value", "points", "manual") or (self.source.startswith("count:") and len(self.source) > 6)):
            raise ValueError(f"GoalCategory.source {self.source!r} must be value|points|manual|count:<event_type>")


@dataclass(frozen=True)
class RuleSeed:
    """A default point rule the product ships (`POST /rules/defaults` copies the missing ones into the org)."""

    event_type: str
    modality: str
    points: float
    description: str = ""


@dataclass(frozen=True)
class MetasConfig:
    schema: str
    event_types: tuple[EventType, ...] = ()
    modalities: tuple[Modality, ...] = (Modality("default", "Padrão"),)
    categories: tuple[GoalCategory, ...] = (GoalCategory("generic", "Meta", "manual"),)
    default_rules: tuple[RuleSeed, ...] = ()
    table_prefix: str = "mt_"

    def __post_init__(self) -> None:
        if not self.schema or not _IDENT.match(self.schema):
            raise ValueError(f"MetasConfig.schema {self.schema!r} must be a lower_snake identifier")
        if not _IDENT.match(self.table_prefix or ""):
            raise ValueError(f"MetasConfig.table_prefix {self.table_prefix!r} must be a lower_snake identifier")
        for what, items in (("event_types", self.event_types), ("modalities", self.modalities), ("categories", self.categories)):
            slugs = [i.slug for i in items]
            if len(slugs) != len(set(slugs)):
                raise ValueError(f"MetasConfig.{what} has a duplicate slug")
        known_events, known_mods = {e.slug for e in self.event_types}, {m.slug for m in self.modalities}
        for rule in self.default_rules:
            if rule.event_type not in known_events or rule.modality not in known_mods:
                raise ValueError(f"default rule {rule.event_type}/{rule.modality} names an undeclared event type or modality")
        for cat in self.categories:
            if cat.source.startswith("count:") and cat.source[6:] not in known_events:
                raise ValueError(f"category {cat.slug!r} counts undeclared event type {cat.source[6:]!r}")

    def table(self, name: str) -> str:
        return f"{self.table_prefix}{name}"

    @property
    def event_slugs(self) -> tuple[str, ...]:
        return tuple(e.slug for e in self.event_types)

    @property
    def modality_slugs(self) -> tuple[str, ...]:
        return tuple(m.slug for m in self.modalities)

    @property
    def category_slugs(self) -> tuple[str, ...]:
        return tuple(c.slug for c in self.categories)

    def category(self, slug: str) -> GoalCategory | None:
        return next((c for c in self.categories if c.slug == slug), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_types": [{"slug": e.slug, "label": e.label} for e in self.event_types],
            "modalities": [{"slug": m.slug, "label": m.label} for m in self.modalities],
            "categories": [{"slug": c.slug, "label": c.label, "source": c.source} for c in self.categories],
        }


__all__ = ["EventType", "GoalCategory", "MetasConfig", "Modality", "RuleSeed"]
