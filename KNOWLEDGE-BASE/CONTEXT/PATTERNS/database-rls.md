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

## Provisioning

Trigger `on_license_change` fires when `public.product_licenses` changes. Auto-provisions product defaults (initial teams, seed rows, roles) in the product's schema.

---

See also:
- `../../CONTEXT/backend/04-DATABASE.md` — per-schema table inventory
- `backend.md` — repository pattern, N+1 discipline
