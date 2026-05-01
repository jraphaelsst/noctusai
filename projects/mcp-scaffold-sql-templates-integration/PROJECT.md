# MCP Scaffold ↔ SQL Templates Integration — Project Document

> **What this project is.** Wire `noctusai_lib.domain.sql_templates` (landed 2026-05-01 by Wave A's `sql-templates-absorption`) into `mcp/noctusai/tools/scaffold.py` so new product scaffolds emit migrations that use the canonical helpers automatically.
>
> **Filed pending interrogation.** No phase plan yet — the scaffold tool's current shape needs auditing before deciding how the integration lands.

- **Created:** 2026-05-01
- **Last updated:** 2026-05-01
- **Status:** 📋 **FILED** — pending Phase 0 interrogation. No phases designed yet.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `mcp-scaffold-sql-templates-integration` (subject=mcp-scaffold-sql-templates, intent=integration)
- **Project location:** `projects/mcp-scaffold-sql-templates-integration/` (cross-product / platform-infra — touches mcp/ and the scaffold convention)
- **Related docs:**
  - `seed/backend/lib/noctusai_lib/domain/sql_templates.py` — the helpers to integrate.
  - `mcp/noctusai/tools/scaffold.py` — the scaffold tool that needs the integration.
  - `KB § PATTERNS/database-rls.md § Authoring helpers` — convention doc.
  - Parent: `projects/execution-workflow-codequality-rollout/PROJECT.md` Phase 4 absorptions queue.

---

## 1. Context & Purpose

Wave A (`projects/sql-templates-absorption/`, closed 2026-05-01) landed pure-string-emission helpers for the SQL DDL conventions every product schema reuses (`SET search_path` prelude, `updated_at` function + trigger, RLS subquery policy). The seed module is tested but unused at authoring time — the scaffold tool that bootstraps new products still emits SQL via inline templates that haven't been audited against the new helpers.

This project closes the loop: when a future agent runs `noctusai_scaffold_product` (or the CLI equivalent), the generated `001_<schema>.sql` file uses the helpers so the conventions can't drift.

---

## 2. Confirmed constraints

_(filled at Phase 0 interrogation)_

---

## 3. Design principles

_(filled at Phase 0 interrogation)_

---

## 3a. Seed-first analysis (REQUIRED — fill at Phase 0)

_(checklist filled at Phase 0; see `templates/PROJECT-TEMPLATE.md § 3a` + `KB § GUIDES/seed-first-design.md`)_

---

## 4. Scope

**In scope (provisional, pending Phase 0 audit):**
- Audit `mcp/noctusai/tools/scaffold.py` — what does it currently emit for migrations?
- If it inlines SQL templates, refactor to import from `noctusai_lib.domain.sql_templates`.
- If it doesn't generate migrations today, decide whether scaffolding should add that responsibility.
- Update tests for the scaffold tool to assert helper-emitted output.

**Out of scope:**
- Rewriting existing product migrations (replay-log rule).

---

## 6. Implementation phases

### Phase 0 — Audit + interrogation

- [ ] Read `mcp/noctusai/tools/scaffold.py` end-to-end.
- [ ] Read `mcp/noctusai/tests/test_scaffold.py` (if exists).
- [ ] Determine current SQL-emission behavior.
- [ ] Decide refactor shape (drop-in import vs deeper restructure).
- [ ] Interrogate user on open questions; fill §2 / §3 / §3a.

### Phase 1+ — Implement

_(designed at Phase 0)_

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-01 | **Project filed.** Spawned by `sql-templates-absorption` Phase 3 close as the deferred scaffold-tool integration. No phases designed yet — Phase 0 interrogation needed before scoping. | Claude Opus 4.7 |
