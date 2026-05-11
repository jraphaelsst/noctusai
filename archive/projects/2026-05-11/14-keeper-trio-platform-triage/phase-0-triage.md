# Phase 0 — Per-product triage queue

**Date:** 2026-05-11
**Engineer:** RR (read-only classification phase)
**Scope:** Classification only — no code edits, no migrations, no proposals.

> **TL;DR:** 207 findings classified across core / erp-imobiliario / mailing / personal-finance. **14 REAL_BUG** (3 unknown_table + 9 search_path + 2 cross-schema cases needing detector tuning), **192 DEFENSE_IN_DEPTH** (missing `service_role_bypass` policies — RLS service-role bypass works at the connection level + many products use schema-level `GRANT ALL ... TO service_role`, but explicit per-table policy is the convention), and **1 FALSE_POSITIVE** (`admin_llm_usage` cross-schema call the detector cannot parse).

---

## Summary table

| Product | REAL_BUG | DEFENSE_IN_DEPTH | FALSE_POSITIVE | Total |
|---|---|---|---|---|
| core | 1 | 149 | 1 | 151 |
| erp-imobiliario | 11 (9 search_path + 1 unknown_table + 1 cross-schema unknown) | 33 | 1 (org_settings cross-schema overlap) | 45 |
| mailing | 0 | 18 | 0 | 18 |
| personal-finance | 0 | 1 | 0 | 1 |
| **Total** | **12** | **201** | **2** | **215** |

> Note: total = 215, not 207. Core has 2 `unknown_table` rows that also produce an `admin_bypass` row on the same site (`billing_events`, `llm_usage`), so each surfaces twice in the raw 151. PROJECT.md tally (2 + 149 = 151) is correct; this triage classifies each row independently and dedup is noted inline where it matters.

---

## Per-product findings

### core (151 findings)

#### REAL_BUG (1 finding)

- **`backend/app/routers/billing.py:284` — table `billing_events` is referenced but has no `CREATE TABLE` anywhere in the platform.**
  - Rationale: `db.table("billing_events").insert({...})` is the Stripe-webhook side-effect that persists raw events for idempotency + audit. **No migration creates `core.billing_events` (verified by `grep -rln "CREATE TABLE.*billing_events"` returning only the router file)**. In production, the call returns "table not found" and the webhook handler raises — silent failures masked by MockSupabase in tests.
  - Recommended fix: add `core.billing_events (stripe_event_id PK, event_type, stripe_customer_id, org_id, payload jsonb, created_at)` migration. Likely also needs the `service_role_bypass` policy.

#### FALSE_POSITIVE (1 finding) — detector tuning candidate

- **`backend/app/routers/admin_llm_usage.py:92` — `.table('llm_usage')` flagged as unknown_table in core.**
  - Rationale: the call is `db.schema(schema).table("llm_usage")` where `schema` ∈ `{"erp", "therapy"}` (see `_PRODUCT_SCHEMAS` map, lines 30-33). Tables exist at `products/erp-imobiliario/backend/migrations/020_llm_usage.sql` + `products/therapy-platform/backend/migrations/006_llm_usage.sql`. **The detector does not understand `.schema(...)` chained before `.table(...)`** — it treats every `.table(X)` as a local-schema reference.
  - Recommended detector tuning: when `.table(X)` is preceded by `.schema(Y)` on the same chain, look up `X` in `products/<Y_to_slug>/backend/migrations/*.sql` instead of the file's own product. Anti-shape today is N=1 (this one site), so detector tuning is enough; no platform-wide refactor needed.
  - Same line also surfaces an admin_bypass row — that is also FALSE_POSITIVE for the same reason (the cross-schema bypass policy must live in ERP/therapy's migrations, not core's).

#### DEFENSE_IN_DEPTH (149 findings) — single cluster

- **Cluster: every `core` admin client call against tables that lack a named `service_role_bypass` policy.**
  - **Affected tables (counts):** `noctus_users` (43), `subscriptions` (32), `roles` (16), `licenses` (14), `plans` (11), `webhook_endpoints` (6), `webhook_deliveries` (5), `org_settings` (5), `audit_logs` (5), `api_keys` (5), `platform_settings` (4), `notifications` (2), `billing_events` (1 — overlaps with the REAL_BUG above).
  - **Affected files (counts, top 10):** `routers/team.py` (13), `routers/roles.py` (12), `services/billing_service.py` (11), `routers/analytics.py` (9), `routers/users.py` (7), `routers/test_accounts.py` (7), `routers/subscriptions.py` (7), `routers/licenses.py` (7), `routers/billing.py` (7), `app/dependencies.py` (7) … 22 files total.
  - **Why DEFENSE_IN_DEPTH, not REAL_BUG**: `products/core/backend/migrations/001_noctusai_core.sql` line 357+ already grants `FOR ALL TO service_role` per-table on the same tables (49+ such policies). The Supabase `service_role` JWT bypasses RLS at the connection level. Runtime is currently fine. **However**, the detector's heuristic looks for the literal policy *name* `"service_role_bypass"` (KB § PATTERNS/testing.md) — core's policies are unnamed/different-named, so the detector flags them.
  - **Recommended fix (one decision closes 149 findings):** EITHER (a) **migration that renames/adds** `service_role_bypass` policies on the 13 affected tables (DEFENSE_IN_DEPTH hardening — explicit policy makes the intent unambiguous); OR (b) **tune the detector** to accept any `FOR ALL TO service_role` policy regardless of name (cuts noise without changing behavior). Per the platform's "triage at decision time" rule, recommend (a) for production-correctness explicitness; (b) as a complementary detector calibration. Therapy's `001_therapy_platform.sql` (lines 846+) is the canonical reference shape.

---

### erp-imobiliario (45 findings)

#### REAL_BUG (11 findings)

- **`backend/app/routers/ai.py:351` — table `certidoes_negativas` does not exist; actual tables are `certidao_consultas` + `certidao_resultados`.**
  - Rationale: `db.table("certidoes_negativas").select("tipo, status, data_emissao, observacoes")...` (line 351). The migration at `products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql:2304` creates `erp.certidao_consultas` + `erp.certidao_resultados` — the columns referenced (`tipo`, `status`, `data_emissao`, `observacoes`) don't all map to either. This route returns "table not found" in production.
  - Recommended fix: rewrite the `ai.py:347-360` block to query `erp.certidao_resultados` (joining via `consulta_id` → `erp.certidao_consultas`) — actual columns: `tipo`, `nome_display`, `status`, `analise_ia`, `api_response`, `erro_mensagem`, `api_requested_at`, `created_at`. The router intent (recent certidão summaries for a `cliente_id`) needs a join through `certidao_consultas` because the consulta-level FK to clientes is implicit (no `cliente_id` column on `certidao_consultas` — uses `tipo_documento`+`documento` instead). **Genuine bug + non-trivial fix; needs Phase 1 attention.**

- **9 × `search_path` not pinned (Supabase advisor 0011 — REAL_BUG per detector author + advisor).**
  - All 9 functions confirmed to lack `SET search_path = ...`:
    1. `003_schema_separation.sql:91` — `erp.current_date_sao_paulo()` (LANGUAGE SQL STABLE)
    2. `003_schema_separation.sql:96` — `erp.now_sao_paulo()` (LANGUAGE SQL STABLE)
    3. `003_schema_separation.sql:101` — `erp.normalize_timestamp_sp(ts)` (LANGUAGE SQL IMMUTABLE)
    4. `003_schema_separation.sql:308` — `erp.distribuir_meta_descendente()` (TRIGGER, no SET clause)
    5. `003_schema_separation.sql:696` — `erp.calcular_nivel_performance(p_realizada, p_pretendida)` (plpgsql IMMUTABLE)
    6. `003_schema_separation.sql:750` — `erp.delete_expired_password_codes()` (plpgsql SECURITY DEFINER — **highest-risk: SECURITY DEFINER without search_path is the classic privilege-escalation vector**)
    7. `003_schema_separation.sql:756` — `erp.get_data_sp()` (LANGUAGE SQL STABLE)
    8. `004_mvp_expansion.sql:28` — `erp.set_timestamps_sp()` (TRIGGER, no SET clause)
    9. `005_fix_sidebar_pages.sql:11` — `erp.set_timestamps_sp()` (TRIGGER override, no SET clause)
  - Recommended fix: single migration that `CREATE OR REPLACE FUNCTION` each with `SET search_path = erp, public` (or `SET search_path = ''` per Supabase advisor for STABLE/IMMUTABLE). The other 30+ ERP functions in 003 already use this pattern (`SECURITY DEFINER SET search_path = erp, public`) — these 9 are the gaps.

- **`backend/app/routers/assinaturas.py:84` — table `org_settings` referenced but does not exist in ERP migrations.**
  - Rationale: `db.table("org_settings").select("value").eq("org_id", org_id).eq("key", "assinatura_webhook_secret")...`. **No `CREATE TABLE erp.org_settings` in any ERP migration**. Likely a cross-schema reference to `core.org_settings` (which DOES exist — see core RLS policies on it) but ERP's `db.table("org_settings")` won't reach there without an explicit `.schema("core")` chain. Production query would fail in ERP's `erp` schema search path.
  - Recommended fix: either (a) add an `erp.org_settings` migration with the same shape, OR (b) prefix the call with `.schema("core")` if cross-product secret-store is intentional. **Decide before fixing — has security/multi-tenant implications.**

#### DEFENSE_IN_DEPTH (33 findings)

- **Cluster: ERP tables without a named `service_role_bypass` policy.**
  - **Affected tables (counts):** `ativos` (8), `assinaturas` (5), `site_config` (3), `meta_config` (3), `whatsapp_messages` (2), `profiles` (2), `clientes` (2), `campanhas` (2), `whatsapp_config` (1), `parcelas_contrato` (1), `meta_leads` (1), `matches` (1), `envios_email` (1), `contratos` (1) — 14 tables.
  - **Why DEFENSE_IN_DEPTH:** ERP's `001_erp_imobiliario.sql:2264` and `004_mvp_expansion.sql:1074` contain DO-blocks that dynamically `CREATE POLICY %I ON erp.%I FOR ALL TO service_role USING (true)` for many tables — the policy NAMES are dynamic (anonymous), but the policies do exist at runtime. Plus `2362, 2381, 2468, 011_storage_buckets.sql:53, 007_certidoes_negativas.sql:81/83` carry explicit `auth.role() = 'service_role'` USING checks. Detector heuristic looks for literal `"service_role_bypass"` and misses both patterns.
  - **Recommended fix:** unified migration that adds explicit `CREATE POLICY "service_role_bypass" ON erp.<table> FOR ALL TO service_role USING (true) WITH CHECK (true)` for the 14 affected tables. Cuts findings to 0 and aligns with therapy's canonical shape.

- **`erp-imobiliario` migration 003:84 (org_settings)** — overlaps with the REAL_BUG above; counted under REAL_BUG.

#### FALSE_POSITIVE (1 finding)

- **`backend/app/routers/assinaturas.py:84` admin_bypass — flagged on `org_settings`.** This is the same site as the unknown_table REAL_BUG above; the admin_bypass row is a downstream artifact (the detector can't tell the table is missing first). Once REAL_BUG is fixed, this row resolves automatically.

---

### mailing (18 findings)

#### REAL_BUG (0)

None — all 18 are the same DEFENSE_IN_DEPTH pattern.

#### DEFENSE_IN_DEPTH (18 findings) — single cluster

- **Cluster: mailing tables without a named `service_role_bypass` policy.**
  - **Affected tables (counts):** `sender_domains` (4), `send_logs` (4), `contacts` (4), `campaigns` (3), `unsubscribes` (2), `automation_enrollments` (1).
  - **Affected files (counts):** `app/scheduler.py` (3), `app/routers/unsubscribe.py` (2), `app/routers/settings.py` (4), `app/routers/analytics.py` (5), `app/routers/webhooks.py` (4).
  - **Why DEFENSE_IN_DEPTH:** `001_mailing.sql:11-15` issues `GRANT ALL ON ALL TABLES IN SCHEMA mailing TO ... service_role` + `ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON TABLES TO ... service_role`. RLS is enabled per-table with org-scoped policies (e.g. `campaigns_own_org`, `send_logs_own_org`), but no per-table `service_role_bypass` policy. Service-role connection-level RLS bypass + schema-level grant cover runtime, but the detector flags the absence of explicit policy.
  - **Recommended fix:** add explicit `CREATE POLICY "service_role_bypass" ON mailing.<table> FOR ALL TO service_role USING (true) WITH CHECK (true)` for the 6 affected tables (consider all RLS-enabled mailing tables for symmetry).

---

### personal-finance (1 finding)

#### DEFENSE_IN_DEPTH (1 finding)

- **`backend/app/scheduler.py:30` — admin client call on `recorrentes` lacks `service_role_bypass` policy.**
  - Rationale: `"personal-finance".recorrentes` exists (`001_personal_finance.sql:221`). Schema-level grant: `001_personal_finance.sql:22` does `GRANT USAGE ON SCHEMA "personal-finance" TO ... service_role`. RLS pattern matches mailing (org-scoped policies, no explicit `service_role_bypass`). Runtime is fine via connection-level bypass + schema grant.
  - **Recommended fix:** add explicit `CREATE POLICY "service_role_bypass" ON "personal-finance".recorrentes FOR ALL TO service_role USING (true) WITH CHECK (true)` (and consider all 12+ RLS-enabled tables in PF for symmetry — once you're already in there).

---

## Recurrence patterns

### N≥3 cluster — **the dominant slip**

**Pattern: every product has tables with RLS + service-role-bypass mechanism (schema grant OR FOR-ALL-TO-service_role policy OR `auth.role() = 'service_role'` USING check), but none uses the literal `service_role_bypass` policy name that the detector + therapy's canonical reference shape uses.**

- **Recurrence (4 products):** core, erp-imobiliario, mailing, personal-finance.
- **Therapy already adopted** the literal `service_role_bypass` name (per `001_therapy_platform.sql:846-`).
- **N=4 → MUST formalize** (per CLAUDE.md §1 recurrence rule).

**Formalization options:**

1. **Single platform-wide migration template** (`KB § PATTERNS/database-rls.md` extension): every `001_<product>.sql` and every `CREATE TABLE` in a new migration MUST be followed by `CREATE POLICY "service_role_bypass" ON <schema>.<table> FOR ALL TO service_role USING (true) WITH CHECK (true)`. Bundle into `noctusai_lib.sql.service_role_bypass(table)` helper alongside `prelude` + `updated_at_trigger`.

2. **Detector accommodation** (complementary): broaden `check_admin_endpoint_service_role_bypass` to accept ANY of:
   - `CREATE POLICY <any-name> ON <schema>.<table> FOR ALL TO service_role …`
   - `CREATE POLICY <any-name> ON <schema>.<table> FOR ALL USING (auth.role() = 'service_role')`
   - `GRANT ALL ON ALL TABLES IN SCHEMA <schema> TO service_role` (schema-level grant).

**Recommended: (1) for production explicitness (matches CLAUDE.md "extend framework, never go custom"), (2) as a tuning pass to clear pre-existing noise without re-migrating every old table.**

### N=3 cluster — search_path on functions without explicit pin (ERP only)

Only ERP triggers this; therapy was cleared. **Recommendation:** add a keeper-trio reminder in `KB § PATTERNS/database-rls.md` § Functions: every `CREATE FUNCTION` MUST include `SET search_path = <schema>, public` (or `''` for IMMUTABLE/STABLE language SQL).

### Detector-tuning candidate (N=1 today)

The `.schema(X).table(Y)` cross-schema chain is unparseable by the unknown_table + admin_bypass detectors. Only one site uses it (core/admin_llm_usage). N=1 → low priority; flag for keeper detector v2.

---

## Recommended Phase 1 dispatch shape

**Cap dispatch at the actual leverage:**

- **REAL_BUG = 12 sites** across only 3 products (core: 1 / erp: 11 / mailing: 0 / pf: 0). These need engineer attention.
- **DEFENSE_IN_DEPTH = 201 sites** across 4 products, but **all 4 collapse to a single migration per product** (add `service_role_bypass` policies — 13 tables in core, 14 in ERP, 6 in mailing, 1+ in PF) ≈ 4 migrations total.

### Dispatch plan

1. **Single child `keeper-trio-core`** — 1 migration (add `billing_events` table + service_role_bypass on the 13 admin-touched tables). Size: M.
2. **Single child `keeper-trio-erp`** — 3 migrations: (a) fix `certidoes_negativas` query in `ai.py:351` + decide on `org_settings` cross-schema-vs-create-local, (b) re-create the 9 functions with `SET search_path`, (c) add `service_role_bypass` on the 14 admin-touched tables. Size: L (most complex; routes through `ai.py` semantic redesign).
3. **Single child `keeper-trio-mailing`** — 1 migration (service_role_bypass on 6 tables). Size: S.
4. **Single child `keeper-trio-pf`** — 1 migration (service_role_bypass on `recorrentes`, optionally all PF tables for symmetry). Size: XS — could be inline (5-min fix per PROJECT.md prediction).

**FALSE_POSITIVE rate per product is below the 50% threshold** (core ≈ 0.7%, erp ≈ 2.2%, mailing 0%, pf 0%), so **no detector-tuning-first gate needed**. The cross-schema `.schema(X).table(Y)` detector gap is N=1 → file as a separate small follow-up project (`keeper-detector-schema-chain-tuning`) **before** Phase 1 children dispatch so the 2 false-positive rows clear automatically.

### Parallelism

The 4 product children are file-disjoint → **dispatch all 4 in parallel** (master-tree parallel-batch). Plus a 5th branch for the detector tuning. ERP is the longest pole; the other three are short.

### Optional fifth child

- **`keeper-trio-seed-formalize`** — add `service_role_bypass` helper to `noctusai_lib.sql` (canonical naming), update `KB § PATTERNS/database-rls.md` with the convention. **Dispatch BEFORE the product children** so they consume the helper. Sequential dependency — Wave 0 (formalize) → Wave 1 (per-product fixes).

### Wave structure

- **Wave 0** (serial): `keeper-detector-schema-chain-tuning` + `keeper-trio-seed-formalize`. Both can run parallel to each other but must FF-merge before Wave 1.
- **Wave 1** (parallel × 4): `keeper-trio-core`, `keeper-trio-erp`, `keeper-trio-mailing`, `keeper-trio-pf`.
