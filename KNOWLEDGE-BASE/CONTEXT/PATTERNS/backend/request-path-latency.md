# Request-path latency — the seed's shared backend path is fast for every product

> Owner: `backend-engineer`. Fixed ONCE in the seed (2026-10-21), inherited by every product — no per-product fix exists or is wanted.

## Why (measured on prod, orbity, VPS Campinas → Supabase sa-east-1, ~25 ms warm / ~50 ms cold per network call)

`GET /api/crm/leads/{id}/activities` took 564 ms alone; three parallel requests finished as a staircase 985 / 1,524 / 2,081 ms. Four root causes, all in the shared path:

1. **Sync I/O on the event loop.** supabase-py is synchronous; the seed's `async def` auth dependencies and most `async def` handlers called it directly, parking the single uvicorn loop for every round-trip. Concurrent requests serialize.
2. **A duplicate `get_user` per request.** `make_supabase_client(access_token=…)` called `client.auth.set_session(token, "")`, which asks Supabase Auth `get_user` AGAIN (the request's own token validation already did) and starts a gotrue refresh `Timer` thread per client.
3. **A TLS handshake per request.** Every client built its own httpx pools + TLS context; `get_core_client()` (hit by org resolution and the licence gate on every request) was rebuilt each call.
4. **The same token validated N times a second** (the SPA fires several requests at once).

## What the seed does now

| Fix | Where | Behaviour |
|---|---|---|
| Off the event loop | `noctusai_lib/api/auth/_blocking.py::run_blocking` (`anyio.to_thread.run_sync`) | Token validation, `noctus_users` membership, licence gate and `get_user_role_fn` run in a worker thread in `make_get_current_user*`, `make_get_current_user_org`, `make_require_role` and `ProductDependencies.get_current_user*`. Deps stay `async def` (they `await` siblings and seed routers call them imperatively), so they hop instead of becoming `def`. Same 40-thread anyio limiter Starlette uses for sync endpoints; contextvars are copied; exceptions propagate unchanged. |
| No duplicate `get_user` | `noctusai_lib/integrations/database.py::make_supabase_client` | The user's JWT is put straight into the `Authorization` header PostgREST/Storage are built from. RLS reads that header, so it sees the same user; no gotrue session, no refresh Timer (`auto_refresh_token=False`, `persist_session=False`). `client.auth` carries no session on a user client — token validation uses the service-role client. |
| One shared pool | `noctusai_lib/integrations/http_pool.py` | Every Supabase client's PostgREST / Storage / Auth session is a thin `httpx.Client` over ONE process-wide `HTTPTransport` (HTTP/1.1, keep-alive 20 s, 200/50 limits). Kill switch `NOCTUS_HTTP_POOL=0`. |
| Cached process clients | `noctusai_seed/database.py` | `get_admin_client()` AND `get_core_client()` are built once per process (double-checked lock) and wrapped in `_SchemaPinnedAdminClient`. `get_client(token)` stays per call (it carries one user's JWT). |
| Verified-token cache | `noctusai_lib/api/auth/token_cache.py` | Positive cache of the verified user, **30 s** (`Settings.auth_token_cache_ttl_seconds`, `0` disables). |

### Token cache contract (owner-approved 2026-10-21)

- **A revoked session can keep working for up to 30 s** on a process that already cached it — the accepted trade-off. The user's own logout on core evicts immediately (`discard_token_everywhere`); a revocation elsewhere (password change, admin sign-out) waits out the TTL.
- Key = `sha256(token)`, never the raw token; only the verified user payload is stored (deep-copied in and out).
- **Positive results only** — a 401, a no-user answer or a 503 outage is never cached.
- Never served past the token's own `exp` (read from the JWT after Supabase accepted it; no readable `exp` ⇒ not cached). LRU, 2 048 entries.
- One cache per validator (`make_get_current_user_ungated()` call / `ProductDependencies`), so apps and tests never share one.

### Thread-safety (why sharing is sound)

- `httpx.HTTPTransport` → `httpcore.ConnectionPool`: lock-protected bookkeeping, one in-flight request per HTTP/1.1 connection. The documented outage (`database.force_postgrest_http1`) was HTTP/2 stream multiplexing on a shared connection; the pool is `http2=False`.
- Per-client state (headers, cookie jar) lives on the per-client wrapper, not the transport. A pooled client's `close()` is a no-op for the transport, so closing one cannot tear down everyone's sockets.
- Residual (pre-existing, unchanged): `_SchemaPinnedAdminClient` re-pins a shared client's schema by mutating it; two threads doing a deliberate cross-schema `.schema(other)` and a bare `.table()` at the same instant can still interleave. Process-wide fix = a client per schema (destination: `NOC-REMEDIATE`-style follow-up in `admin-client-schema-pinning.md`).
- Never run `client.auth.sign_in_*` / `verify_otp` on a cached client — it establishes a session and turns the shared service-role client into a user client (the 2026-05-23 core outage). Use a throwaway `create_client`, as `auth_router` does.

## Handlers: the part a product still owns

The seed cannot make a product's own handlers non-blocking. Rule: an `async def` route handler that calls the sync client (directly or through a service) and `await`s nothing is a plain `def` — FastAPI threadpools it. One that must stay async wraps the call in `await anyio.to_thread.run_sync(...)`.

- **Keeper `check_async_handler_sync_db`** (`--check-async-handler-sync-db`, pre-commit, `review`): ratchet baseline `mcp/noctusai/tests/async_handler_sync_db_baseline.json`, per file, may only go down; `--lower-async-handler-sync-db-baseline` follows a conversion. Escape: `# noc-allow: sync-in-async — why` on the `async def` line. It sees DIRECT `.execute()` / `.auth.*` / `.storage` calls only, so the count is a lower bound (a handler reaching the DB via `svc.list(...)` is invisible to it).
- **Codemod `noctus.dev.async_handlers_to_def`** (`--async-handlers-to-def PRODUCT [--apply]`, libcst): converts every awaitless route handler (no `await`/`async for|with`/`yield`/`asyncio|anyio|trio`/`global`, never `await`ed elsewhere in the product) and reports the rest with a reason. DRY-RUN by default. After applying: review module-level shared state, run the product's backend tests, then lower the baseline. Piloted on orbity; the other products are the follow-up sweep.

## Round trips: count them, run the independent ones together (2026-10-22)

A 600 ms shell endpoint is ~10 sequential PostgREST calls (~25 ms warm each, VPS -> Supabase) or a blocked loop. Count `.table()` calls first (`_CountingCore` in `test_shell_endpoint_latency.py`). Independent reads inside one sync call run together via `noctusai_lib.api.auth._blocking.run_parallel` (own pool, all thunks finish, first exception by order re-raised): the effective-org member resolve reads memberships / blocks / live selection concurrently (still fresh every request -- revocation by recheck is untouched), and `/api/me/access` runs resolve, platform-staff check and manageable memberships concurrently, then ONE `organizations` name lookup for every org it mentions (was home + effective + eligible + manageable = 4+ separate lookups; ~11 sequential calls -> 4 levels). `/api/notificacoes*` and the org-choice handlers wrap their sync client calls in `run_blocking`. Core-served `/api/me/consents` and `/api/admin/llm-spend/{org}` live in `products/core`, not the seed.

## Budget + gate: fast responses are mandatory (owner, 2026-10-22)

Server-side p95 budgets live in ONE file, `deploy/fleet/latency-budgets.json` (shell/me **150 ms**, reads **300 ms**, writes **500 ms**; per-route `overrides` must carry a `reason`). Floor reasoning: ~25-50 ms per PostgREST round trip, so a 300 ms read is already ~6 sequential calls — count round trips, do not guess.

- **Mechanism (by construction).** `RequestTimingMiddleware` (`noctusai_lib/api/request_timing.py`, registered in `configure_app` for every product) adds `Server-Timing: app;dur=<ms>` and logs one `req_timing method= route= status= dur_ms=` line per request. The route is the TEMPLATE (`/x/{id}`), never the raw path — no ids/PII in logs; unmatched requests log `<unmatched>`. Duration is to first byte.
- **Gate.** `noctus.dev.latency_report product=<slug>` (`--latency-report`) reads recent container logs through the VPS log plumbing and reports p50/p95/count per route vs budget: `ok | over_budget | inconclusive`. No `req_timing` data (old image, quiet product, short window) is `inconclusive`, never `ok`; routes under `min_samples` cannot make a verdict ok. `/api/health` is ignored. Run it after every `deploy_image` (skill `noc-ship` step 6b).
- **Procedure.** Skill `noc-fast-responses`: budget, handlers rule above, count round trips before changing anything, cache-writes for the perceived half.
- **Adding a budget exception** = an `overrides` entry with method, route, `p95_ms` and a `reason`; "it is slow today" is not a reason.

## Measuring

Do not trust a green unit run alone: time one authenticated endpoint with 3 concurrent requests before/after (`serial` = sum, `parallel` ≈ max). The tests pin the mechanism (`test_token_cache.py`, `test_database_pooling.py` — incl. a real local keep-alive server — and `test_request_path_latency.py`).

Cross-links: skill `noc-fast-responses` · `mutation-cache-writes.md` (the perceived-latency half) · `admin-client-schema-pinning.md` · `postgrest-row-cap.md` · `tenancy-license-gate.md`.
