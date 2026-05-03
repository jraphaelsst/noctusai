"""Primitives — stateless helpers any layer can call.

**Layer contract.** Anything in `primitives/` MUST:
- Be a pure function or dataclass-shaped object.
- Have NO HTTP, NO DB, NO IO beyond stdlib + filesystem reads at module
  import time.
- Have NO knowledge of FastAPI, Supabase, or our domain.
- Be safe to call from any other layer (api, domain, integrations) without
  creating a cycle — this layer imports from nothing in `noctusai_lib.*`.

**Why a layer.** Without this boundary, every absorption (parsing helpers,
date utilities, format helpers) would land at the top level of
`noctusai_lib/`, growing a flat namespace where you can't tell a "platform
primitive" from a "feature module" by looking. With this folder, the rule
is clear: if it doesn't talk to the network or the DB, and it doesn't
know about our domain, it goes here.

**Active occupants:**
- `parsing.py` — `safe_float`, `safe_json_loads`, `format_brl`,
  `parse_iso_or_400`, `parse_iso_or_none`
- `responses.py` — `success_response`, `error_response`, etc.
- `exceptions.py` — base exception types
- `_correlation.py` — `ContextVar` for correlation IDs (used by
  `logging_config.py` at the seed-lib root and by `api/middleware.py`)
- `roles.py` — pure role constants + predicates (`ORG_ROLES`,
  `ADMIN_ROLES`, `DEV_ROLES`, `is_dev_or_owner`, etc.). Imported by
  `domain/page_status.py` and `api/` consumers; the placement here
  honors the dep-direction rule.
- `timeutil.py` — `now_utc()`, `today_utc()`, `current_month_ref()`,
  `current_day_ref()`, `frozen_time(dt)` context manager. Single
  source of truth for "current wallclock" / "current period
  reference" so production + tests agree across UTC midnight.

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
