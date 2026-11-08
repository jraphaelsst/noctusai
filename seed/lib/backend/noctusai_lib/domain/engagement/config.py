"""`EngagementConfig` -- where the engagement organ's tables live (the product's schema, `eng_` prefix)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


@dataclass(frozen=True)
class EngagementConfig:
    schema: str
    table_prefix: str = "eng_"

    def __post_init__(self) -> None:
        if not _IDENT.match(self.schema or ""):
            raise ValueError(f"EngagementConfig.schema {self.schema!r} must be a lower_snake identifier")
        if not _IDENT.match(self.table_prefix or ""):
            raise ValueError(f"EngagementConfig.table_prefix {self.table_prefix!r} must be a lower_snake identifier")

    def table(self, name: str) -> str:
        return f"{self.table_prefix}{name}"


__all__ = ["EngagementConfig"]
