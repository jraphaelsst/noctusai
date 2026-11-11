"""`ActivitiesConfig` -- everything that differs between two activities hosts (schema, prefix, default types)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from .types import GENERIC_ACTIVITY_TYPES, ActivityTypeSpec

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class ActivitiesConfig:
    """One activities host's knobs.

    Attributes:
        schema: the product's Postgres schema.
        table_prefix: prefix of every organ table (`act_` => `act_activities`) and RPC.
        default_types: the market's activity types, seeded lazily per org (`CrmPreset.activity_types`); the org edits
            them afterwards. Empty => `GENERIC_ACTIVITY_TYPES`.
        org_id_expr: SQL expression the authenticated own-org policy compares `org_id` to.
            Unset => `public.current_org_id_for('<schema>')`.
    """

    schema: str
    table_prefix: str = "act_"
    default_types: Sequence[ActivityTypeSpec] = ()
    org_id_expr: Optional[str] = None

    def __post_init__(self) -> None:
        for label, value in (("schema", self.schema), ("table_prefix", self.table_prefix)):
            if not _IDENT.match(value or ""):
                raise ValueError(f"ActivitiesConfig.{label} must be a bare lowercase identifier, got {value!r}")
        types = tuple(self.default_types) or GENERIC_ACTIVITY_TYPES
        slugs = [t.slug for t in types]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"ActivitiesConfig: repeated default type slug in {slugs}")
        object.__setattr__(self, "default_types", types)
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("ActivitiesConfig.org_id_expr must be a non-empty SQL expression (or unset)")

    @classmethod
    def for_preset(cls, schema: str, preset: Any, **kw: Any) -> "ActivitiesConfig":
        """The config of a market: its `CrmPreset.activity_types` become the default types."""
        return cls(schema=schema, default_types=tuple(getattr(preset, "activity_types", ()) or ()), **kw)

    def table(self, name: str) -> str:
        return f"{self.table_prefix}{name}"

    def rpc(self, name: str) -> str:
        return f"{self.table_prefix}{name}"


@dataclass(frozen=True)
class ActivitiesContext:
    """What every handler needs, resolved by the host's `resolve_context`.

    `is_member(user_id) -> bool` answers "is this user an ACTIVE member of the caller's org" (the assignee check);
    the host wires it over the existing membership helper, so the organ never reaches for core on its own.
    """

    db: Any
    org_id: str
    user_id: str
    is_admin: bool = False
    is_member: Optional[Callable[[str], bool]] = None


__all__ = ["ActivitiesConfig", "ActivitiesContext"]
