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

## Migrations

Numbered SQL files in `products/<name>/backend/migrations/001_*.sql`, `002_*.sql`, etc. These files are the **authoritative replay log** — the DB is mutable state and can be wiped; the files are what rebuild it.

**Rules:**
- Idempotent: use `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` where Postgres supports them.
- RLS enabled in the same migration that creates the table. No "enable RLS later" follow-ups.
- Seed data, if any, goes in a separate `00X_seed_*.sql` file.
- **Next number wins:** pick the next unused number in the product's `migrations/` directory (e.g. `016_metas_domain.sql` after `015_invitations.sql`).

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

## Provisioning

Trigger `on_license_change` fires when `public.product_licenses` changes. Auto-provisions product defaults (initial teams, seed rows, roles) in the product's schema.

---

See also:
- `../../CONTEXT/backend/04-DATABASE.md` — per-schema table inventory
- `backend.md` — repository pattern, N+1 discipline
