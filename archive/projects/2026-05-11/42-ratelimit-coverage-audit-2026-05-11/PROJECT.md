# Rate-Limit Coverage Audit — Project Document

> **Phase 0 audit only.** Read-only inventory of `@limiter.limit` decorator
> coverage across all 11 products. No source-code edits in this project. The
> follow-on rollout work (Phase 1+) will be filed as separate projects after
> orchestrator triage.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0 audit complete — recommended next steps in §7
- **Owner / stakeholders:** USER · Engineer RATELIMIT-AUDIT
- **Related docs:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhook-signatures.md` (5-pin contract; Pin 4 = rate-limit)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/llm-bot-security.md §7.1` (per-conversation limiter)
  - `seed/lib/backend/noctusai_lib/api/rate_limit.py` (seed factory)
  - `seed/framework/backend/noctusai_seed/rate_limit.py` (settings-aware wrapper)
- **Project slug:** `ratelimit-coverage-audit-2026-05-11`

---

## 1. Context & Purpose

The 5-pin webhook compliance contract (formalized 2026-05-09) makes
`@limiter.limit(settings.webhook_rate_limit)` **Pin 4** for every webhook
receiver. Webhook coverage is now well-policed. **General API surface — auth,
public CRUD, LLM bot endpoints — is NOT.** Most products instantiate a
`Limiter` (via the seed factory) and pass it to `create_product_app`, but only
apply `@limiter.limit` decorators on webhook routes. That leaves authenticated
CRUD endpoints and (more importantly) **unauth auth-endpoints** wide open to
brute-force / scraper / runaway-client abuse.

This audit inventories who's where and emits a prioritized close-the-gap
queue.

---

## 2. Confirmed constraints

- **Read-only audit.** No router / service edits in this project. *(Any code change is a follow-up project, filed after Phase 0 triage.)*
- **Seed-first lens.** The seed already ships `create_limiter` (lib) + `create_product_limiter` (framework). Per-product code count for the **factory** is zero. Per-product code count for the **decorator placement** is non-zero by design (only the product knows which of its routes are public / authenticated / vendor-webhooks). *(Rules out "lift the decorator into seed"; the seam already exists.)*
- **No new abstractions in audit phase.** If a per-product decorator pattern recurs at N≥3, file as a seed-extension follow-up — don't pre-create. *(Recurrence rule fires only at evidence.)*

---

## 3. Design principles

1. **Classify, don't prescribe.** Audit emits a triage table; rollout decisions belong to the orchestrator.
2. **Recurrence-rule lens.** If 3+ products need the *same* shape of rate-limit on the *same* surface (auth/login, signup, CRUD), that's a seed-extension signal.
3. **Don't double-count webhooks.** They're already covered by Pin 4 — out-of-scope for this audit's gap analysis (in-scope only for inventory).

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** PARTIAL — *the factory shape is universal* (slowapi `Limiter` with optional Redis backing); *the policy* (`5/min` vs `30/min` vs `60/min`) is per-route, not per-product.
2. **Is the data source product-specific?** N/A — rate-limit is a transport guard, not a data-binding.
3. **Is the placement product-specific?** YES — auth router exists in `core/` + `therapy-platform/` only; LLM-bot router exists in `imobi-scheduling/` (+ ERP `whatsapp.py`, therapy `whatsapp_therapy.py`); CRUD routers vary wildly. Only the *product* knows which of its routes are unauth.
4. **Is the visibility / permission rule the same?** YES at the decorator level — `@limiter.limit("N/period")` is uniform syntax.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.api.rate_limit.create_limiter` (lib) + `noctusai_seed.rate_limit.create_product_limiter` (framework). Every product consumes it via `from app.rate_limit import limiter` → 10/11 products already wired (dev-team is the gap; see §5).
6. **Default-on or opt-in?** **OPT-IN per-route** — the seed factory builds the `Limiter` instance; route authors apply `@limiter.limit(...)` where they want it. This is correct: a forced default-on at decorator level would either be too strict (breaking authenticated power-user flows) or too loose (not protecting `/auth/login`).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — the `app/rate_limit.py` 5-line consumer of the seed factory + 0..N `@limiter.limit(...)` decorators on routes the product owns. *Acceptable for opt-in placement.*

**Phase plan implications:** Phase 0 = inventory + triage (THIS project). Phase 1+ = per-product rollout, filed as separate follow-up projects.

---

## 4. Scope

**In scope (Phase 0):**
- Per-product inventory of `@limiter.limit` decorator usage
- Classification (always-applied / webhooks-only / none / custom)
- Identification of the seed seam shape
- Top-N highest-priority gap list

**Out of scope (for now):**
- Actual rollout of `@limiter.limit` decorators — *follow-up project per product cluster*
- KB pattern doc for `rate-limit.md` — *propose at follow-up project time, after the rollout shape stabilizes (recurrence rule)*
- Tuning the per-route policy (5/min vs 30/min) — *each cluster's project owns its calibration*
- LLM-bot per-conversation limiter (imobi-scheduling's custom) — *separate concern; covered by KB §7.1 and already shipped*

---

## 5. Architecture / Data Model

### 5.1 — Seed seam (already shipped)

**Lib layer** — `seed/lib/backend/noctusai_lib/api/rate_limit.py`:
```python
def create_limiter(redis_url=None, default_limits=None) -> Limiter:
    # Builds slowapi Limiter. Redis storage if reachable; in-memory fallback.
    # default_limits=["100/minute"] if unspecified.
```

**Framework layer** — `seed/framework/backend/noctusai_seed/rate_limit.py`:
```python
def create_product_limiter(settings):
    redis_url = getattr(settings, "redis_url", None)
    return create_limiter(redis_url=redis_url)
```

**Consumer pattern** — `products/<p>/backend/app/rate_limit.py` (10/11 products, byte-identical 5-line module):
```python
"""Rate limiter for <Product> — delegates to framework."""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings
limiter = create_product_limiter(settings)
```

Wired into `app/main.py` via `create_product_app(..., limiter=limiter, ...)`. Routes that want enforcement decorate with `@limiter.limit("N/period")` and accept `request: Request` (or `response: Response`) as the slowapi key-extractor.

### 5.2 — Custom in-app primitive (LLM bot)

`products/imobi-scheduling/backend/app/services/conversation_rate_limit.py`:
- `ConversationRateLimiter` Protocol
- `RedisConversationRateLimiter` concrete (used in prod)
- `configure_rate_limiter` lifespan-wire
- Wired in `app/lifespan.py` for the LLM-tool-dispatch hot loop

This is the per-conversation (chat_id-keyed) limiter; orthogonal to the slowapi per-IP factory. KB §7.1 (`llm-bot-security.md`) flags `noctusai_lib.api.conversation_rate_limit` as the seed-lift destination once N=2.

### 5.3 — `dev-team` exception

`products/dev-team/backend/app/main.py` does NOT import or pass `limiter` to `create_product_app`. No `app/rate_limit.py` module. Routes (`agents.py`, `metrics.py`, `run.py`, `configs.py`) have no `@limiter.limit` decorators.

---

## 5.4 — Per-product audit table

| # | Product | `app/rate_limit.py` | `@limiter.limit` route files | Routes decorated | Total routers | Classification | Notes |
|---|---|---|---|---|---|---|---|
| 1 | adconnect | ✅ seed-delegated | `financial.py` | 1 (webhook) | 9 | **Webhooks only** | Asaas billing webhook (Pin 4) |
| 2 | core | ✅ seed-delegated | `billing.py` + `auth.py` | 5 (1 webhook + 4 auth) | 28 | **Webhooks + auth (partial)** | Stripe webhook + login/refresh/forgot-password (5/min on `forgot-password`, 10/min on others). No SSO/OAuth/team-invite rate-limit. |
| 3 | daily-life | ✅ seed-delegated | — | 0 | 7 | **None (factory wired only)** | No webhooks, no auth-bearing routes — auth is in `core`. Gap is benign on auth-side. |
| 4 | dev-team | ❌ MISSING | — | 0 | 4 | **None — no factory wired** | `main.py` doesn't pass `limiter=`. Routes proxy agno engine — `run.py` could DoS the LLM. **HIGH PRIORITY**. |
| 5 | erp-imobiliario | ✅ seed-delegated | 7 routers | 23 (3 webhook + 20 mixed) | 59 | **Most comprehensive** | `ai.py` (8×30/min, 1×60/min) + `portal_externo.py` (5×30/min) + `portal_cliente.py` (4×30/min) + `whatsapp.py` (2×30/min) + 3 webhooks (Pin 4). The reference pattern. |
| 6 | imobi-scheduling | ✅ seed-delegated | `webhook_router.py` | 1 (webhook) | 3 | **Webhooks only + custom LLM limiter** | WAHA webhook (Pin 4) + `services/conversation_rate_limit.py` (per-chat Redis). `whatsapp_router.py` has 0 slowapi decorators — relies on conversation limiter. |
| 7 | mailing | ✅ seed-delegated | `webhooks.py` | 1 (webhook) | 10 | **Webhooks only** | Resend webhook (Pin 4). 9 CRUD routers (`campaigns`, `contacts`, `lists`, `automations`, `templates`, …) unlimited. |
| 8 | media-scheduling | ✅ seed-delegated | `webhooks.py` | 1 (webhook) | 5 | **Webhooks only** | WAHA webhook (Pin 4). `oauth.py` (Google OAuth callback) UNLIMITED — gap. |
| 9 | personal-finance | ✅ seed-delegated | — | 0 | 15 | **None (factory wired only)** | 15 CRUD routers (`transacoes`, `contas`, `metas`, `dashboard`, `ai.py` …) — `ai.py` LLM endpoint unlimited. |
| 10 | therapy-platform | ✅ seed-delegated | `auth.py` + `whatsapp_therapy.py` | 8 (6 auth + 2 LLM-WA) | 40 | **Auth + WA partial** | `auth.py` (10/min × 5 + 5/min × 1 on signup) + `whatsapp_therapy.py` (30/min × 2). 38 other routers (38 CRUD covering patients/sessions/payments/wallets) unlimited. |
| 11 | youtube-crawler | ✅ seed-delegated | — | 0 | 0 | **None (no app routers yet)** | Reference seed product; `routers/__init__.py` only. N/A — defer until product gains real routes. |

**Summary — coverage classification:**
- **None / factory-only-wired:** `daily-life`, `personal-finance`, `youtube-crawler` (3)
- **Factory MISSING entirely:** `dev-team` (1) ← **STRUCTURAL gap**
- **Webhooks only:** `adconnect`, `imobi-scheduling`, `mailing`, `media-scheduling` (4)
- **Webhooks + auth (partial):** `core`, `therapy-platform` (2)
- **Comprehensive (auth + CRUD + LLM + WA + webhooks):** `erp-imobiliario` (1)
- **Custom in-app primitive:** `imobi-scheduling` (per-conversation Redis limiter for LLM bot — orthogonal to slowapi)

---

## 6. Implementation phases

### Phase 0 — Audit ✅ (2026-05-11)

- [x] Per-product `grep -rln "@limiter.limit"` inventory
- [x] Read `seed/lib/backend/noctusai_lib/api/rate_limit.py` + framework wrapper
- [x] Read `products/<p>/backend/app/rate_limit.py` for all 11 (10 byte-identical; dev-team missing)
- [x] Count decorated routes vs total routers per product
- [x] Identify custom primitives (`conversation_rate_limit.py`)
- [x] Triage table at §5.4
- [x] Recommended Phase 1 dispatch shape at §7

**Improvements:** none — audit was a discovery scan, no implementation friction.

### Phase 1+ — Rollout (NOT EXECUTED in this project)

The recommended follow-up shape:

1. **`dev-team-rate-limit-wiring`** (HIGH PRIORITY) — create `products/dev-team/backend/app/rate_limit.py` (consume seed factory) + pass `limiter=` to `create_product_app` + decorate `run.py` (LLM-engine dispatch) with `@limiter.limit("30/minute")`. *Why high: `run.py` proxies the agno LLM team — runaway loops or scraping = unbounded LLM spend.*
2. **`auth-rate-limit-rollout`** (cluster project) — add `@limiter.limit("5/minute")` / `"10/minute"` to all unauth login / signup / forgot-password / SSO-callback endpoints in `core`. Reference pattern: `core/auth.py` (already shipped). Targets: `core/sso.py`, `core/oauth.py`, `core/onboarding.py`, `core/test_accounts.py`, plus `therapy-platform/auth.py` (already partially done — round out missing endpoints), plus `media-scheduling/oauth.py`.
3. **`llm-endpoint-rate-limit-rollout`** (cluster project) — `mailing/ai.py`, `personal-finance/ai.py`, `daily-life/ai.py`, `therapy-platform`'s LLM-touching routers. Pattern reference: `erp-imobiliario/ai.py` (30/min). *Why grouped: same shape, same recurrence (N=4+), seed-lift candidate if it grows.*
4. **`crud-rate-limit-rollout`** (LOWEST PRIORITY) — broad CRUD endpoints across `mailing`, `personal-finance`, `daily-life`, `therapy-platform`. Catch-all "60/min" default-cover on read-heavy GETs; authenticated, lower-risk. *Recommend defer until 1+2+3 land — most likely never needed if access is properly authenticated and Cloudflare / proxy WAF is in front.*

### Phase 2 — KB pattern doc (deferred — after Phase 1 lands)

A `KB § PATTERNS/rate-limit.md` doc should reference:
- The seed seam (`create_limiter` / `create_product_limiter`)
- Recommended policies by route class (public auth: 5-10/min; authenticated CRUD: 60/min; LLM: 30/min; webhooks: vendor-dictated)
- The two-layer model: slowapi (per-IP transport) + `conversation_rate_limit` (per-chat application)
- Link from `webhook-signatures.md §Pin 4`

File as part of Phase 2 of the auth-rate-limit-rollout project — pattern docs are most accurate when written *from* a recently-shipped rollout.

---

## 7. Open questions

1. **dev-team `limiter=` wiring — defer or rush?** — `run.py` proxies LLM team execution; runaway client = LLM-spend DoS. **Recommendation: rush — `dev-team-rate-limit-wiring` is the first follow-up project.** Decided by USER at dispatch time.
2. **Should `noctusai_seed.create_product_app` enforce `limiter=` not-None?** — `dev-team`'s gap was silent because `limiter=None` is accepted. Could add a `WARN-on-None` log line (no hard-fail; gradual rollout). *Decided by orchestrator at Phase 1 dispatch.* Companion thought: this same shape (`limiter=None` accepted) is what surfaced the gap, so the absence-as-claim rule says we should at least log it.
3. **Per-conversation limiter seed-lift trigger (N=2)?** — KB §7.1 says `noctusai_lib.api.conversation_rate_limit` is the destination *once N=2*. Right now N=1 (imobi-scheduling only). Therapy-platform's `whatsapp_therapy.py` could be the N=2 candidate — does it have similar Redis-per-chat needs? Inspect during therapy auth-rollout project.
4. **Should webhooks-only products (adconnect/mailing/media-scheduling) add `oauth.py` rate-limit too?** — `media-scheduling/oauth.py` is unauth Google OAuth callback. Same shape as `core/auth.py` "5/min on forgot-password". **Recommendation: yes — bundle into `auth-rate-limit-rollout` cluster project.**

---

## 8. Dependencies & blockers

- **None for audit Phase 0.** Read-only scan completed.
- **Phase 1 dispatch depends on USER triage** — orchestrator approves which of the 4 follow-up projects to spin up + parallel/serial choice.

---

## 9. Success criteria

**Phase 0 (this project):**
- [x] Per-product table complete (all 11 products)
- [x] Seed seam shape documented
- [x] Top-3 priority gaps identified (see §7 + report)
- [x] Recommended Phase 1 dispatch shape stated
- [x] Findings synthesized (5 categories)
- [x] 0 source code edits

**Phase 1+ (future projects):**
- `dev-team` has `limiter=` wired + `run.py` decorated
- Auth endpoints across `core` + `therapy-platform` + `media-scheduling` covered uniformly
- KB pattern doc filed after rollouts land

---

## 10. How to use this project

- **Closed at Phase 0.** Treat this file as the audit reference; follow-up project briefs cite §5.4 and §7.
- **Do NOT edit decorators in this branch.** Source-code rollout = separate branches per cluster project.
- **Findings live in `findings.md`** (sibling file) — knowledge for the orchestrator to mine when dispatching Phase 1+.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 0 audit complete — table at §5.4, recommendations at §6/§7 | Engineer RATELIMIT-AUDIT |
