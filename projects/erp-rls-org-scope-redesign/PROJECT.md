# erp-rls-org-scope-redesign — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 🟡 **READY FOR EXECUTION (parked on user design decision).** Filed under user signal *"create projects for deferrals/parks that happen along the way."* Engineer D's `erp-org-scoping-completion` Phase 2 close (commit `6a1abdf`) surfaced 3 tables (`ativos`, `clientes`, `metas`) that are NOT a security gap today but represent a per-product RLS-design divergence worth resolving via a deliberate design choice.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `erp-rls-org-scope-redesign` (root `projects/` — cross-cutting ERP RLS design)
- **Related docs:**
  - `KB § PATTERNS/database-rls.md` — canonical RLS patterns
  - `archive/projects/...//erp-org-scoping-completion` (when archived) — predecessor; its Phase 2 close surfaced these gaps
  - migration `027_erp_org_scoping_completion.sql` — closed WITH-CHECK + FK gaps on 5 tables; left these 3 as design-pending

---

## 1. Context & Purpose

Engineer D's `erp-org-scoping-completion` Phase 2 close (commit `6a1abdf`) re-audited the brief's 11-table matrix against live schema and found:

- **5 already-org-scoped tables** (eventos, lancamentos, site_config, whatsapp_config, certidao_consultas) → fixed in migration 027 (WITH CHECK + FK closure).
- **3 design-pending tables**: `ativos`, `clientes`, `metas` — these have NO `org_id` column today. They are scoped via `owner_id` / `usuario_id` (per-user) + role RLS (admin sees all). No code path filters them with `.eq("org_id", ...)`, so they are NOT a security gap.
- **3 nonexistent tables** in current schema (imoveis, whatsapp_etiquetas, financeiro under different names) → brief aliases retired.

**The design question for the 3 deferred tables:** should they have `org_id` for defense-in-depth (org-scoping cuts off the "user belongs to multiple orgs" footgun and tightens RLS pre-image), or should they stay per-user-scoped (current design — admin role still has org-scoping through the `profiles` table join)?

This isn't urgent. The current design works. But the divergence between "5 tables org-scoped" and "3 tables user-scoped" is the kind of inconsistency that compounds — every new product agent has to learn which convention applies where. Standardize, or document the divergence as intentional.

Additionally, Engineer D surfaced `certidao_consultas` RLS scoping mismatch: `org_id NOT NULL` but RLS uses `created_by = auth.uid()` — same shape as the 3 deferred tables. Same design question.

## 2. Confirmed constraints

- **NOT a security gap today.** 0 cross-org leaks; no `.eq("org_id", ...)` code paths for these tables; per-user RLS holds.
- **Defense-in-depth is the only motivation for change.** Decisions should reflect that — not "fix the bug."
- **Migration 027 already shipped.** This project picks up at design-decision, not Phase 0 audit.
- **No in-flight engineer on ERP backend.** Safe to dispatch when scheduled.

## 3. Design principles

1. **Document the divergence OR standardize it.** Either valid; the ANTI-pattern is "leave inconsistent without explicit reasoning."
2. **Defense-in-depth gates the decision.** If adding `org_id` to ativos/clientes/metas would catch a real failure mode in any product (not just ERP), formalize. If it's pure pattern hygiene, accept-with-rationale.
3. **Migrations follow `noctusai_lib.sql.prelude` + `updated_at_trigger`** (per `feedback_migration_prelude_helpers.md`).

## 3a. Seed-first analysis

- **Cross-product?** YES — RLS-design convention ripples to PF, therapy, daily-life. The canonical pattern doc is `KB § PATTERNS/database-rls.md`.
- **Per-product code count for cross-cutting concern?** 0 — the seed-lib already provides RLS templates.
- **Seam in seed?** YES — `noctusai_lib.sql` + `noctusai_lib.api.auth.make_get_current_user_org` (the org-id-source-of-truth at the application layer).

## 4. Scope

- **In scope:**
  - User decides: standardize to org_id-scoped OR document the divergence as intentional per-user-scoping.
  - If standardize: add `org_id` columns to ativos, clientes, metas + WITH CHECK + FK + LGPD lens.
  - If document: amend `KB § PATTERNS/database-rls.md` with the "per-user-scoped vs org-scoped" decision matrix (when to pick each).
  - Resolve `certidao_consultas` RLS-shape inconsistency (org_id NOT NULL but RLS by created_by — same question).
- **Out of scope:**
  - The 5 tables migration 027 already handled.
  - The `profiles.org_id` NOT NULL + FK decision (separate concern; predecessor 024 left nullable for fail-closed).

## 5. Architecture / Data Model

The 4 design-pending tables (ativos, clientes, metas, certidao_consultas) share the same shape:
- User-derived scoping today
- No code path treats them as org-scoped via `.eq("org_id", ...)`
- Migration 027 closed FKs but NOT WITH CHECK (because the tables aren't UPDATE-mutated against org_id in code)

## 6. Implementation phases

### Phase 0 — User design decision

- [ ] Surface §7 Q1 to user: standardize (a) OR document divergence (b)?
- [ ] Log decision in §11.

### Phase 1 — Implementation (chosen path)

- [ ] If (a): 1 migration adding `org_id` to 4 tables + backfill from `users.org_id` via the user-id seam + WITH CHECK + FK + RLS update.
- [ ] If (b): KB amend documenting the divergence + decision matrix + the 4 tables tagged with the rationale.

### Phase 2 — Close

- [ ] Tests green; cross-org rejection covered (if (a)).
- [ ] KB amend (regardless of path — pattern doc gets the lesson).
- [ ] Archive via `noctus.dev.archive(mode="project")`.

## 7. Open questions

- **Q1: Standardize (a) or document divergence (b)?** **Recommendation: (b) document divergence** — these tables are intentionally per-user-scoped (one user can own multiple `ativos` / `clientes` independently of org), org-scoping would force a join through profiles.org_id which is the current RLS shape via role. Adding org_id is pure pattern hygiene at risk of breaking the per-user mental model. **Defer to user.**

## 8. Dependencies & blockers

- User §7 Q1 sign-off — gates everything.
- No in-flight engineer on ERP backend.

## 9. Success criteria

- [ ] Design decision documented.
- [ ] KB pattern doc reflects the chosen path.
- [ ] If (a): tests green + cross-org rejection covered.

## 10. How to use this plan

Dispatched when user signals decision on Q1. Single-engineer brief.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer D's `erp-org-scoping-completion` Phase 2 close surfaced 3 tables (ativos/clientes/metas) + 1 (certidao_consultas) as design-pending — NOT a security gap today, but pattern divergence worth resolving via deliberate design choice. **Status: parked on user §7 Q1 sign-off.** Default recommendation: (b) document divergence (per-user scoping intentional). | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
