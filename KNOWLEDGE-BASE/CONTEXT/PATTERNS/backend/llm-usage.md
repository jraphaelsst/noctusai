# LLM Usage Tracking — Sink Pattern + Cost Accounting

> **Since 2026-10-29 (roadmap D25) the source of truth is ONE central ledger:
> `public.ai_usage`** (core migration `091_ai_usage.sql`). Every LLM call of
> every product, core included, is a row there. Rows are attributed, priced at
> write time, append-only, and written by the seed by construction. §0 below
> is the current contract. §1–§3 describe the legacy per-schema
> `<schema>.llm_usage` copy, which is still written only for products that set
> `llm_usage_tracking=True`, pending
> `NOC-REMEDIATE[ai-usage-retire-legacy-llm-usage]`.

## 0. The central ledger (D25)

- **Write path.** `create_product_app` installs `CentralUsageSink`
  (`noctusai_lib/integrations/llm/ledger.py`) for every product, using
  `get_core_client`, which is the service role on `public`. There is no
  per-product registration and no hand-kept product→schema map. Under pytest
  the factory returns `None`; tests pass `force_real=True` with a mock client.
- **Attribution** (`attribution.py`). Layers resolve innermost-wins:
  1. Process default product: the catalog slug, or `core` for schema `public`.
  2. The HTTP request: `UsageAttributionMiddleware` (mounted by
     `configure_app`) supplies `user_id`/`org_id` from
     `request.state.audit_actor`, which comes from the seed auth deps and is
     never `user_metadata`. It also supplies `feature = "METHOD /route/template"`
     and `request_id` = the correlation id.
  3. Explicit `with llm_usage_context(feature=, purpose=, agent_key=, conversation_id=, org_id=, user_id=)`.
     These nest, and contextvars follow tasks and `to_thread`.
- **Pricing.** `price_usage(...)` returns `(cost_usd, price_version)`.
  `price_version` is one of:
  - `override:v<N>` (DB catalog override)
  - `catalog:<sha10 of the rates>`
  - `unpriced` (unknown model; the row is flagged in `extra.unpriced`, never
    silently free)

  BRL uses the latest `public.fx_rates` USD/BRL PTAX, cached for 1 h. With no
  bulletin it falls back to `LLM_USD_TO_BRL` and sets
  `extra.fx_source = "env_fallback"` plus `fx_warning`.
- **Every call is a row.**
  - `status=ok`: a normal call.
  - `status=error`: the provider raised. Tokens are null and the error class is
    in `extra`. Recorded by `metered_call` around chat, tool turns, embeddings,
    vision and audio, and by the image-edit adapter. Local refusals (not
    configured, provider stub, budget) are not rows.
  - `status=partial`: a stream cut short by a consumer abort or a mid-stream
    error, recorded by `metered_stream`. Tokens are estimated at chars/4 and
    `extra.tokens_estimated` is set to true.
- **Append-only.** A trigger refuses UPDATE, DELETE and TRUNCATE for every
  role. The single exception is the wallet's `charged_credits` NULL→value
  stamp. This is proven against prod by the `verify_db_guards` probes
  `ai_usage.update_refused`, `ai_usage.delete_refused` and
  `ai_usage.charged_credits_restamp_refused`.
- **RLS.** `authenticated` gets SELECT only, covering members of the row's org
  and platform admins. Writes are INSERT by the service role.
- **Reads** (`ledger_read.py`). `read_ai_usage_rows` is paged via
  `iter_paged_rows` and raises `AiUsageWindowTooLarge` instead of truncating.
  `aggregate_ai_usage` rolls up org → product → feature (plus `by_model`).
  Consumers:
  - core `GET /api/admin/llm-usage` (platform admin, with `org_id/product/feature/from/to` filters)
  - seed `GET /api/llm/usage` (caller's org × this product)
  - the budget guard (`budget.py`, which sums `cost_brl`)
  - social-wiring `/api/custos`
- **D26 gate.** Keeper `check_no_direct_llm_sdk_import` (`--check-no-direct-llm-sdk-import`,
  pre-commit) refuses `anthropic`/`openai` imports in product backends: a call
  that bypasses the seed seam is unbilled and invisible.
- **Deferred.**
  - A failed insert is logged at ERROR, not spooled. The marker is
    `NOC-REMEDIATE[ai-usage-durable-outbox]` in `ledger.py`.
  - Image-edit batch items need an idempotency key before they can be rows.
    The marker is `NOC-REMEDIATE[ai-usage-image-edit-batch]` in
    `openai_adapter.py`.

---

## 1. Architecture

```
provider call (openai / anthropic / gemini)
    ↓ success
record_usage(provider, model, operation, tokens, org_id)
    ↓ reads LLMConfig.usage_sink (may be None)
SupabaseUsageSink.record(UsageEvent)
    ↓ service-role INSERT
<schema>.llm_usage (one row per call)
```

- **Sink is optional.** `usage_sink=None` → no tracking (`record_usage` returns early).
- **Failure is swallowed.** A broken sink must not fail a successful LLM call. Errors log at WARN.
- **Provider-side emission.** The three real providers (OpenAI, Anthropic, Gemini) call `record_usage` after extracting tokens from their SDK's response. Entry points (`chat_completion`, etc.) stay string-shaped.

## 2. Enabling in production

Opt-in per product via env var:

```
# .env
LLM_USAGE_TRACKING=1
```

The framework (`create_product_app()`) reads `settings.llm_usage_tracking`, pulls a service-role Supabase client from the product's `DatabaseModule`, and passes both into `default_llm_config(usage_tracking_db=..., usage_tracking_schema=...)`. No product code changes.

## 3. Schema

Each product ships its own migration (`NNN_llm_usage.sql`). The shape is identical across products — only the tenant-scoping RLS differs:

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `org_id` | UUID nullable | Tenant key (ERP: org_id; Therapy: clinic_id — stored under `org_id` per existing convention) |
| `provider` | TEXT | `openai` / `anthropic` / `gemini` |
| `model` | TEXT | e.g. `gpt-4o-mini` |
| `operation` | TEXT | `chat` / `embedding` / `audio` / `vision` |
| `prompt_tokens` | INTEGER | Nullable (some ops don't report) |
| `completion_tokens` | INTEGER | Nullable |
| `total_tokens` | INTEGER | Nullable |
| `cost_estimate_usd` | NUMERIC(12,6) | Catalog-driven; 0.0 for unknown models |
| `at` | TIMESTAMPTZ | Call timestamp |

Indexes: `(org_id, at DESC)`, `(provider, model)`, `(at DESC)`.

RLS: SELECT restricted by `public.current_org_id()` (ERP) or `therapy.current_clinic_id()` (Therapy). ERP admins get full-org access via `public.has_role(auth.uid(), 'admin')`. Writes are service-role only.

## 4. Endpoints (both read `public.ai_usage` since D25)

**Per-product** (inherited via `noctusai_seed.llm_router`):
```
GET /api/llm/usage?from=ISO&to=ISO&group_by=provider_model|feature|...&limit=500
    → { events, aggregate, ledger, window }
```
The caller's org × this product, read from the central ledger with the core
client. `aggregate` is bucketed by `provider`, `model`, `operation`,
`provider_model` or `feature`. `ledger` is `aggregate_ai_usage`. A caller
with no org gets a 403.

**Core admin** (platform admin only, service role):
```
GET /api/admin/llm-usage?org_id=&product=&feature=&from=ISO&to=ISO
    → { window, filters, totals, per_org[→per_product[→per_feature, by_model]], per_product{slug: ...} }
```
This endpoint has no product map. A new product appears the moment its
first call lands.

## 5. Cost estimation

`price_usage(...)` → `(cost_usd, price_version)` (and its shim `estimate_cost_usd(...)`) reads the EFFECTIVE catalog (DB overrides first) for `cost_per_1m_input_tokens` / `cost_per_1m_output_tokens` from the model catalog. Unknown models return `(0.0, "unpriced")`; the ledger row is flagged `extra.unpriced`, never silently free. The ledger is the FOUNDATION of per-org billing: the wallet slice charges `charged_credits` from these write-time prices.

Stored cost is *snapshotted* at call time. If provider prices change later, historical rows keep their old cost. To recompute accurately, query tokens and apply current prices client-side.

## 6. LGPD

- `UsageEvent` intentionally stores **counts only** — never prompt or response text.
- The sink writes the event as-is; the schema has no text columns.
- Clinical paths (Therapy) also set `cache=False` on `chat_completion`; the two controls are orthogonal and both required.
- Per-clinic aggregation by `org_id` is a legitimate billing signal; it doesn't identify patients.

If you find yourself adding a text column to `llm_usage`, stop. Use structured logs or a separate audit table with explicit LGPD review.

## 7. Testing

- `InMemoryUsageSink` for unit tests — `.events` + `.aggregate()` give you exact assertions.
- `SupabaseUsageSink` wraps an injected `db_client` with `.schema().table().insert().execute()`. Tests pass a fake client mirroring that fluent API. See `mcp/noctusai/tests/test_llm_usage.py::TestSupabaseUsageSink`.
- Sink failures are swallowed — `test_record_swallows_db_errors` pins the behavior.

## 8. When to reach for this vs just logs

- **Use `llm_usage`** when: per-org cost attribution, platform billing dashboards, anomaly detection ("why did ERP org X burn $200 on gpt-4o last week?").
- **Use structured logs** when: debugging a specific prompt, capturing request/response bodies (with LGPD scrubbing), one-off investigation.

The two complement. Don't cross the streams — never dump prompt content into `llm_usage`.
