# Proposal: Phase 4 Tier C follow-ups (cross-schema audit + bounded N+1 helper)

**Agent:** claude-opus-4-7
**Origin:** project:personal-finance-wiring:phase-4
**Generated:** 2026-05-10
**Severity:** medium
**Effort:** small (cross-schema audit) + medium (N+1 seed helper)
**Affected products:** personal-finance (this engineer); cross-product candidates: erp-imobiliario, therapy-platform, daily-life
**Status:** pending

---

## 1. Context

Phase 4 of `personal-finance-wiring` (Tier C scaffolding debt) shipped the recorrentes router → service refactor, the cross-schema `organizations` reach fix in `monthly_narrative_service`, the RLS audit, the `search_path` audit, the N+1 walk, the orphan-endpoint triage, and the LGPD evaluation. Two findings did not land inline because they cross the engineer's dispatch scope (`products/personal-finance/**` only): a cross-product audit and a seed-side helper candidate.

This proposal carries both forward for cross-product owners or future seed-extension projects.

---

## 2. Situation

### 2.1 Cross-schema `db.table("organizations")` slip — likely cross-product recurrence

PF-8 surfaced at `products/personal-finance/backend/app/services/monthly_narrative_service.py:147`. The service receives `db = get_user_client(token)` from the router (`routers/ai.py:118`), which is a Supabase client pinned to schema `personal-finance`. The original call `db.table("organizations").select("id, nome").eq("id", org_id).single().execute()` would fail at runtime with PGRST205 (`relation "organizations" not found in schema "personal-finance"`) because `organizations` lives in the `public` schema.

The fix is mechanical: import `get_core_client` from `app.database` and use `core.table("organizations")` instead. The seed already provides this primitive: `seed/framework/backend/noctusai_seed/database.py:53` (`DatabaseModule.get_core_client()` → schema=`public`).

**Risk: this slip almost certainly exists in sister-product services that also need cross-schema reach.** Likely candidates by shape:
- ERP `monthly_narrative` or any service that reads `organizations` / `noctus_users` from product code.
- Therapy clinical-digest services with org-name interpolation.
- Daily-life weekly-review services.
- Any product that emails an org-name greeting and reads it from `public.organizations`.

Existing PF tests didn't catch this because mock fixtures hit the empty-data fallback path. Real-DB tests likely catch it, but those run less frequently.

### 2.2 Bounded N+1 in `relatorios_service.relatorio_anual`

The annual report at `products/personal-finance/backend/app/services/relatorios_service.py:25-61` is the canonical "loop over N fixed periods, cache-fallback per period" shape:

1. Batch-fetch all 12 months from `resumos_mensais` cache in 1 query (good).
2. For each month, if cache-hit use it; if cache-miss compute (`_computar_relatorio_mensal` = 1 query) and save (`_salvar_cache` = 1 select + 1 update or 1 insert).

Worst case (cold cache): 1 batch + 12 × 3 = 37 DB calls. Already constant-bounded at N=12 (months in a year). Cache prefetch at line 28 is the right optimization; the per-month computation cost is unavoidable because the cache key is `(org_id, mes)` and the cache miss must compute the full month.

This is the **same shape that surfaces across products** with periodic reports:
- Monthly digest backfill (ERP, daily-life, therapy).
- Weekly review (daily-life).
- Yearly portfolio rebalance (PF).
- Annual financial close (ERP).

N=1 today within PF. Flip to formalize at cross-product N=2+.

---

## 3. Proposed Solution

### 3.1 Cross-schema audit (out of dispatch scope; cross-product project)

File a follow-up project `cross-schema-organization-reach-audit` (or similar slug). Scope: walk every product backend at `products/*/backend/app/services/` looking for the slip shape `db.table("organizations")` or `db.table("noctus_users")` where `db` is a product-scoped client. Replace with `get_core_client()` calls. Owner: orchestrator dispatches as routine cross-product cleanup; one engineer per affected product OR a single engineer doing all products in one pass (these are mechanical edits).

**Detection grep** (run from noc root):

```bash
grep -rnE 'db\.table\("(organizations|noctus_users|sso_link|product_membership)"\)' products/*/backend/app/services/
```

Any non-zero result that's reading via a `get_user_client`/product-schema client is a slip. Anything that's already routing through `get_core_client()` or `supabase_admin` is fine.

### 3.2 Seed-side `cached_period_loop` helper (defer until N=2+)

**N=1 today (this PF instance) — accept-with-rationale and watch.** When ERP, daily-life, or therapy ship a sister "annual report" / "monthly digest backfill" feature with the same shape, flip to formalize:

Candidate seed surface (`noctusai_lib/api/batch_cache.py` or `noctusai_lib/domain/reports/`):

```python
async def cached_period_loop(
    *,
    db,
    org_id: str,
    cache_table: str,            # e.g. "resumos_mensais"
    cache_key_column: str,        # e.g. "mes"
    periods: list[str],           # e.g. ["2026-01", ..., "2026-12"]
    fetch_one: Callable[[str], Awaitable[dict]],   # compute one period
    cache_payload_column: str = "dados",
) -> list[dict]:
    """Batch-prefetch the cache, then yield per-period results — computing
    + cache-writing on miss. Returns periods in input order.

    Eliminates the N+1-of-bounded-N anti-pattern in periodic reports."""
    ...
```

This is a small primitive; the win is convention, not LoC. Document at `KB § PATTERNS/cached-period-loop.md`. Once N=2 confirms the shape, the lift fits the seed-fake-real-adapter pattern (pure-logic exempt — `cached_period_loop` is data orchestration, no IO of its own beyond the injected `db`).

---

## 4. Risks / Trade-offs

- **Cross-schema audit risk**: zero. Detection grep is precise; the fix is mechanical and the seed primitive already exists. Tests should pick up regressions (the PF test gap is a fixture-fallback issue, not a seed gap).
- **`cached_period_loop` helper risk**: premature abstraction if shipped at N=1. Defer to N=2.

---

## 5. Application checklist

- [ ] Cross-schema audit — file `cross-schema-organization-reach-audit` cross-product project. Owner: orchestrator.
- [ ] Watch for sister "annual report" / "monthly digest backfill" features in ERP / daily-life / therapy; flip `cached_period_loop` to formalize at N=2. Owner: whoever ships the second instance.

---

## 6. References

- PF-8 fix: `products/personal-finance/backend/app/services/monthly_narrative_service.py:147` (this phase).
- Seed primitive: `seed/framework/backend/noctusai_seed/database.py:53` (`get_core_client`).
- Bounded N+1 site: `products/personal-finance/backend/app/services/relatorios_service.py:43-49`.
- Recurrence rule: `KB § PATTERNS/project-execution.md § 2.7`.
- Seed-lib layout: `KB § PATTERNS/seed-lib-layout.md`.
