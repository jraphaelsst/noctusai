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
- `timeutil.py` — `now_utc()`, `now_utc_iso()`, `today_utc()`,
  `current_month_ref()`, `current_day_ref()`, `frozen_time(dt)`
  context manager. Single source of truth for "current wallclock" /
  "current period reference" so production + tests agree across
  UTC midnight. `now_utc_iso()` is the canonical ISO-string form,
  lifted from N=4 byte-identical product-local `_now_iso()` helpers.
- `phone.py` — `normalize_phone()`, `format_phone()`, `phone_digits()`,
  `is_valid_phone()`. THE canonical phone format for the platform
  (E.164, `+5511994573387` — the shape Meta Lead-Ads already delivers
  and one `+` away from the WhatsApp chat id). Lifted from N=4
  disagreeing product-local helpers that stored, displayed, imported
  and received the same number in four non-comparable spellings.
  `format_phone` is the single display seam: change it here and every
  product's UI follows. Mirrored 1:1 by `@noctusai/lib/phone`.
- `tasks.py` — `schedule_coro(coro, *, logger=None, name=None)` +
  `NoRunningLoopError`. Canonical fire-and-forget helper that
  schedules a coroutine on the running loop and logs exceptions
  via `add_done_callback`. Lifted from N=3 product callsites
  (core/billing, erp-imobiliario/certidoes, erp-imobiliario/jobs)
  that each hand-rolled the same shape with no exception logging.

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
