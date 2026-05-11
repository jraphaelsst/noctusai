"""SQL-authoring convenience layer — `prelude` + `updated_at_trigger` + `service_role_bypass`.

Thin authoring-ergonomic wrappers over the canonical, single-source-of-truth
helpers in :mod:`noctusai_lib.domain.sql_templates`. The audit on 2026-05-09
(`noctus.dev.scan_migration_patterns`) flagged two patterns recurring in
EVERY product migration:

- ``SET search_path`` — 100 instances across 9/9 products
- ``updated_at`` BEFORE-UPDATE trigger pair — 28 instances across 5 products

A third pattern was lifted from
``projects/keeper-trio-platform-triage/phase-0-triage.md`` (2026-05-11):

- ``CREATE POLICY "service_role_bypass" ... FOR ALL TO service_role`` —
  192 missing instances across core / erp / mailing / pf. Therapy's
  ``001_therapy_platform.sql:846+`` is the canonical reference adopter.

This module is the seed surface that absorbs those patterns *for newly
authored migrations*. Existing migrations stay verbatim per the
"MCP migrations mirror the file" rule — they are authoritative replay
logs and rewriting them carries high churn risk.

Three functions:

- :func:`prelude` — schema-lock + comment block at the top of a fresh
  migration, explaining the why (RLS isolation, cross-product safety).
  Idempotent (no DDL — session-level setting).
- :func:`updated_at_trigger` — emits the function declaration AND a
  BEFORE-UPDATE trigger for one table in one call. Idempotent
  (CREATE OR REPLACE on both function and trigger).
- :func:`service_role_bypass` — emits the canonical
  ``service_role_bypass`` policy for one table. The keeper detector
  looks for the literal policy NAME, so callers MUST NOT rename.

Delegation rule: ALL functions delegate to
:mod:`noctusai_lib.domain.sql_templates` so the canonical strings have
a single source of truth. Drift would surface as a test failure here AND
in ``test_sql_templates.py`` simultaneously.
"""
from __future__ import annotations

from .prelude import prelude
from .service_role_bypass import service_role_bypass
from .triggers import updated_at_function, updated_at_trigger

__all__ = [
    "prelude",
    "service_role_bypass",
    "updated_at_function",
    "updated_at_trigger",
]
