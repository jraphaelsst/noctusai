"""`AssignmentConfig` -- everything that differs between two assignment hosts.

The organ owns WHO may own a subject (teams, members, strategies, capacity, out-of-office) and records every
assignment as an event. It does not own the subject: a lead / card / ticket lives in the host's own table. When the host
names that table (`card_table` + `responsavel_field`, typically `AssignmentConfig.for_funnel(...)`), the assign RPC writes
the chosen owner into that column in the SAME transaction as the assignment row and its event, so the funnel's
`responsavel_field` can never disagree with the organ's record. A host that keeps ownership elsewhere leaves
`card_table` unset and reads `GET /api/assignment/assignments/...` instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class AssignmentConfig:
    """One assignment host's knobs.

    Attributes:
        schema: the product's Postgres schema.
        table_prefix: prefix of every organ table (`asg_` => `asg_teams`) and RPC (`asg_assign`).
        subject_kind: the `subject_kind` the card projection applies to (a host may assign several kinds of subject;
            only this one is projected onto `card_table`).
        card_table: the host table holding the subject (a funnel's card table), or None to project nothing.
        responsavel_field: the column of `card_table` that holds the owner (`FunnelConfig.responsavel_field`).
        card_has_org_id: False for a platform-tenancy card table that has no `org_id` column.
        org_id_expr: SQL expression the authenticated own-org policies compare `org_id` to. Unset =>
            `public.current_org_id_for('<schema>')`.
    """

    schema: str
    table_prefix: str = "asg_"
    subject_kind: str = "card"
    card_table: Optional[str] = None
    responsavel_field: str = "responsavel_id"
    card_has_org_id: bool = True
    org_id_expr: Optional[str] = None

    def __post_init__(self) -> None:
        for label, value in (("schema", self.schema), ("table_prefix", self.table_prefix), ("responsavel_field", self.responsavel_field)):
            if not _IDENT.match(value or ""):
                raise ValueError(f"AssignmentConfig.{label} must be a bare lowercase identifier, got {value!r}")
        if self.card_table is not None and not _IDENT.match(self.card_table):
            raise ValueError(f"AssignmentConfig.card_table must be a bare lowercase identifier, got {self.card_table!r}")
        if not re.match(r"^[a-z][a-z0-9_]{0,39}$", self.subject_kind or ""):
            raise ValueError(f"AssignmentConfig.subject_kind must be a lowercase slug, got {self.subject_kind!r}")
        if self.org_id_expr is None:
            object.__setattr__(self, "org_id_expr", f"public.current_org_id_for('{self.schema}')")
        elif not self.org_id_expr.strip():
            raise ValueError("AssignmentConfig.org_id_expr must be a non-empty SQL expression (or unset)")

    @classmethod
    def for_funnel(cls, schema: str, funnel: Any, **kwargs: Any) -> "AssignmentConfig":
        """Bind the organ to a `FunnelConfig`: its card table and its `responsavel_field` (the column this organ writes).

        A platform-tenancy funnel has no `org_id` on its card table (`tenancy == "platform"`)."""
        return cls(
            schema=schema,
            card_table=funnel.pipeline.card_table,
            responsavel_field=funnel.responsavel_field,
            card_has_org_id=getattr(funnel, "tenancy", "org") != "platform",
            **kwargs,
        )

    def table(self, name: str) -> str:
        """The physical name of the organ table or RPC `name` (`teams` -> `asg_teams`, `assign` -> `asg_assign`)."""
        return f"{self.table_prefix}{name}"


__all__ = ["AssignmentConfig"]
