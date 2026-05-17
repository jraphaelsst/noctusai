# Chatbot operational readiness — production hardening pattern

> Baseline production-hardening checklist for any LLM-driven chatbot
> product that talks to external write APIs (Google Calendar, WAHA,
> Twilio, Slack, …). Pairs with `KB § PATTERNS/llm-bot-security.md`
> (defensive trio against prompt-injection / arg coercion / flooding)
> and `KB § PATTERNS/llm-tool-audit.md` (the observation layer).
>
> Security keeps bad outcomes from happening. Audit captures what
> happened. **This pattern keeps the bot operationally healthy** —
> survives transient failures, emits structured signal, ships safely.
>
> **Folded from sibling repo** `whatsapp-google-scheduling/`'s
> `production-hardening` + `operational-dashboards` planning artifacts
> (preserved here so the pattern survives the sibling's deletion).
>
> First adopter: `imobi-scheduling`, absorbed into
> `products/social-wiring/app/modules/scheduling/` on 2026-05-16
> (`social-wiring-absorption` Wave 4 — the imobi-scheduling product was
> retired; the pattern is durable, the adopter path moved). Adoption-ready:
> any chatbot with external writes — therapy bot, social-wiring email
> dispatcher, PF coach bot.

---

## 1. The six pillars

| # | Pillar              | What "ready" looks like                          | Default destination                        |
|---|---------------------|--------------------------------------------------|--------------------------------------------|
| 1 | **Retries**         | Exponential backoff on transient writes           | Product-side `app/services/retry.py` (lift to seed at N=2) |
| 2 | **Structured logs** | JSON output; correlation IDs; level discipline    | `noctusai_lib.logging_config.configure_logging` (auto-wired by seed) |
| 3 | **Health check**    | `GET /api/health` returns 200 + lifespan state    | `standard_routers=["health"]` (seed)        |
| 4 | **Deployment doc**  | Compose vs k8s decision + env checklist + secrets | Product `DEPLOYMENT.md`                     |
| 5 | **Backup procedure**| Restore path documented; critical tables listed   | Supabase managed daily backups + manual `pg_dump` recipe |
| 6 | **Metrics sink**    | Seam wired at call sites; default `NoopCounter`   | Product `app/services/metrics.py` (lift to platform-metrics project at N=2) |

A chatbot product reaching its production-hardening phase walks this
checklist top-to-bottom. Each pillar is independently verifiable + has a
default destination — silent skipping is forbidden per the
no-silent-errors rule.

---

## 2. Pillar 1 — Retries on transient external writes

External APIs fail transiently. Calendar 503s. WAHA TCP hiccups. SMS
gateway rate limits. Without retry semantics, a single transient hits
the user as a hard failure ("I couldn't book your viewing") when a
0.5-second sleep + one retry would have succeeded.

**The seed ships `noctusai_lib.domain.jobs.retry_policy.RetryPolicy`**
(exponential-backoff configuration + `next_retry_at` math). It's
consumed by the seed's **queue-job worker** which re-enqueues failed
jobs. That shape doesn't help an *in-flight blocking call* — the
calling code can't yield and come back later, it needs the result now.

**Pattern: product-side `retry_call(...)` wrapper composing the seed's
`RetryPolicy`** at the consumer side. First adopter shipped at
`products/imobi-scheduling/backend/app/services/retry.py`, absorbed into
`products/social-wiring/app/modules/scheduling/.../retry.py` on 2026-05-16
(`social-wiring-absorption` Wave 4). Shape:

```python
from noctusai_lib.domain.jobs.retry_policy import RetryPolicy
from typing import Callable, TypeVar

T = TypeVar("T")

def retry_call(
    callable_: Callable[[], T],
    *,
    policy: RetryPolicy,
    transient_exceptions: Iterable[type[BaseException]] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    label: str,
) -> T: ...
```

**Per-API tuning.** Different APIs have different transient-failure
windows. The first-adopter constants (calibrate per backend):

- Calendar: 3 retries, 1s base, 2x, 30s cap. Google Calendar 503 clears
  in 5-10s typically; longer caps prolong inbound webhook response.
- WAHA: 3 retries, 0.5s base, 2x, 10s cap. Local-network deployment;
  failures are TCP transients, recovery is fast or it's a real outage.

**Anti-patterns:**
- Wrapping retries around code paths with their own retry semantics
  (OpenAI SDK already retries). Apply only at outermost consumer
  boundaries.
- Retrying on non-idempotent operations without an idempotency key.
  Calendar `create_event` uses a deterministic `request_id` derived
  from `(appointment_request_id, start_at_iso)` so retries collapse
  server-side (once the seed-side wire-idempotency lands; until then,
  consumer-side DB-pre-check is the guard).
- Wrapping retries inside an async hot path with the default
  `time.sleep` — blocks the event loop. Pattern: `await
  asyncio.to_thread(retry_call, ...)`.

**N=2 destination.** When the second consumer needs the same shape
(social-wiring email-marketing outbound / therapy's calendar invites), absorb to
`noctusai_lib.primitives.retry` (the primitives layer per
`KB § PATTERNS/seed-lib-layout.md`).

---

## 3. Pillar 2 — Structured logs

The seed framework already wires structured logging — `create_product_app(...)`
calls `noctusai_lib.logging_config.configure_logging(...)` during
lifespan startup (see `seed/framework/backend/noctusai_seed/app.py`).
JSON format in production (`debug=False`); plain format in development.

**Verification step** during production-hardening: confirm the product
uses `logging.getLogger(__name__)` not `print(...)` and not
`logging.basicConfig(...)`. The pattern at `KB § PATTERNS/logging.md`
applies in full — no `# silent-ok`, level discipline, correlation IDs
where they help.

**Re-export shortcut.** Each product ships a thin
`app/logging_config.py` that re-exports
`from noctusai_lib.logging_config import *` so product code can
`from app.logging_config import configure_logging` without reaching
into the seed namespace. Useful when a product needs to suppress a
noisy third-party logger or layer a custom formatter.

---

## 4. Pillar 3 — Health-check endpoint

`standard_routers=["health"]` (passed to `create_product_app(...)`)
registers `GET /api/health` returning `200 {"status": "ok"}` when the
app is up. Compose healthcheck wiring:

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:<PORT>/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

Future enhancement candidates (filed when N=2 products need them):

- Lifespan-state reporting (`{"status": "ok", "lifespan": {"calendar": "configured", "conversation": "configured"}}`)
  — helps an operator distinguish "app is up" from "app is up but
  half-wired".
- DB connectivity ping — currently the health route returns 200 even
  if Supabase is unreachable. Bumping to a real ping introduces
  health-flapping risk; defer until an operator surfaces the need.

---

## 5. Pillar 4 — Deployment documentation

Every chatbot product ships a `DEPLOYMENT.md` at the product root with
six sections:

1. **Target** — Compose / k8s decision + rationale.
2. **Ports** — what listens on what (backend / frontend / external WAHA / Redis).
3. **Environment variables** — table: name | purpose | secret? | default.
4. **Secrets handling** — Docker secrets / mounted `.env.production` / encryption-at-rest notes.
5. **Health check** — endpoint + Compose wiring.
6. **Smoke test** — copy-pasteable `curl` invocations to verify post-deploy.

**Why a standalone file (not just README).** The README is the
project's *what + why*; `DEPLOYMENT.md` is operational. Mixing them
makes the README too long for users who only want to understand the
product. Folded into the README only if the product team prefers it
that way — both shapes are valid.

---

## 6. Pillar 5 — Backup procedure

**Default: Supabase managed daily backups.** Pro+ tier ships
PITR-capable daily snapshots; retention configurable. Restore path
documented in `DEPLOYMENT.md` (Supabase Dashboard → Database → Backups
→ Restore).

**Critical tables** — every chatbot product enumerates the tables
whose loss = re-onboarding the user base:

- Appointment / booking tables (the durable state the bot creates).
- User + linked-identity tables (authorization mapping).
- OAuth credential tables (refresh-token cache; loss → users re-auth).
- Tool-call audit tables (LGPD-relevant; retention should match
  product's data-retention policy).

**Manual disaster-recovery drill.** `pg_dump --schema=<schema>
$DATABASE_URL > <product>-$(date +%F).sql` produces a schema-scoped
snapshot. Restore via `psql $DATABASE_URL`. Run the drill at least
once per release cadence so the recipe stays exercised.

**Conversation memory caveat.** Redis-backed buffers are *ephemeral
by design* (TTL-bound per `CONVERSATION_MEMORY_TTL_SECONDS`). Not part
of the backup contract. Lossy at restart in dev; production keeps
short windows survivable via Redis persistence (AOF / RDB) when
configured.

---

## 7. Pillar 6 — Metrics sink

**v1 ships with a seam, not a backend.** A full metrics implementation
(StatsD / OpenTelemetry / Prometheus) is a platform-wide concern.
Implementing it inside one product either duplicates future seed-layer
work or locks in a wire format that gets changed later.

**Pattern: product-side `app/services/metrics.py`** exposing:

1. A `Counter` Protocol (low-cardinality `increment(metric, *, value, tags)`).
2. `NoopCounter` — default; logs at DEBUG so events are observable via
   the structured-log stream (`metric.increment name=... value=... tags=...`).
3. Semantic helpers — `record_tool_dispatch(...)`,
   `record_llm_call(...)` — the conversation worker + dispatcher call
   these without knowing the backend.
4. `configure_counter(...)` — lifespan-startup swap point. When the
   platform-metrics project lands, this becomes a one-line wire
   change.

**Why wire the seam now if the backend is `NoopCounter`?** Backfilling
metric call sites later is a cross-cutting refactor. Wiring them today
(with the no-op default) lets the future platform-metrics project ship
a one-line lifespan change. Costs near-zero today; saves a refactor
later.

**N=2 destination.** Second adopter triggers a
`projects/platform-metrics/` (TBD) follow-up that lifts the Protocol
+ a real backend (likely OpenTelemetry, given the multi-export story)
into `noctusai_lib.observability.counter`.

---

## 8. Adoption checklist

When a chatbot product enters its production-hardening phase, walk:

- [ ] **Retries.** External-write call sites wrapped with `retry_call`
      + tuned per-API `RetryPolicy`. Idempotency keys present for
      non-idempotent ops.
- [ ] **Structured logs.** `app/logging_config.py` is a re-export of
      `noctusai_lib.logging_config`. No `print(...)`. No `# silent-ok`.
- [ ] **Health check.** `standard_routers=["health", ...]` includes
      `"health"`. Compose `healthcheck:` block wired.
- [ ] **DEPLOYMENT.md.** Six sections. Env vars table complete.
      Secrets handling explicit. Smoke-test recipe copy-pasteable.
- [ ] **Backup.** Restore path documented. Critical tables listed.
      Disaster-recovery drill exercised at least once.
- [ ] **Metrics sink.** `app/services/metrics.py` shipped with seam +
      `NoopCounter`. Call sites at the dispatcher boundary.

Each item lands on green or files a follow-up project (with a named
destination) per the no-silent-errors rule.

---

## 9. First adopter — imobi-scheduling (absorbed into social-wiring)

The first walkthrough of this pattern shipped in the `imobi-scheduling`
product (2026-05-11). That product was retired on 2026-05-16
(`social-wiring-absorption` Wave 4) and its scheduling chatbot absorbed
into `products/social-wiring/app/modules/scheduling/`. The pattern is
durable; the canonical artifacts now live at the social-wiring paths:

- `products/social-wiring/app/modules/scheduling/.../retry.py`
- `products/social-wiring/app/modules/scheduling/.../metrics.py`
- `products/social-wiring/DEPLOYMENT.md`
- `products/social-wiring/.../logging_config.py` (re-export)
- Calendar wrappers in the scheduling module adopt `retry_call` at
  create/update/delete.

Future adopters (therapy / social-wiring email-marketing / PF) inherit
the pattern verbatim; N=2 triggers the seed-side lifts noted in §2
(retry) and §7 (metrics).
