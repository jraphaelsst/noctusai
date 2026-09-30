## Summary

Delivered the seed (S2) slice of the audit-trail feature (owner directive 2026-09-23, "record history of actions for everything") on `feat/seed-audit-middleware` (base `f7ee4b24378e7af3fa0a6bf40d195c008feb18a4`, 6 commits, HEAD `77381f98db51a2701eb7c377be9b2946858dda72`).

## What shipped

- `noctusai_lib.api.audit` — new seed IO module (Protocol+Fake+Real+factory, bundled in `sink.py` mirroring `noctusai_lib.api.auth.session.audit`'s precedent):
  - `AuditMiddleware` (pure ASGI) — records POST/PUT/PATCH/DELETE requests: route template, path params, status, correlation_id, duration, actor, actor_kind, client_hint.
  - `AuditSink` Protocol, `FakeAuditSink`, `RealAuditSink` (bounded `asyncio.Queue`, flushes every 2s or 50 rows, drains on shutdown, never caches `.schema()`).
  - `detect.py` — pure `detect_actor_kind()` / `client_hint_from_ua()`.
  - `log_overflow_or_failure()` — ERROR + named counter + stdout JSON fallback, reused by `action_log.py`.
- Wired behind `settings.audit_trail_enabled` (default `False`, new `ProductSettings` field) — mounted in `configure_app()` next to `RequestLoggingMiddleware` (both nested inside `CorrelationIdMiddleware` — load-bearing for correlation-id capture). `create_product_app()` builds the sink and drains it on lifespan shutdown.
- `request.state.audit_actor` propagation in `make_get_current_user_org` (auth/__init__.py) and `ProductDependencies.get_current_user` (dependencies.py) — the only channel the ASGI middleware has to learn the caller.
- `card_hub.gatherers.gather_audit` — default `"historico"` timeline kind, wired into `CardHubConfig.__post_init__` only when `audit_trail_enabled` + `get_core_client` are both set.
- `action_log.log_action` — removed its silent `except Exception as e: logger.warning(...)`; now routes through `log_overflow_or_failure`. Destination table unchanged (still the caller-specified product table, e.g. ERP's live `user_actions_log`) — deliberate, see design note below.
- FE `api.ts` — sends `X-Noctus-Client: web` / `agent:webdriver`.

## Design decisions worth flagging to the architect

1. **`public.audit_logs` already exists** (core migrations 001/002) with a DIFFERENT shape (`action`/`resource_type`/`resource_id`/`details`/`ip_address`/`user_agent`/`user_id`/`org_id`/`created_at` — core's own admin-action log, e.g. subscription/license/api_key events). Rather than inventing a second table or silently colliding, `RealAuditSink` writes through the EXISTING columns (`action=method`, `resource_type=product`, everything else inside `details` JSONB). This means the sink is functionally correct TODAY without waiting on the "core migration S1" the brief named — I read S1 as an *additive* follow-up (dedicated columns + indexes for `gather_audit`'s JSONB-containment query, which currently has no index and is capped at 200 rows) rather than a hard blocker. Please confirm this reading, or redirect.
2. **`action_log.log_action` was NOT redirected to `public.audit_logs`.** Its callers (ERP's `user_actions_log`, Therapy's `action_log`) are LIVE tables real routers/UI read today (grepped: dozens of call sites across ERP alone). Redirecting would have been a silent regression. I kept the destination unchanged and only fixed the silent-swallow, reusing the audit module's shared failure-handling helper — a narrower reading of "thin adapter over AuditSink" than a literal dual-write. Flagging for confirmation.
3. **`gather_audit` does not filter by product** (only `org_id` + entity-id JSONB containment) — `AuditMiddleware`'s `product` field is the human-readable name (`create_product_app(name=...)`), which `CardHubConfig` has no access to; relying on UUID-uniqueness instead. Noted in the gatherer's docstring.

## Bug found + fixed in shared seed auth deps (real production risk, not audit-trail-specific)

Adding `request: Request` to `make_get_current_user_org` and `ProductDependencies.get_current_user` (to receive the actor stash) initially used `Optional[Request] = None`. This BROKE EVERY ROUTE FLEET-WIDE that uses either as a `Depends(...)` sub-dependency — `FastAPIError: Invalid args for response field!` at collection time, because FastAPI's special "inject the live Request" detection matches only the bare `Request` class annotation (`lenient_issubclass`), not `Optional[Request]` (a `Union`). Fixed to `request: Request = None` (bare annotation, `None` default) — confirmed via a minimal repro AND the full fleet pytest sweep (see Tests below). This is a general FastAPI footgun worth a KB note / keeper (see scoped-improvement below) — any seed dependency needing an optional `Request` injection must use this exact shape.

## Tests

- `seed/lib/backend/tests/api/audit/` (detect, sink, middleware) — new, 3 files.
- `seed/lib/backend/tests/domain/test_action_log.py` — new.
- `seed/lib/backend/tests/domain/card_hub/test_gather_audit.py` — new.
- `seed/framework/backend/tests/test_audit_trail_wiring.py` — new (pilot proof: app construction + full request cycle, flag off/on/absent).
- `seed/lib/frontend/src/api.test.ts` — existing, still green (29/29).

Gates run (all via `noctus.dev.pytest`/direct pytest with correct worktree PYTHONPATH):
- Fleet sweep (all active products): **9891 passed, 0 failed**.
- `erp-imobiliario` (inactive, run separately since asleep): **2235 passed, 0 failed** (1 signature-pinning test updated for the new `request` param).
- `seed/lib/backend` full suite: **5914 passed, 1 pre-existing unrelated Redis-flake failure** (`test_bus.py::test_publish_then_subscribe_roundtrip[redis]` — no Redis in this env).
- `seed/framework/backend` full suite: **260 passed**.
- `seed/lib/frontend` vitest: **29 passed**.
- `social-wiring` vite build: succeeds.

## Files touched

`seed/lib/backend/noctusai_lib/api/audit/{__init__,types,detect,sink,middleware}.py`, `api/app_factory.py`, `api/auth/__init__.py`, `domain/action_log.py`, `domain/card_hub/{config,gatherers}.py`; `seed/framework/backend/noctusai_seed/{app,config,dependencies}.py`; `seed/lib/frontend/src/api.ts`; `products/erp-imobiliario/backend/tests/test_dependencies_factory.py` (signature-pin update, caused by this change); plus the 6 new test files listed above.
