# Database & RLS Patterns

234+ tables across 7 schemas. All RLS-enabled. Supabase-hosted.

## Schemas

| Schema | Owner | Purpose |
|---|---|---|
| `public` | Core | Auth, orgs, billing, licenses, notifications, products registry |
| `erp` | ERP | Real estate CRM (imóveis, clientes, contratos, comissões, visitas, metas) |
| `personal-finance` | PF | Accounts, transactions, budgets, portfolios — org-scoped via `public.current_org_id()` (post 2026-05-03 `pf-org-scoping-migration`); 12 op tables + 4 child tables, each parent has `org_id NOT NULL + created_by UUID NULL`. |
| `therapy` | Therapy | Therapists, patients, sessions, wallets, messaging |
| `daily_life` | Daily Life | Tasks, goals, habits, schedule, notes |
| `mailing` | Mailing | Contacts, lists, templates, campaigns, automations |
| `seed` | Seed | Reference impl; empty of business data |

## RLS — the canonical rules

1. **All tables have RLS enabled** — no exceptions.
2. **Use `(SELECT auth.uid())`**, not bare `auth.uid()`.
   - Bare form: re-evaluated per-row (quadratic cost on large tables).
   - Subquery form: cached per-statement.
3. **All SECURITY DEFINER functions include `SET search_path = public, <schema>`** — prevents search-path hijacking attacks.
4. **HaveIBeenPwned check enabled** on Supabase Auth (org-wide policy).
5. **Service role bypasses RLS** via `get_admin_client()`. Use sparingly — cross-tenant leaks start here.
6. **A tooling-created bookkeeping table is not exempt from rule 1** — see § Migration ledger RLS below. Every product schema is PostgREST-exposed with default grants, so ANY table without RLS is readable/writable over REST, whether or not it holds "real" domain data.

## Policy patterns

**Own-row access (agent-facing data):**
```sql
CREATE POLICY "own rows"
  ON erp.eventos FOR ALL
  USING ((SELECT auth.uid()) = corretor_id);
```

**Org-level access (admin/manager):**
```sql
CREATE POLICY "org scoped"
  ON erp.contratos FOR SELECT
  USING (org_id = (SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid())));
```

**Leader-of-team access (ERP Metas):**
```sql
CREATE POLICY "leader sees team"
  ON erp.metas FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM erp.equipe_membros em
    WHERE em.user_id = erp.metas.user_id
      AND em.equipe_id = (
        SELECT equipe_id FROM erp.equipe_membros
        WHERE user_id = (SELECT auth.uid()) AND papel = 'lider'
      )
  ));
```

### Service-role bypass — canonical helper

Every product backend uses the Supabase `service_role` JWT through `get_admin_client()`. The JWT bypasses RLS at the *connection level* — so admin-client reads/writes work even without a per-table policy. But the platform ships a keeper detector (`check_admin_endpoint_service_role_bypass`, run by `python mcp/noctusai/cli.py --review`) that surfaces tables lacking an *explicit named* `service_role_bypass` policy — the explicit policy makes the intent unambiguous and is the platform convention going forward.

> **Critical:** the detector heuristic is *literal name match*. It looks for a policy whose name is exactly `service_role_bypass`. Equivalent policies under different names (e.g. core's `noctus_users_service_role` or ERP's dynamic DO-block-generated anonymous policies) are *still flagged*. **Renaming the policy in a future cleanup pass re-opens every keeper finding for that table.** The literal name is the contract.

**Canonical SQL (mirrors `products/therapy-platform/backend/migrations/001_therapy_platform.sql:846+`):**

```sql
CREATE POLICY "service_role_bypass" ON <schema>.<table>
  FOR ALL TO service_role USING (true) WITH CHECK (true);
```

**Helper:** `noctusai_lib.sql.service_role_bypass(table, schema="public")` — added 2026-05-11 by `projects/keeper-trio-seed-formalize/` as the Wave 0 seed addition for the keeper-trio platform triage. Mirrors the existing `prelude` + `updated_at_trigger` shape (canonical impl in `noctusai_lib.domain.sql_templates`; thin re-export wrapper in `noctusai_lib.sql`).

**Usage in fresh migrations:**

```python
from noctusai_lib.sql import prelude, service_role_bypass, updated_at_trigger

body = "\n".join([
    prelude("erp"),
    updated_at_trigger("clientes", schema="erp"),
    "",
    service_role_bypass("clientes", schema="erp"),
    service_role_bypass("contratos", schema="erp"),
    # one line per RLS-enabled table needing admin-client access
])
```

**Output (single line per table, byte-equal to therapy):**

```sql
CREATE POLICY "service_role_bypass" ON erp.clientes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON erp.contratos FOR ALL TO service_role USING (true) WITH CHECK (true);
```

**Reference adopter:** `products/therapy-platform/backend/migrations/001_therapy_platform.sql:846+` emits 40 of these in sequence. Test `test_service_role_bypass.TestAgainstTherapyMigration` pins byte-equality against the real migration.

**Coverage gap context:** Engineer RR's triage (`projects/keeper-trio-platform-triage/phase-0-triage.md`, 2026-05-11) classified 192 of 215 keeper findings as this same DEFENSE_IN_DEPTH cluster — every per-product admin client call on a table that lacks the literal `service_role_bypass` policy. Wave 1 per-product children (`keeper-trio-{core,erp,mailing,pf}`) consume this helper to close the cluster.

### RLS self-reference recursion (Postgres 42P17) — N=3

**The bug.** An RLS policy whose `USING` / `WITH CHECK` clause **subqueries the
table the policy is ON** recurses at evaluation: reading `foo` applies `foo`'s
policy, which reads `foo`, which re-applies the policy → `42P17 "infinite
recursion detected in policy for relation foo"`. A **hard prod outage**, not a
degradation — the table becomes unreadable for `authenticated` (service_role has
BYPASSRLS, so it's masked until a real authenticated read hits it: the frontend's
direct supabase-js reads, or `GET /api/auth/me`).

The classic shape:
```sql
-- ❌ recursive: the policy reads its own table
CREATE POLICY "users_read_own" ON public.noctus_users FOR SELECT TO authenticated
  USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));
```

**The fix — a SECURITY DEFINER bypass helper.** Resolve the scope in a
`SECURITY DEFINER` function (runs as the owner → BYPASSRLS → does NOT re-trigger
the policy), then call it from the policy. Always `SET search_path = ''` +
fully-qualify (search-path hardening) and `REVOKE ALL ... FROM PUBLIC; GRANT
EXECUTE ... TO authenticated`.
```sql
-- ✅ non-recursive
CREATE OR REPLACE FUNCTION public.current_user_org_id() RETURNS uuid
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid()); $$;
REVOKE ALL ON FUNCTION public.current_user_org_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_user_org_id() TO authenticated;
CREATE POLICY "users_read_own" ON public.noctus_users FOR SELECT TO authenticated
  USING (id = (SELECT auth.uid()) OR org_id = public.current_user_org_id());
```
Fixing the table's OWN policy cures the whole cascade — the other policies that
subquery `SELECT org_id FROM noctus_users WHERE id = auth.uid()` become safe once
`noctus_users`' own policy no longer recurses.

**Recurrence (N=3).** `erp.equipe_membros` (`026_fix_equipe_membros_rls_recursion`)
· `public.noctus_users` (`035_fix_noctus_users_rls_recursion`, the 2026-05-23 core
login outage) · `therapy.conversation_participants` (`001_therapy_platform.sql`,
**latent** — flagged by the keeper, fix pending). **Keeper:**
`check_rls_policy_self_reference` (Stage-4, `compliance.py`; migration-supersession
aware so a later DROP+recreate clears the original; severity `error`, baseline 0
since 2026-05-23 — therapy `015` cleared the last finding; live-apply of 015 is the
separate gated prod-DB step). Memory: `feedback_rls_policy_self_reference`.

## Migrations

Numbered SQL files in `products/<name>/backend/migrations/001_*.sql`, `002_*.sql`, etc. These files are the **authoritative replay log** — the DB is mutable state and can be wiped; the files are what rebuild it.

**Rules:**
- Idempotent: use `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` where Postgres supports them.
- RLS enabled in the same migration that creates the table. No "enable RLS later" follow-ups.
- Seed data, if any, goes in a separate `00X_seed_*.sql` file.
- **Next number wins — but "next" is not `max(local NN) + 1`.** Use `noctus.dev.next_migration_number` (or just `noctus.dev.scaffold_migration`, which calls it internally) rather than eyeballing `ls migrations/`. See § Migration-number collision safety below.

### Migrations mirror the code — the live-schema drift gate (2026-09-17)

A migration FILE existing, being syntactically valid, and even being recorded
"applied" in `schema_migrations` are three different facts from "the live
schema actually has what the code reads and writes." Three real bugs, found
the same day, all the same shape:

1. `erp.assinaturas.external_id` — `assinatura_service.preparar_envio` had
   inserted this key for months. No migration ever created the column
   (`047_assinaturas_external_id.sql` added it after the fact).
2. `erp.tool_call_audits` — `ai_service.py` + `audit_hook.py` write rows via
   the seed `make_audit_writer`. Migration `030_tool_call_audits.sql` was
   authored but never *applied* — erp's `schema_migrations` ledger was
   empty (the pre-2026-09 phantom-schema bug wrote bookkeeping to
   `erp_imobiliario` while DDL landed in `erp`), so "which migrations ran"
   was unanswerable. Table absent.
3. `erp.llm_preferences` — a live routed page (`App.tsx:283` →
   `useLLMPreferences()`) called an endpoint backed by a table whose
   migration (`017_llm_preferences.sql`) referenced `public.org_members`, a
   table that has NEVER existed in this database, so it could never apply.
   Table absent in every schema — a live dead page.

All three survived because (a) the applied-ledger was unanswerable (now
closed — ledgers reconciled, `noctus.dev.migrate_product` refuses a stale
tree, § Migration ledger RLS above) and (b) the product's own tests ran
`MockSupabaseClient(validate_schema=False)`, so a missing table/column was
invisible to them (§ below, and `KB § PATTERNS/compliance/testing.md`).

**`noctus.dev.schema_drift`** closes the remaining question: given a fully-
applied migration set, does the live schema still match what the product's
migrations (parsed by the SAME `noctusai_lib.testing.migration_parser`
`MockSupabaseClient` uses) and any SQLAlchemy ORM models (`app/models/*.py`,
AST-extracted, never executed) declare? It queries
`information_schema.columns` via the same `SqlExecutor` DI seam
`noctus.dev.migrate_product` uses. Findings: `missing_table` /
`missing_column` (declared-vs-live) and `orm_migration_drift` (ORM mirror
vs. migrations — offline, no live DB needed). A product with NEITHER a
migrations dir NOR ORM models is `undeterminable` — a finding, never a
silent pass (fail-closed).

**Blind spot, by construction:** a column the code writes that NO migration
(and no ORM model) ever declared — bug #1's own shape — agrees with itself
on both sides of a migrations-vs-live diff, so `schema_drift` cannot see it.
That gap is closed by a DIFFERENT leg: `check_mock_schema_validation`
gating `validate_schema=False` (see `KB § PATTERNS/compliance/testing.md`)
forces the product's OWN test suite to exercise every code call site
against the real column set.

Wired into `noctus.dev.predeploy_check` as the `schema_drift` leg (sibling
of `schema_exposure`, same fail-closed posture — `not_configured` /
`undeterminable` / `error` all BLOCK a deploy, never silently skip).

### Migration-number collision safety — cross-worktree, not just cross-file

Two migrations sharing a numeric prefix have undefined apply-order. This bit twice: 2026-08-03 (three concurrent sessions each picked a number from `ls migrations/` + `git log origin/dev` — both blind to a sibling branch that hadn't pushed; two collided on `040`) and 2026-08-13 (a parallel worktree's migration merged and deployed FIRST; the other worktree, mid-authoring its own same-numbered file, had not rebased and so never saw it — ~1600 lines of rework before the tech-lead caught it at integration).

**Pick correctly at authoring time — `noctus.dev.scaffold_migration` / `noctus.dev.next_migration_number`.** The number is computed from THREE unioned sources, none sufficient alone:

1. This worktree's own `migrations/` directory — the naive signal.
2. `origin/dev`, freshly fetched — the authoritative merged state. Catches a migration a parallel worktree already merged that this worktree hasn't rebased onto (the 2026-08-13 shape).
3. Every LOCAL branch (git refs are shared across every worktree of one clone) diffed against `origin/dev` — catches a sibling worktree's committed-but-unpushed migration (the 2026-08-03 shape).

`scaffold_migration` consumes this internally, so using the standard authoring tool is sufficient — no extra step to remember. Call `next_migration_number` directly only to preview a number before scaffolding, or to sanity-check a hand-picked one.

**Two backstops catch what authoring-time missed.** `check_migration_number_collision` (a `check_*` keeper — the compliance-not-authoring layer) runs at `pre-commit` whenever a migration is staged: **Leg A** (severity `high`, blocking) flags a duplicate number already ON DISK; **Leg B** (severity `warning`, non-blocking) flags a number two DIFFERENT local branches both claim, latent until one of them merges second. Leg B stays a warning at commit time deliberately — blocking it would punish whichever branch happens to commit first for something not their fault (the collision belongs to whoever merges *second*, who may not be this commit). The SECOND backstop is `noctus.dev.task_branch(action='integrate')`: after the branch rebases onto fresh `origin/dev` (so Leg A's plain directory scan now sees both the merged state and this branch's own migration together) it re-runs the same unmodified keeper, scoped to the directories this branch's own migrations touch.

**2026-09-23 — the collision RENUMBERS, it does not just block.** Six hand-done `fix: renumber NNN→MMM` commits after `scaffold_migration`/`next_migration_number` shipped were the evidence the block was routine, not exceptional — concurrent worktrees pick the same next number often enough that the safety net was firing every session. Per the owner's gates-are-nets-not-walls directive, `integrate` now auto-resolves the ONE deterministic, safe shape: THIS branch's own newly-introduced file, colliding with exactly one on-disk sibling it did NOT introduce, that is confirmed **not yet applied to any DB** (via `migrate_product`'s own dry-run listing, scoped to that one filename — never a hand-rolled second query path). It `git mv`s the file to the next free number in its own directory (`max(on-disk NN) + 1`), rewrites the file's OWN in-file self-citation (a header like `-- Migration 057 --` / an inline `` `057` ``  — its own content only, never cross-file references in services/tests/docs, which stay a human follow-up as they always were), and commits `chore(migration): renumber NNN→MMM after rebase [auto]` on the branch before continuing to push. Three shapes still BLOCK, unchanged: an ambiguous on-disk collision (0 or 2+ non-ours siblings — no principled "which wins"), a Leg B finding with nothing on disk in THIS worktree to renumber against (an unmerged sibling's own number isn't safe to preempt), and applied-ness that cannot be established (no Supabase credentials / network / catalog scope — "cannot tell" never collapses to "assume safe"; the block names the one-call fix). See `mcp/noctusai/tools/noctus/dev/task_branch.py`'s module comment above `_MIGRATION_NUM_RE` for the full narrowing rationale.

### Single 001 migration convention (fresh-start optimization)

> **One-line rule:** every product ships a single `001_<product>.sql` that builds the full schema from scratch. Additive patches for live DBs land as `002+`, but the 001 stays in lock-step.

The replay-log invariant is that **applying `001_<product>.sql` alone to a fresh DB produces the same final shape as applying 001 + every patch in order.** Two reasons:

1. **Fresh-environment cost.** A new dev / CI / sandbox spin-up runs one file, not N. The 80-line "001 framework + 8 numbered patches" pattern AdConnect briefly carried in May 2026 turned a 30-second bootstrap into a 5-minute audit of which files apply in what order.
2. **Single-file diff for review.** When the schema evolves (Phase 2 catalog → Phase 3 orders → Phase 4 rewards), every change goes into one file. PR review reads the schema in topological order: framework → identity → catalog → orders → rewards → financial. No cross-file flip-back to understand FK targets.

**How to evolve the 001:**
- *Greenfield product*: scaffold drops a single `001_<product>.sql` with framework tables only. Each MVP-implementation phase **edits 001 in-place** to add tables/RLS/columns. No `002_*.sql` is created during initial implementation.
- *Live DB past 001*: ship the additive change as `002_<patch>.sql` (idempotent, applies cleanly on top of an existing 001-deployed DB) AND mirror the change into `001_<product>.sql` (so a fresh DB still bootstraps with one file). Both files commit together.
- *Topological ordering inside 001*: schema → grants → trigger functions → tables in dependency order (parents before children). Defer FKs that would require forward references via `ALTER TABLE ... ADD CONSTRAINT` at the bottom of the file.

**Why not just bigger 001s without patches?** Because Supabase's migration log records what was applied — if you're past 001 and want to add a column, you can't re-apply 001 without dropping the schema. The 002 patch records the delta in the live-DB log; the 001 mirror keeps fresh-start clean.

**Anti-pattern (don't):** N numbered files for a greenfield product where 001 has only framework tables and 002-007 are domain phases. Collapse them into a single 001 before merge to main. AdConnect's May 2026 collapse from 7 files → 1 is the reference fix.

### Migration ledger (`schema_migrations`) RLS — 2026-09-16

`noctus.dev.migrate_product` creates a `<schema>.schema_migrations` bookkeeping table per product (filename, applied_at, checksum). Rule 1 above ("all tables have RLS enabled — no exceptions") applies to it too: every product schema is PostgREST-exposed (see § PostgREST schema exposure below) with Postgres' default grants intact, so a bare bookkeeping table is readable AND writable over REST by `anon`/`authenticated` — including inserting a fake filename to make a future `migrate_product` run silently skip a real migration.

**Fix:** `ALTER TABLE <schema>.schema_migrations ENABLE ROW LEVEL SECURITY;` + `REVOKE ALL ON <schema>.schema_migrations FROM anon, authenticated;` — both idempotent, emitted by `_ensure_tracking_table_sql` for every newly created ledger and codified fleet-wide by `products/core/backend/migrations/048_lock_schema_migrations_ledgers.sql`. Full detail: `KB § PATTERNS/backend/migrate-product-mcp-tool.md § Ledger RLS hardening`.

### PostgREST schema exposure — the sibling gate to RLS

RLS controls WHO can read/write within a schema PostgREST already serves. A SEPARATE gate controls WHETHER PostgREST serves the schema at all: `authenticator`'s `pgrst.db_schemas` GUC, a comma-separated allowlist. A schema absent from it fails every REST call with `PGRST106` regardless of how correct its RLS policies are — the two gates are independent and both must be satisfied.

**Never overwrite this GUC with a literal list.** It's one shared value across the whole fleet; every product's onboarding migration appends to the SAME list. A migration that writes the full list as a hand-copied literal can silently DROP a schema added between when the literal was copied and when the migration runs — no error, just that product's REST API going down fleet-wide (memory `feedback_postgrest_exposed_schema_drop`; near-miss in `products/p-studio/backend/migrations/002_plataforma_e_seeds.sql`, which would have dropped `igig`).

**Canonical read-then-append shape:**

```sql
DO $$
DECLARE
    v_current text;
BEGIN
    SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_current
    FROM (
        SELECT unnest(setconfig) AS cfg
        FROM pg_db_role_setting s
        JOIN pg_roles r ON r.oid = s.setrole
        WHERE r.rolname = 'authenticator'
    ) t
    WHERE cfg LIKE 'pgrst.db_schemas=%';

    v_current := COALESCE(v_current, 'public, graphql_public');

    IF v_current !~ '(^|,)\s*<schema>\s*(,|$)' THEN
        EXECUTE format(
            'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
            v_current || ', <schema>'
        );
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;
```

- Reads the CURRENT value (never a literal copy) via `pg_db_role_setting` joined to `pg_roles`.
- `COALESCE`s to Supabase's own defaults (`public, graphql_public`) when the GUC is entirely unset — safe on a brand-new project too.
- Appends the target schema ONLY if a word-boundary regex says it's absent — never drops or reorders existing entries.
- `NOTIFY pgrst` (both `reload config` + `reload schema`) so PostgREST picks it up without a restart.

**Where this lives in the platform:** `noctus.dev.scaffold_product` emits this DO block automatically inside every new product's seed-row migration (`_pgrst_schema_exposure_sql` in `mcp/noctusai/tools/noctus/dev/scaffold.py`) — see `KB § GUIDES/new-product.md § PostgREST schema exposure`. The fleet-wide list as verified live on `nyplttplcoyiiqjrvtiw` (2026-09-16) is codified in `products/core/backend/migrations/049_reconcile_postgrest_exposed_schemas.sql`, using the same read-then-append logic per schema so a fresh DB reproduces the live state without ever risking a drop.

### Authoring helpers — `noctusai_lib.domain.sql_templates`

For new migrations and the product-scaffold tool, use the helpers in `noctusai_lib.domain.sql_templates` to emit the canonical shapes for the conventions that recur across products. The detector `scan_migration_patterns` flags drift; the helpers prevent it.

| Helper | Use for | Convention encoded |
|---|---|---|
| `set_search_path(*schemas)` | SECURITY DEFINER function preludes | Always trails `, public`; pinning prevents schema-search-path attacks. |
| `updated_at_function(schema)` | Once per schema | Standard `BEGIN NEW.updated_at = now(); RETURN NEW; END;` body + SECURITY DEFINER + locked search_path. |
| `updated_at_trigger(schema, table)` | Per-table | `BEFORE UPDATE FOR EACH ROW EXECUTE FUNCTION <schema>.set_updated_at()`. Default trigger name = `set_updated_at_<table>`. |
| `rls_subquery_policy(schema, table, policy_name, command, using=..., with_check=..., to_role=...)` | Every CREATE POLICY | Forces caller to use `(SELECT auth.uid())` shape; validates command/clause requirements (INSERT needs `with_check`; SELECT/DELETE need `using`). |

```python
from noctusai_lib.domain.sql_templates import (
    set_search_path,
    updated_at_function,
    updated_at_trigger,
    rls_subquery_policy,
)

# Inside scaffold or migration-author script:
print(updated_at_function("therapy"))           # → CREATE OR REPLACE FUNCTION therapy.set_updated_at()...
print(updated_at_trigger("therapy", "clinics")) # → CREATE OR REPLACE TRIGGER set_updated_at_clinics ...
print(rls_subquery_policy(
    "erp", "metas", "metas_select", "SELECT",
    using="(SELECT auth.uid()) = usuario_id",
))
```

Existing migration files (the replay log) are NOT rewritten; they stay authoritative per the MCP-migrations-mirror-the-file rule. The helpers exist for migrations being authored fresh + the scaffold tool that bootstraps new product schemas.

### Authoring-ergonomic wrappers — `noctusai_lib.sql` (2026-05-10)

Sits on top of `noctusai_lib.domain.sql_templates` — same canonical strings, more ergonomic API for direct authoring + the scaffold tool. Drift would surface in tests at BOTH layers simultaneously (delegation, not fork).

| Helper | Returns | Notes |
|---|---|---|
| `prelude(schema)` | Comment-block header (RLS isolation + cross-product safety rationale) + `SET search_path = '<schema>', public;` line + trailing newline | Use at the top of every new migration |
| `updated_at_function(schema, *, function_name="set_updated_at")` | `CREATE OR REPLACE FUNCTION` block | Threads `function_name=` for ERP's legacy `update_updated_at_column` shape |
| `updated_at_trigger(table, *, schema=None, function_name=..., trigger_name=..., include_function=True)` | Function + trigger pair (or trigger-only when `include_function=False`) | `include_function=False` is the composition lever for multi-table migrations |

```python
from noctusai_lib.sql import prelude, updated_at_trigger

migration = f"""
{prelude(schema="my_product")}

CREATE TABLE my_product.posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- ...
  updated_at timestamptz NOT NULL DEFAULT now()
);

{updated_at_trigger("posts", schema="my_product")}
"""
```

The MCP `noctus.dev.scaffold_migration` tool emits both helpers automatically — pass `with_updated_at=["posts", "comments"]` for multi-table cases. Existing migrations stay verbatim (cosmetic-only absorption; no churn).

## MCP + file sync (hard rule)

When you apply DDL via the Supabase MCP (`apply_migration` or `execute_sql`), the same SQL **must** live as a numbered migration file. Both get committed together. Drift between what's on the hosted DB and what's in the repo breaks fresh clones.

**The recipe:**
1. **Write the migration file** (`NNN_<slug>.sql`) and add parse tests for it (`tests/test_<slug>_migration.py`).
2. Run the parse tests — catch typos and structural mistakes cheaply.
3. **Apply via `mcp__claude_ai_Supabase__apply_migration`** with the same SQL body. Supabase records it in its own versioned migrations table under a timestamp version (independent of your sequential file number — both coexist).
4. Run the `realdb` tests to verify the live DB matches the file's intent.
5. Commit the migration file, the parse tests, and any code that consumes the new schema — all together.

**Do not use `execute_sql` for DDL.** It bypasses Supabase's migration tracking and leaves no record. Reserve `execute_sql` for read-only inspection.

**If you iterated live during debugging** (patched the DB directly), back-port every delta into a fresh migration file (`NNN+1_fix_<what>.sql`) before committing. Never leave DB state that isn't reproducible from the repo.

**Red flags to block at review:**
- A commit that changes the DB but doesn't touch `migrations/`.
- An `execute_sql` call body containing `CREATE TABLE`, `CREATE POLICY`, `ALTER TABLE`, `CREATE TYPE`, `ALTER TYPE`, `CREATE INDEX`, `DROP ...`.
- A migration file whose content doesn't match what's running on the DB.

See also `CLAUDE.md → MCP migrations mirror the file` and `CONTEXT/01-PHILOSOPHY.md → MCP migrations mirror the file`.

## Multi-tenant isolation

- Tenant key per product: see `02-LANDSCAPE.md` product table (`org_id` for most; `clinic_id` for Therapy).
- Every business table has the tenant key as the first filter in its RLS policy.

## Per-user-scoped vs org-scoped tables (the decision matrix) — 2026-05-10

**Two RLS-scoping conventions coexist intentionally** across the ERP product (and by extension other products that adopt the same pattern). The choice is design-driven, not a bug:

| Scoping | When to pick | Example tables (ERP) |
|---|---|---|
| **org-scoped** (`org_id` column + RLS filter) | Entity is shared across an org's users; multiple users can read/write the same row; admin role sees all rows in an org | `eventos`, `lancamentos`, `site_config`, `whatsapp_config`, `certidao_consultas` (post-2026-05-10 migration 027) |
| **per-user-scoped** (`owner_id` / `usuario_id` / `created_by` + RLS filter) | Entity belongs to one specific user within an org; admin role sees all via role-RLS, but normal users see only their own | `ativos`, `clientes`, `metas` (ERP); `recorrentes`, `transacoes`, `metas` (PF — user-owns-everything model); `goals`, `schedule`, `notes` (daily-life) |

**Rule of thumb:**
- If "user A and user B in the same org both work on row X" is normal → org-scoped.
- If "user A's row X is invisible to user B even in the same org (except admin)" is normal → per-user-scoped.

**The Engineer-D finding (2026-05-10):** `ativos`, `clientes`, `metas` in ERP appeared to be candidates for org-scoping retrofit at brief-time. Re-audit showed they're intentionally per-user-scoped — adding `org_id` would force a join through profiles.org_id and break the per-user mental model. **Documented as intentional divergence per `projects/erp-rls-org-scope-redesign/`** (resolved 2026-05-10 with Q1=b orchestrator-stamped default). Not a security gap — code paths for these tables never filter via `.eq("org_id", ...)`.

**Anti-pattern:** silently switching a per-user-scoped table to org-scoped without re-validating that "user A's row visible to user B in same org" is acceptable. The RLS-scoping switch is a design change, not a refactor.

## Cross-schema reach via `get_core_client()` — 2026-05-11

**Problem shape.** A product-schema service needs a row from `public.*` (e.g. `organizations`, `noctus_users`, `product_licenses`, `notifications`). The product's `db` argument is a Supabase client with `search_path = "<product-schema>", public`. PostgREST resolves `db.table("organizations")` against the FIRST schema in `search_path` — the product schema — where the relation does NOT exist. Result at runtime: **PGRST205 "relation organizations not found in schema <product-schema>"**.

**Slip shape — the bug masker.** Services that wrap the read in `or {fallback}` swallow the PGRST205 row-side (data ends up `None` → fallback dict wins) and never raise. Tests don't seed organizations rows, so the fallback always wins, false-green. Real bug only manifests in production once a real org row exists.

**Original sighting.** PF `monthly_narrative_service._fetch_window` (commit `15bea72`, Engineer W's PF Phase 4 close). Fixed by switching to `get_core_client()` (a Supabase client rooted in `public` schema).

**The canonical seam.** `get_core_client()` from `app.database` — every product re-exports it. The seed module ships it as `seed/framework/backend/noctusai_seed/database.py::DatabaseModule.get_core_client`.

```python
# BEFORE — product-schema client; PGRST205 at runtime, masked by fallback.
org_res = db.table("organizations").select("id, nome").eq("id", org_id).single().execute()
org_record = org_res.data or {"id": org_id, "nome": "Você"}

# AFTER — public-schema client; runtime-correct.
from app.database import get_core_client
core = get_core_client()
org_res = core.table("organizations").select("id, nome").eq("id", org_id).single().execute()
org_record = org_res.data or {"id": org_id, "nome": "Você"}
```

**When to reach for `get_core_client()`.** Any product-side read/write of a `public.*` table — `organizations`, `noctus_users`, `product_licenses`, `user_org_memberships`, `notifications`, `audit_log` (when surfaced cross-product). Adjacent product schemas use `.schema("<other-product>")` — also valid cross-schema but distinct from the public-shape reach this section addresses.

**Methodology amendment — `or {fallback}` after a DB read requires a non-fallback-path test.** When authoring code with shape `record = res.data or {default...}`:
1. Write at least one test that **seeds the row** and asserts the service consumes it (not the fallback).
2. The seeded-path test is the one that exercises the table-name + schema choice — the fallback-path test does not.
3. Without (1), PGRST205 (or any read-side error) is invisible to the test suite.

**2026-05-11 cross-schema-organization-audit.** Audit across all 11 non-core products surfaced exactly 0 REAL_BUG, 0 WORKS_BY_LUCK after the PF fix. Only one digest-shape service (PF `monthly_narrative`) fetched `organizations`; sister digest services (daily-life `weekly_review`, mailing `campaign_debrief`, ERP `metas_digest`, core `audit_digest`) either don't reach `organizations` (their digests are product-data-only) or live in core and therefore correctly default to public. Therapy `ai_pipeline.py` was already using the explicit-DI `core_db` shape pre-audit. Per-product code count for the cross-schema-reach concern remains 0 outside the natural call sites.

## Storage buckets — never public

**The bug (erp-certidoes, 2026-09-17).** `erp-certidoes` (102 objects / 21MB of
CPF-bearing certidões — full names, debt/restriction findings) and
`erp-geral` were declared `public = true` in
`products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql` +
`011_storage_buckets.sql`. Anyone with (or able to guess/enumerate) an
object URL could fetch a certidão fully unauthenticated.

**🔴 "RLS is on" is NOT "the data is protected" the moment a bucket is
public.** `storage.objects` had RLS ENABLED, with 17 policies (`erp_storage_*`
— org-scoped via `(storage.foldername(name))[1]`, see § RLS self-reference
recursion above for the pattern shape). They gave **ZERO** protection,
because Supabase Storage serves a **public** bucket's objects via the
`/object/public/{bucket}/{path}` route — a route that does not evaluate
`storage.objects` RLS **at all**. Only the `/object/authenticated/...` and
`/object/sign/...` routes do. A public bucket routes every request around
the policy engine entirely; the 17 policies were evaluated for exactly zero
of the leaked requests.

**The rule is absolute, no exception (owner directive, 2026-09-17): zero
public buckets, in every product, forever.** Not "avoid where possible" —
there is no legitimate reason to declare `public = true` on this platform.
The sanctioned alternative, always:

```sql
-- ❌ never — bypasses storage.objects RLS entirely
INSERT INTO storage.buckets (id, name, public) VALUES ('x', 'x', true);

-- ✅ private bucket + a short-TTL SIGNED url minted AT READ TIME, never persisted
INSERT INTO storage.buckets (id, name, public) VALUES ('x', 'x', false);
```
```python
# app/services/storage_service.py (erp-imobiliario) or
# noctusai_lib.integrations.storage + documento_store.py's `.url()` /
# contratos_service.url_versao (social-wiring — the canonical
# Protocol+Fake+Real adapter shape; see § Migrations above for why
# consuming an existing mechanism beats inventing a second one)
signed = storage.get_signed_url(path, categoria="certidoes")  # or storage.signed_url(bucket=..., key=path, expires_in_seconds=300)
```

Persist the storage **PATH**, never a URL — a public URL is the leak; a
signed URL goes stale the moment its TTL passes and would freeze a broken
link into the row forever. Mint the signed URL fresh, on every read, from
the persisted path.

**Two-legged gate, both blocking, neither skippable, NEITHER has any
override — the ONE deliberate exception to this codebase's own
accept-with-rationale convention (owner directive: "not even with my
explicit permission... find THE CORRECT AND SECURE WAY"):**

- **Static** — `noctus.dev.compliance.check_storage_bucket_public`
  (pre-commit, severity `critical`). Three legs: (A) a migration's
  `INSERT INTO storage.buckets` / `UPDATE storage.buckets SET public =
  true`; (B) any `get_public_url(` / `getPublicUrl(` call site anywhere on
  the platform — that method only makes sense against a public bucket, so
  there must be zero call sites in the end state; (C) a runtime
  `create_bucket(...)` passing `public=True`. Scoped to the files STAGED in
  the current commit (the same idiom `check_conflict_markers` uses) — so
  the IMMUTABLE historical declarations in 001/011 (which will say `true`
  forever, by design — see § Migrations above) never re-block a future
  commit that never touches them. A full-tree audit (`paths=None`) still
  finds them, deliberately, and is therefore NOT wired into any
  whole-platform sweep (a permanently-red gate gets ignored).
- **Live** — `noctus.dev.check_storage_no_public_buckets`, wired into
  `noctus.dev.predeploy_check` as the `storage_bucket_public` leg. Queries
  the RUNNING `storage.buckets` table; FAILS on any `public = true` row,
  and FAILS — never skips — when it cannot verify at all (mirrors the
  `schema_exposure` leg's identical fail-closed posture: "we couldn't
  check" must never read as "it's fine"). Read-only by construction: no
  `apply` / `confirm` / any write parameter exists anywhere in this tool —
  the fix (flip the bucket private) is a manual `ALTER`/dashboard action
  the operator runs directly, never something a tool could be asked to
  undo later.

**Forward fix, immutable history.** `products/erp-imobiliario/backend/
migrations/048_storage_no_public_buckets.sql` is the codified live fix —
NOT an edit to 001/011 (a migration is a record of what WAS applied, never
a mutable snapshot of current intent; see § Migrations above). It flips
both buckets private (idempotent `UPDATE ... WHERE public = true`), adds
`certidao_resultados.arquivo_path`, and backfills the pre-existing
public-URL rows into that path column, clearing `arquivo_url`.

**Wider surface, flagged not fixed (2026-09-17 audit — in scope only where
clearly wrong):** none of the platform's 5 bucket declarations (erp × 2,
social-wiring × 3) set `file_size_limit` or `allowed_mime_types` at the
bucket level — every product relies entirely on its own application-layer
`validate_file`/`ALLOWED_TYPES`/`MAX_FILE_SIZE` checks. A fleet-wide
gap, not erp-specific; flagged for a future slice, not expanded into this
one.

## Schema-wide grants — `anon` gets USAGE only, never a blanket table grant

**The bug (2026-09-20).** `products/seed/backend/migrations/001_seed.sql`
used to read:

```sql
GRANT USAGE ON SCHEMA seed TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON TABLES TO anon, authenticated, service_role;
```

Propagated verbatim via `templates/product-seed/` into 9 product schemas
(`academia_de_reciclagem`, `adconnect`, `agents`, `community`, `daily_life`,
`igig`, `orbity`, `p_studio`, `social_wiring`). Rule 6 above already says it:
*"Every product schema is PostgREST-exposed with default grants, so ANY
table without RLS is readable/writable over REST"* — this is that rule's
worst-case realization. RLS is the ROW-level gate; a table-level GRANT is
what lets a role reach a table **before RLS is even consulted**. In the
live `social_wiring` schema, 4 out-of-band backup tables
(`_leads_backup_20260902`, `_clientes_orfaos_backup_20260902`,
`_cliente_merges_backup_20260902`, `_atendimentos_backup_20260902` —
21,567 rows of names/emails/birthdates) were created directly against the
database, outside any migration, and therefore never got an RLS policy.
Because the schema-wide grant gave `anon` full table privileges by
default, they were readable **and writable** by the unauthenticated
PostgREST role from the moment they existed. Contained live via a direct
`REVOKE` + `ENABLE ROW LEVEL SECURITY` against those 4 tables; the fix
below is the ROOT closure so the class cannot recur.

**The canonical shape** (`products/seed/backend/migrations/001_seed.sql`,
post-fix):

```sql
GRANT USAGE ON SCHEMA seed TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA seed TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA seed TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;

-- A table that genuinely needs anonymous access re-grants it EXPLICITLY,
-- per table, with a comment saying why:
GRANT SELECT ON seed.status_pagina TO anon;  -- todos_veem_producao: page-visibility flags, no PII
```

`anon` gets schema USAGE (routing only, required by PostgREST) and
**nothing** at the table level by default. `service_role` gets ALL — the
trusted server-side role, already bypasses RLS. `authenticated` gets
SELECT/INSERT/UPDATE/DELETE — real signed-in users, gated per table by
RLS. **4 products already used a narrower — but still not canonical —
shape** (`erp`, `therapy`, `personal-finance`: `SELECT, INSERT, UPDATE,
DELETE` to `anon` + `authenticated` on `ALL TABLES`, reserving `ALL` for
`postgres`/`service_role`) — narrower than the seed's old `ALL`-to-anon
default, but still a **blanket** table grant naming `anon`, which the
canonical shape forbids outright. Fixing those 3 products is out of scope
for the 2026-09-20 lockdown (flagged, not fixed — same "wider surface,
flagged not fixed" posture as the storage-buckets audit above).

**Forward fix, immutable history.** Each of the 9 inheriting schemas got
one new migration (`REVOKE ALL ON ALL TABLES IN SCHEMA <s> FROM anon` +
the matching `ALTER DEFAULT PRIVILEGES ... REVOKE ALL ... FROM anon`, plus
an explicit per-table re-grant for any audited anon exception) — **never**
an edit to `001_*.sql` (a migration is a record of what WAS applied, never
a mutable snapshot of current intent; see § Migrations above). `community`
had already closed its own exposure earlier
(`007_drop_anon_write_policies.sql` / `008_pagamentos.sql` /
`009_whatsapp.sql`, after `aplicacoes_insert_anon`'s `WITH CHECK (true)`
was found to let anyone POST arbitrary pre-approved rows) — its lockdown
migration restates the REVOKE for consistency and deliberately does
**not** re-open `status_pagina` for `anon` (that surface was closed on
purpose; re-opening it here would be a regression, not a fix).

**Audited anon exceptions, per schema (grep every migration for `TO anon`,
`FOR ... anon`, and TO-less/PUBLIC-role policies before writing the
REVOKE):** the only exception across all 9 schemas is
`status_pagina.todos_veem_producao` (or, on `p_studio`, the equivalently-
shaped `status_pagina_select_producao`) — a deliberate TO-less (PUBLIC,
`anon` included) SELECT policy over page-visibility flags, no PII.
`agents`' `session_transcript_entries` / `app_integration_config` /
`runtime_settings` already carry an explicit per-table `REVOKE ALL ...
FROM anon, authenticated`; `social_wiring`'s `mc_brand_owners_select_own_org`
is TO-less but keys on `auth.jwt() ->> 'org_id'`, which is `NULL` for an
unauthenticated request, so `anon` already got zero rows via RLS
regardless of the grant. Every other policy across the 9 schemas is
`TO authenticated` / `TO service_role`, or RLS-enabled with zero policies
(implicit deny) — REVOKE-only is safe everywhere else.

**Static gate** — `noctus.dev.compliance.check_schema_wide_anon_grant`
(pre-commit, severity `critical`, no allowlist — same posture as
`check_storage_bucket_public`). Two legs: (A) `GRANT ... ON ALL TABLES IN
SCHEMA <s> TO ...anon...`; (B) `ALTER DEFAULT PRIVILEGES IN SCHEMA <s>
GRANT ... ON TABLES TO ...anon...`. Deliberately sequence-exempt (`ON ALL
SEQUENCES` is not matched — no row data, and every product already grants
`anon` sequence USAGE by design). Comments are stripped before matching
(`noctusai_lib.testing.migration_parser`), so a migration's own prose
citing the historical vulnerable shape (exactly what every lockdown
migration's header does) can never trip its own keeper. Diff-scoped to
the files STAGED in the current commit — same reasoning as
`check_storage_bucket_public`: the pre-fix `001_*.sql` files stay on disk
forever, so a full-tree audit (`paths=None`) is deliberately NOT wired
into any blocking gate (it still finds them, on purpose, for an ad-hoc
audit — including the 3 narrower-but-still-blanket erp/therapy/
personal-finance grants above).

**Advisory (not blocking) sibling** —
`noctus.dev.compliance.check_table_has_rls`: flags a `CREATE TABLE` with
no matching `ENABLE ROW LEVEL SECURITY`, static or the dynamic
`DO $$ ... FOREACH t IN ARRAY ARRAY[...] LOOP EXECUTE format('ALTER TABLE
%I ENABLE ROW LEVEL SECURITY', t) ... END $$;` shape (`social-wiring`
065/101) AND the `FOR t IN SELECT unnest(ARRAY[...])` shape
(`erp-imobiliario` 001's "RLS for expansion tables" block). A naive
literal grep sees neither dynamic form and reported 66 "exposed" tables in
`social_wiring` when the live number was 4 — this detector resolves both
by correlating the loop's array literal with its `EXECUTE format(...)`
call by loop-variable name, statement-scoped via `_walk_statements` so an
inner `;` inside the `DO $$ ... $$` body never confuses it. Validated
fleet-wide: zero false positives against every `campanhas`/`permuta*`
table (the shape that produced the 66-vs-4 incident) and against erp's
40-table `FOR ... unnest` loop; 3 genuine remaining findings platform-wide
(a `social_wiring.tool_call_audits` cross-file gap closed by a LATER
migration — a known per-file scope limitation — and 2 real
`knowledge_extractor` tables with no RLS at all). Not wired into any
CLI flag or blocking gate — a regex scan is not a SQL parser, and a THIRD
dynamic-batch shape this scanner doesn't yet recognise would be a false
positive, not a false negative; promote to blocking only after widening
coverage further.

## Provisioning

Trigger `on_license_change` fires when `public.product_licenses` changes. Auto-provisions product defaults (initial teams, seed rows, roles) in the product's schema.

---

See also:
- `../../CONTEXT/backend/04-DATABASE.md` — per-schema table inventory
- `backend.md` — repository pattern, N+1 discipline
