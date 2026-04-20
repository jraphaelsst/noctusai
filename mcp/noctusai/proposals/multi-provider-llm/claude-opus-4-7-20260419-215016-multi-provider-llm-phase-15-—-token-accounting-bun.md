# Proposal: Multi-provider LLM Phase 15 — Token accounting bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-15
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 15 shipped the observability foundation: `UsageEvent`, `UsageSink` Protocol, `InMemoryUsageSink`, catalog-driven cost estimation (gpt-4o/mini, claude family, gemini-1.5), and provider-side recording in all 4 OpenAI methods. 9 tests. DB sink + admin aggregate endpoints deferred.

---

## 2. Situation

Core works but carries performance and correctness caveats: every lib call pays for `get_llm_config()` even when the sink is None; `estimate_cost_usd` linearly scans the catalog per call; audio cost is always 0 because token counts aren't exposed; `UsageEvent` cost is frozen at record-time (historical costs rot); no RLS on the in-memory sink.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. Cache sink-availability check at provider init

**Linkage:** Every call hits get_llm_config + attribute lookup; sink-None is the 99% case in dev.

**Steps:**
1. Cache `self._sink_available` at provider construction
2. Invalidate on `configure_llm` (push to a signal, or check `id(config)`)

**Risks:** Low — tests cover sink=None path

*Independent:* can be applied without other bundled improvements.

#### 2. Build a (provider, model) dict once at models.py import

**Linkage:** `models_for` + filter-by-id is O(n) per call. Dict lookup is O(1).

**Steps:**
1. Add `_MODELS_BY_KEY: dict[tuple[str, str, ModelKind], ModelEntry]` populated on import
2. Rewrite `estimate_cost_usd` + `is_stub_model` to use the dict

**Risks:** Low — catalog is static. Tests already verify correctness.

*Independent:* can be applied without other bundled improvements.

#### 3. Estimate audio cost from duration when reported

**Linkage:** Whisper charges per-minute. Duration is in the response; we discard it.

**Steps:**
1. Extend ModelEntry with `cost_per_minute_usd: Optional[float]`
2. In OpenAI.transcribe_audio, read `response.duration` if present
3. Update estimate_cost_usd signature + record_usage to handle duration

**Risks:** Medium — changes the UsageEvent shape; tests need updating

*Depends on:* improvement(s) #2.

#### 4. DB-backed SupabaseUsageSink + per-product migration

**Linkage:** InMemorySink doesn't survive restart. Production needs persistent storage.

**Steps:**
1. Write `seed/backend/lib/noctusai_lib/llm/sinks/supabase_sink.py`
2. Per-product migration: `products/<p>/backend/migrations/NNN_llm_usage.sql`
3. RLS: org members read own rows, service_role writes
4. Wire via `create_product_app(..., llm_usage_sink=...)`

**Risks:** Medium — new migration + cross-product touch

*Independent:* can be applied without other bundled improvements.

#### 5. Admin aggregate endpoint in Core

**Linkage:** Admins need `GET /api/admin/llm-usage?from=&to=&group_by=` for cost reports.

**Steps:**
1. Write `core/backend/app/routers/admin_usage.py`
2. Platform-admin gate
3. Aggregate over `public.llm_usage` (or union of product tables)
4. Pagination + period + groupby

**Risks:** Medium — query shape depends on where the DB sink lands

*Depends on:* improvement(s) #4.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — additive changes.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Dev/staging see observability — prod waits on DB sink
- **Ergonomics:** Cache lookups + catalog scans drop O(n) → O(1)

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product core` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
