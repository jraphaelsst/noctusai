"""`ApprovalsConfig` -- everything that differs between two approvals hosts (just the schema and the table prefix)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class ApprovalsConfig:
    """schema: the product's Postgres schema. table_prefix: prefix of the organ table (`apr_events`) and RPC (`apr_record`)."""

    schema: str
    table_prefix: str = "apr_"

    def __post_init__(self) -> None:
        for label, value in (("schema", self.schema), ("table_prefix", self.table_prefix)):
            if not _IDENT.match(value or ""):
                raise ValueError(f"ApprovalsConfig.{label} must be a bare lowercase identifier, got {value!r}")

    def table(self, name: str) -> str:
        """Physical name of the organ table or RPC `name` (`events` -> `apr_events`, `record` -> `apr_record`)."""
        return f"{self.table_prefix}{name}"


__all__ = ["ApprovalsConfig"]
