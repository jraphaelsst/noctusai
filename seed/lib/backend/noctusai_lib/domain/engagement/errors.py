"""Engagement domain errors.

`EngagementRuleError` is raised only for a **malformed rule
configuration** (a duplicate `PointRule` for the same
`(source, action)`, a non-positive `points` value, a `daily_cap`
that exceeds its own `period_cap`, ...). It is never raised for an
ordinary runtime outcome:

- A duplicate event delivery (same `idempotency_key` seen twice) is a
  `DuplicateEvent` result, not an exception.
- An event whose `(source, action)` has no configured `PointRule` is an
  empty award list, not an exception — not every action earns points
  (KB § 07-GAMIFICATION.md § 3: "no logged-in-today rewards").
"""
from __future__ import annotations


class EngagementRuleError(ValueError):
    """A `PointRule` / `RuleSet` is misconfigured. Raised at construction
    time (fail fast, before any event is evaluated against the bad
    config) — never at evaluation time for a normal event outcome."""


__all__ = ["EngagementRuleError"]
