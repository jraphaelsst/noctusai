# Outbound rate limiting — pace every external call, back off on throttle

**Rule.** Every outbound request to a third-party API routes through the shared
limiter `noctusai_lib.integrations.rate_limit` before it fires. Bursting gets us
throttled or banned — it hit the Meta Marketing API (the 12-month ads backfill
tripped Meta's user-level limit mid-run, 2026-07-23) and the Cloudflare MCP
before it. This is a `no-quick-fixes` / root-level concern: one primitive, every
integration adopts it — never a per-integration reinvented backoff.

## The two protections (both required)

1. **Pacing (token bucket).** `acquire(bucket)` / `await acquire_async(bucket)`
   blocks/awaits just long enough to hold the sustained request rate below a
   safe ceiling, allowing a small burst. Keyed per provider so a slow provider
   doesn't throttle a fast one. This keeps us from *hitting* the limit.
2. **Backoff-on-signal (`retry_with_backoff` / `_async`).** When the provider
   still says "slow down" (HTTP 429 or a provider-specific rate-limit code),
   honor `Retry-After` if given, else exponential backoff with full jitter,
   bounded by `max_retries`. This is what recovers *gracefully* instead of
   hammering a throttled endpoint (which extends the ban).

Rate-limit errors mean the request was **rejected, not processed**, so retrying
one is safe even for writes. Timeouts (which might have landed) are NOT
rate-limit signals and are never auto-retried by this layer.

## This is NOT the inbound limiter

`noctusai_lib.api.rate_limit_policies` (slowapi) protects OUR endpoints —
requests coming IN. This module paces requests going OUT to third parties.
Different direction, different concern; don't conflate them.

## Adoption — sync vs async

- **Sync httpx** (e.g. Meta `_meta_api._graph_request`): `rate_limit.acquire("<bucket>")`
  immediately before the call, and wrap the public request functions with a
  backoff-retry (`retry_with_backoff`, `is_retryable=<is-this-a-rate-limit?>`).
  See the Meta wiring: pacing at the single `_graph_request` chokepoint +
  `@_meta_paced_retry` on `graph_get/paged/post/delete`.
- **Async httpx** (e.g. Mailchimp `_request`): `await rate_limit.acquire_async("<bucket>")`
  before the call (never the blocking `acquire`, which would stall the event
  loop). Backoff via `retry_with_backoff_async`.
- **Per-method clients** (WAHA) — pace each call site, or refactor to one
  `_request` helper first.
- **Non-httpx SDKs** (YouTube googleapiclient) — `acquire` before each
  `.execute()`. Note a request-rate limiter does NOT model a hard daily QUOTA.

## Config

Per-bucket `rate_per_sec` / `burst` / `max_retries` default conservatively and
are overridable via env (`NOC_RL_<BUCKET>_RPS`, `NOC_RL_<BUCKET>_BURST`) — tune a
provider without a code change. Unknown buckets get the global default.

## Testing

All clocks/sleeps are injectable. The seed test conftest installs a
`VirtualClock` as the default (autouse) so pacing/backoff LOGIC runs for real
(tokens refill, retries count, `acquire` is genuinely called) but no test
wall-clock-waits — without it the real-adapter Graph tests take ~50s instead of
~2s. Unit tests inject their own `VirtualClock` for precise assertions.

## Adoption status (2026-07-24)

- ✅ **Meta** (sync) — fully wired + tested.
- ✅ **Mailchimp** (async) — wired (`acquire_async` at `_request`).
- ⏳ **Vista / WAHA / YouTube / Google** — `NOC-REMEDIATE[rate-limit]` markers at
  their chokepoints (sweep: `grep -rn "NOC-REMEDIATE\[rate-limit\]"`). Deferred
  because their call volume is low today; adopt before any of them grows a sync
  loop. Named destination, not a silent skip.

## Composes with

- `KB § PATTERNS/common/remediation-markers.md` — the un-wired adopters carry markers.
- `KB § CONTEXT/01-PHILOSOPHY.md` — no-silent-errors: backoff never swallows a non-retryable error; giving up after `max_retries` re-raises.
- `KB § INTEGRATIONS/meta.md` — the reference wiring.
