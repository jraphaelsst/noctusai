# LLM Usage Tracking — Sink Pattern + Cost Accounting

> Every successful LLM call emits a `UsageEvent` (provider, model, operation,
> tokens, cost estimate, `org_id`, timestamp) to the active `UsageSink`. In
> dev/test we keep events in memory; in production we write them to
> `<schema>.llm_usage` via `SupabaseUsageSink`. Reads are RLS-scoped
> per-org; aggregates are served through `/api/llm/usage` per-product and
> `/api/admin/llm-usage` in Core.

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

## 4. Endpoints

**Per-product** (inherited via `noctusai_seed.llm_router`):
```
GET /api/llm/usage?from=ISO&to=ISO&group_by=provider_model&limit=5000
    → { events, aggregate, window }
```
Returns the caller's org's rows (RLS-scoped) plus an in-memory aggregate bucketed by `provider`, `model`, `operation`, or `provider_model`.

**Core admin** (platform-admin only, service role):
```
GET /api/admin/llm-usage?product=&org_id=&from=ISO&to=ISO
    → { per_product: { slug: { calls, total_tokens, cost, by_model } }, totals, window }
```
Scans every product schema's `llm_usage` table. Add a new product by appending to `_PRODUCT_SCHEMAS` in `products/core/backend/app/routers/admin_llm_usage.py`.

## 5. Cost estimation

`estimate_cost_usd(provider, model, prompt_tokens, completion_tokens)` reads `cost_per_1m_input_tokens` / `cost_per_1m_output_tokens` from the model catalog. Unknown models return `0.0` (no crash). Values are approximations — use for dashboards and budget alarms, **not** billing-of-record.

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
