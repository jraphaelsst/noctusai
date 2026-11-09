"""Deterministic in-memory output guard for consumer tests: returns the scripted detail per rule, records the calls."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .types import GENERIC_RULES, GuardContext, GuardFinding, GuardRule

__all__ = ["FakeOutputGuard"]


class FakeOutputGuard:
    def __init__(self, findings: Mapping[str, dict[str, Any]] | None = None) -> None:
        self._findings = dict(findings or {})
        self.calls: list[tuple[str, str]] = []

    def evaluate(
        self, rule: str, reply: str, ctx: GuardContext, params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if rule not in GENERIC_RULES:
            raise KeyError(f"unknown guardrail rule {rule!r}")
        self.calls.append((rule, reply))
        return self._findings.get(rule)

    def check(self, reply: str, ctx: GuardContext, rules: Mapping[str, GuardRule]) -> list[GuardFinding]:
        out: list[GuardFinding] = []
        for name in GENERIC_RULES:
            cfg = rules.get(name)
            if cfg is None:
                continue
            detail = self.evaluate(name, reply, ctx, cfg.params)
            if detail is not None:
                out.append(GuardFinding(name, cfg.policy, detail))
        return out
