# Audit trail — request history for every mutating call

> Absorbed 2026-09-30 from `projects/audit-trail/proposals/engineer-seed-20260923-*`
> (S2 delivery report, feat/seed-audit-middleware) + follow-ups `a152609dc`,
> `33cffbad0`. Owner directive 2026-09-23: "record history of actions for
> everything". Self-contained.

## Shape

- **Module:** `noctusai_lib.api.audit` — seed IO, Protocol + Fake + Real + factory
  (`AuditSink` / `FakeAuditSink` / `RealAuditSink` / `make_audit_sink`), plus the
  pure-ASGI `AuditMiddleware` and `detect.py` (`detect_actor_kind`, `client_hint_from_ua`).
- **What is recorded:** POST/PUT/PATCH/DELETE — `product_slug`, method, route
  template, path params, status, correlation_id, duration, actor, actor_kind,
  client_hint (FE `api.ts` sends `X-Noctus-Client: web` / `agent:webdriver`).
- **Opt-in:** `ProductSettings.audit_trail_enabled` (default `False`). First adopter:
  social-wiring.
- **Destination:** core `public.audit_logs`, extended by migration 053
  (`audit_trail_expansion`) with dedicated columns and index
  `idx_audit_logs_product_resource (product_slug, resource_type, resource_id)`.
  The original columns (`action`/`resource_type`/`resource_id`/`user_id`/`org_id`)
  are still populated. `resource_id` = the FIRST path parameter (card_hub's
  `entity_path()` convention). A last-parameter rule would point every nested
  sub-resource route at its own id and miss it in a per-entity query.
- **Read side:** `card_hub.gatherers.gather_audit`, the `"historico"` timeline
  kind. It is wired only when `audit_trail_enabled` + `get_core_client` +
  `product_slug` are all set.

## Decisions that are not obvious from the code

1. **Middleware order is load-bearing.** `AuditMiddleware` sits inside
   `CorrelationIdMiddleware` (next to `RequestLoggingMiddleware`). Outside it, the
   correlation id is not yet bound.
2. **The actor reaches ASGI via `request.state.audit_actor`**, stashed by
   `make_get_current_user_org` and `ProductDependencies.get_current_user`. Pure
   middleware has no other way to learn the caller.
3. **`action_log.log_action` was NOT redirected to `audit_logs`.** Its tables
   (ERP `user_actions_log`, Therapy `action_log`) are live and read by routers and
   UI, so redirecting them would be a silent regression. It keeps its destination
   and only lost its silent `except` (it now goes through
   `log_overflow_or_failure`: ERROR + named counter + stdout JSON fallback).
4. **`RealAuditSink` is bounded and asynchronous.** It uses an `asyncio.Queue`,
   flushes every 2 s or 50 rows, drains on lifespan shutdown, and never caches
   `.schema()`.
5. **Resolve the core client lazily.** `create_product_app` passes
   `lambda: db.get_core_client()`, never the bound method. A bound method captured
   at import time outlives every later `mock.patch` of `DatabaseModule`, so a
   flush during a slow test would write to the REAL Supabase from `.env`
   (`33cffbad0`). The same late-binding-lambda convention is already used by
   `make_resolve_platform_role`.

## 🔴 FastAPI footgun — an optional `Request` must be `request: Request = None`

FastAPI injects the live request only when the annotation is the bare `Request`
class (it checks with `lenient_issubclass`). `Optional[Request] = None` is a `Union`,
so FastAPI treats it as a body/response field. Every route that uses that
dependency as a `Depends(...)` sub-dependency then fails at startup with
`FastAPIError: Invalid args for response field!`. When the S2 slice first used
`Optional[Request]`, it broke every route fleet-wide. It was caught by the fleet
pytest sweep before merge.

**Rule:** a seed dependency that wants an optional request injection is declared
`request: Request = None` (bare annotation, `None` default), never
`Optional[Request]` or `Request | None`.

## Related

`KB § PATTERNS/backend/logging-at-except.md` (the no-silent-except convention
`action_log` now follows) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` (the
IO-module shape) · `KB § PATTERNS/backend/llm-tool-audit.md` (tool-call audit,
a separate ledger).
