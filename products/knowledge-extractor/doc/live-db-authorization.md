# Authorization + runbook — create the live DB & apply migrations

> **Status: AUTHORIZED.** **Authorizer:** rapha (supervisor). **Date:** 2026-05-23.
> **Scope:** knowledge-extractor agent on the `methodology-dev` branch.
> **Source of truth for the schema:** `backend/migrations/001_knowledge_extractor.sql`.

This note operationalizes the migration header line "*Applied by: supervisor (not
automated — see /CLAUDE.md §6 step 5)*" and brings persistence forward from
absorption-time into the current step-2 work: you are **authorized to create the
live database and apply the migration now.**

---

## 1 · What is authorized (and what is NOT)

**Authorized:**
- Apply `backend/migrations/001_knowledge_extractor.sql` to the live database.
- Enable the `pgvector` extension (once per project).
- Add the `knowledge_extractor` schema to the project's PostgREST **exposed
  schemas** so the REST/RPC adapter can reach it.
- Add the Supabase keys to `.env.example` (contract) + your local `.env` (values).
- Verify, smoke-test, and report.

**NOT authorized (would need a fresh, explicit "yes"):**
- Creating a **new** Supabase project. (Decision is locked — see §2.)
- Any DDL/DML against **other schemas** in the target project (the `public`
  fleet tables and every other product's data are off-limits — read-only, hands-off).
- Pushing/merging `main` (CLAUDE.md §1 — `main` is protected).
- Committing any secret (service-role key, PAT) — `.env` only, gitignored.

---

## 2 · Target — LOCKED decision

**The `knowledge_extractor` schema goes inside the EXISTING `noctusai` Supabase
project.** Do **not** create a new project.

Why (this is the noc-methodology reasoning, encode it):
- noc's Supabase architecture is fixed at **2 active projects** — `noctusai`
  (whole fleet, RLS on) + One Permutas (legacy). A 3rd active project exceeds the
  free 2-active cap; the supervisor will not pay for it. (See
  the memory `reference_supabase_projects_architecture`.)
- The migration is already **schema-isolated** (`CREATE SCHEMA knowledge_extractor`,
  every object namespaced). That is precisely the shape designed to coexist inside
  a shared project — the same way noc products share one project with
  schema/RLS isolation.
- It is **absorption-forward**: when noc absorbs this repo
  (`products/knowledge-extractor/`), the schema is already in place — CLAUDE.md
  §6 step 5 becomes a no-op.

---

## 3 · Step-by-step runbook (respects noc methodology)

> Cross-cutting rules that apply to **every** step below: **No silent errors**
> (no `except: pass`, no unverified "✓"; quote the command + result). **Codebase
> is source of truth** (the `.sql` file is authoritative — apply its exact bytes,
> never hand-type DDL into the dashboard). **MCP-first** (drive Supabase through
> the MCP, not manual dashboard SQL, so the action is reproducible). **Verify in
> the real shape** (a migration "applied" is a claim until a live query proves the
> tables + RPC exist).

### Step 0 — Preconditions
- `git branch` → confirm you are on **`methodology-dev`** (never `main`).
- Read CLAUDE.md §1 (inherited noc rules) + this note in full.
- Confirm the Supabase MCP is available. Keep-list (CLAUDE.md §7) includes
  `supabase`. Use either the managed `mcp__claude_ai_Supabase__*`
  (`list_projects` / `apply_migration` / `execute_sql` / `list_tables` /
  `get_project_url` / `get_advisors`) **or** noc's self-hosted connector
  (`supabase.project.list` / `supabase.migration.apply` / `supabase.db.query`).
  If neither is wired here, STOP and ask the supervisor to enable it — do not
  paste SQL into the dashboard by hand as a workaround.

### Step 1 — Resolve the target project (don't hardcode)
- List projects via the MCP and select the one named **`noctusai`**. Capture its
  **project ref** + **URL** (`get_project_url`). Do not guess the ref.
- Sanity-check you have the right one: it should already contain the `public`
  fleet tables (`list_tables`). If it looks empty or unfamiliar, STOP and ask.

### Step 2 — LGPD / RLS review BEFORE applying (noc is RLS-first)
The `noctusai` project runs **RLS on every table** for LGPD. `001` currently
isolates via **schema grants** (anon reaches data only through the `match_kb`
RPC; only `service_role` can read/write `kb_*`), not `ENABLE ROW LEVEL SECURITY`.
Make this an **explicit, documented decision — never silent**:
- **Option A (accept-with-rationale):** these two tables hold the supervisor's
  *own* course-methodology content (not multi-tenant customer PII), and anon is
  already RPC-gated. Record the acceptance in a one-line note in `doc/` +
  (post-absorption) `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md`.
- **Option B (full RLS parity):** `ALTER TABLE … ENABLE ROW LEVEL SECURITY` on
  both tables, make `match_kb` `SECURITY DEFINER` (so the RPC still works under
  RLS), and add the minimal anon read policy the RPC needs. Reference
  `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`.
- Pick one, write it down, then proceed. (Recommended: A for now, with a
  follow-up to B if this schema ever holds anything beyond the user's own docs.)

### Step 3 — Apply the migration (mirror-the-file)
- Apply via the MCP `apply_migration` (managed) / `supabase.migration.apply`
  (noc connector). Migration **name = `001_knowledge_extractor`**. Migration
  **body = the exact contents** of `backend/migrations/001_knowledge_extractor.sql`
  (read the file, pass it verbatim — the file is the source of truth, the MCP
  apply mirrors it byte-for-byte). This enables `pgvector`, creates the schema,
  both tables, the HNSW index, the `match_kb` RPC, and the grants.
- If `pgvector` needs superuser enablement first, the migration's
  `CREATE EXTENSION IF NOT EXISTS vector;` handles it on Supabase (the
  service-role/owner can enable it). If it errors, surface the exact error —
  don't silently skip it.

### Step 4 — Expose the schema to PostgREST (required, easy to miss)
The adapter calls `/rest/v1/kb_chunk` and `/rest/v1/rpc/match_kb` against schema
`knowledge_extractor`. PostgREST only serves schemas in its **exposed-schemas**
list (default `public, graphql_public`). Add `knowledge_extractor`:
- Supabase Studio → Project Settings → API → "Exposed schemas" → add
  `knowledge_extractor`; **or** via SQL the equivalent
  `ALTER ROLE authenticator SET pgrst.db_schemas = 'public, graphql_public, knowledge_extractor';`
  then `NOTIFY pgrst, 'reload config';`.
- Without this, the REST/RPC calls 404 even though the migration applied — a
  classic "DB looks fine, app still fails" boundary gap. Verify in Step 5.

### Step 5 — Verify in the live shape (no assumptions)
Quote each result; a green run is the only proof:
- `list_tables` (or `supabase.db.list_tables`) shows `knowledge_extractor.kb_document`
  + `knowledge_extractor.kb_chunk`.
- The `match_kb` function exists:
  `SELECT proname FROM pg_proc WHERE proname = 'match_kb';` returns a row.
- REST reachability: a `match_kb` RPC call with a zero/dummy 1536-vector returns
  `[]` (empty, not a 404) — proves Step 4 worked.
- `get_advisors` (managed) — check for new security/RLS advisories from your
  Step-2 choice; address or document them.

### Step 6 — Wire credentials (least privilege; secrets stay local)
The adapter reads **`SUPABASE_URL`** + **`SUPABASE_SERVICE_ROLE_KEY`**
(`backend/app/integrations/vectors/supabase_adapter.py`).
- Add both keys to **`.env.example`** as the contract (empty values + a comment),
  under a new `# ─── Supabase (vector store) ───` block. Commit-worthy (no secret).
- Put the real values in **`.env`** only (gitignored — confirm with
  `git check-ignore .env`). **Never commit the service-role key.**
- ⚠️ **Least-privilege flag (LGPD):** the `noctusai` project's `service_role`
  key bypasses RLS across the **whole fleet**, not just `knowledge_extractor`.
  Holding it in this dev tool's `.env` grants this process full fleet access.
  Acceptable **only** because this runs **locally** (the user's machine, not
  deployed) on the user's own data. Surface this explicitly to the supervisor.
  If this tool is ever deployed, switch to a dedicated schema-scoped Postgres
  role + key (do NOT ship the fleet service-role key). Record the decision.

### Step 7 — Smoke the adapter end-to-end
- Swap the pipeline's `FakeVectorStore` → `SupabaseVectorStore` (DI seam) and run
  the smallest real path: ingest one tiny doc → embed → `match_kb` returns it
  ranked. Confirm the row landed (`kb_chunk` count > 0) and similarity is sane.
- `cd backend && pytest` must stay green (fakes still pass with no network).
  Quote the result.

### Step 8 — Future schema changes = `002+` (single-001 rule)
- `001` is now applied to a **live** DB. Per noc's single-001 rule, `001` builds
  the full schema and is edited-in-place **only pre-live**. From now on, every
  change ships as a **new numbered migration** (`002_*.sql`, `003_*.sql`),
  applied via the MCP and kept in `backend/migrations/` (mirror-the-file). Never
  edit `001` to mutate the live DB.
- New mutable tables → add an `updated_at` trigger (on absorption this becomes
  `noctusai_lib.sql.updated_at_trigger`; until then, inline it).

---

## 4 · Commit / push discipline (noc + this repo's §1)
- **Never auto-commit.** When the supervisor asks to commit: `git status` first,
  explicit-path `git add` only (never `git add .` / `-A`), and only files YOU
  authored. The `.env.example` + this `doc/` note are commit-worthy; `.env` is not.
- **`main` is protected** — all of this lands on `methodology-dev`; pushing or
  merging `main` needs a separate explicit "yes."
- Report at the end: what was applied, the verification output (Step 5), the
  RLS decision (Step 2), the least-privilege note (Step 6) — loudly, no silent ✓.

---

## 5 · Quick reference
| Thing | Value |
|---|---|
| Target project | `noctusai` (existing — resolve ref via MCP `list_projects`) |
| Schema | `knowledge_extractor` |
| Migration file (source of truth) | `backend/migrations/001_knowledge_extractor.sql` |
| Objects | `kb_document`, `kb_chunk` (vector 1536), HNSW idx, `match_kb` RPC |
| Adapter env vars | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| Adapter REST paths | `/rest/v1/kb_chunk` (schema `knowledge_extractor`), `/rest/v1/rpc/match_kb` |
| Edge function | `supabase/functions/kb-search` |
| Branch | `methodology-dev` (never `main`) |
| MCP | managed `mcp__claude_ai_Supabase__*` or noc `supabase.*` connector |
