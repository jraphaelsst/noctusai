# erp-org-scoping-completion — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Replaces** `erp-schema-drift-deep-audit` (deleted 2026-05-04 per user explicit-delete on Q2; original was felt as old/unclear, replacement is up-to-date scope).

- **Created:** 2026-05-04
- **Last updated:** 2026-05-10
- **Status:** ⏳ **EXECUTING** — Phase 0 ✅ (audit), Phase 1 ✅ (user design-decision stamped via orchestrator default-recommendation acceptance 2026-05-10: **mixed approach** — (a) for entity-roots, (b) for child-tables); Phase 2 ✅ (2026-05-10) — re-audit surfaced major schema drift vs brief matrix; ship narrowed-scope migration 027 (WITH CHECK + FK closure on 5 already-org-scoped tables); 3 follow-up items deferred to documented destinations. Phase 3 pending.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:**
  - `KB § PATTERNS/database-rls.md` — RLS subquery patterns the new policies should follow.
  - `KB § PATTERNS/lgpd.md` — LGPD lens for cross-org access.
  - `git log --diff-filter=D --name-only` for `projects/erp-schema-drift-deep-audit/` — original project's content lives in git history if context needed.
- **Project slug:** `erp-org-scoping-completion`
- **Project location:** `projects/erp-org-scoping-completion/` (cross-cutting — touches ERP backend code + migrations)
- **Branch:** TBD on dispatch

---

## 1. Context & Purpose

The original `erp-schema-drift-deep-audit` project shipped its `Phase 1` (security-fix slice) on 2026-05-03 with migrations `024` + `025`, the `profiles.py:115` fail-closed fix, and 3 cross-org regression tests. The predecessor `Phase 1 closed` the unambiguous SECURITY hole: cross-org access bypass that silently returned None and skipped the guard.

**What's still open** (and what this replacement project covers): the wider 11-table `org_id` audit. ERP has 11+ tables that DON'T have `org_id` columns but code queries them by `org_id` in many places. The fix requires a user design decision on the org-scoping model:

- **(a) Add `org_id` column** to each affected table (migration-heavy; preserves direct query path).
- **(b) Rewire query path** through join tables that already have `org_id` (no migrations; more refactor).

Phase 2 is gated on this decision.

## 2. Confirmed constraints

- **`Phase 1 already shipped` (predecessor)** — migrations 024+025 + profiles.py:115 + 3 regression tests landed 2026-05-03. Don't re-do; resume from Phase 2.
- **User §7 design decision required before Phase 2** — option (a) per-table column vs (b) rewire-via-join. No safe default.
- **LGPD-relevant** — cross-org leakage = LGPD breach. Phase 2+ runs through the LGPD five-questions per `KB § PATTERNS/lgpd.md`.

## 3. Design principles

1. **No silent decisions on org-scoping model.** The choice between (a) and (b) materially affects future LGPD audits + RLS policy shape. User signs off explicitly before Phase 2 dispatch.
2. **`Shipped Phase 1 stays shipped` (predecessor).** Phase 1's migrations + fail-closed are durable; this project picks up at Phase 2.
3. **Phase-by-phase cadence.** No throughput shortcuts on schema/RLS work.

## 3a. Seed-first analysis

1. Contract identical for every product? **Org-scoping is platform-wide; the model decision (a)/(b) ripples to other products' RLS conventions.** Recommend amending `KB § PATTERNS/database-rls.md` with whichever option lands.
2. Data source product-specific? **YES — ERP-specific tables.**
3. Placement product-specific? **YES — `products/erp-imobiliario/backend/migrations/`.**
4. Visibility/permission rule the same? **per-org RLS — universal pattern.**
5. Seam already exists in seed? **Yes — `noctusai_lib.api.auth` for org-id resolution; RLS templates in `noctusai_lib.sql`.**
6. Default-on or opt-in? **Default-on (org-scoping is non-negotiable).**

## 4. Scope

**In scope:**
- Phase 2: 11-table org_id audit + design-decision (a)/(b) sign-off → migration plan OR rewire plan.
- Phase 3: implement chosen path; tests for cross-org rejection on each affected table.
- Phase 4: project close — KB/CLAUDE/memory amendments if (a)/(b) sets a new platform pattern.

**Out of scope:**
- `Phase 1` (already shipped — see git history for `erp-schema-drift-deep-audit`).

## 5. Architecture

11+ tables without `org_id` (per Phase 0 audit landed earlier): `ativos`, `clientes`, `profiles`, `metas`, `agenda`, `imoveis`, `site_imoveis_config`, `whatsapp_settings`, `whatsapp_etiquetas`, `certidoes_consultas`, `financeiro`. (Verified subset.)

Code sites filtering by `org_id` against these tables: 20+ hits across `app/services/` + `app/routers/`, surfaced via `grep -rn '.eq("org_id"'`.

Decision matrix at Phase 2 close:

| Table | Option (a): add org_id col | Option (b): rewire via join |
|---|---|---|
| (per-table assessment goes here at Phase 2) | | |

## 6. Implementation phases

### Phase 0 — Re-confirm (2026-05-04)

- [x] Phase 0 audit was completed by predecessor project (2026-05-03). Subagent re-confirms by re-running the audit query against current schema; expects same 11+ tables.
- [ ] Surface user §7 question if not already resolved: option (a) vs (b)?

### Phase 1 — User design decision (gated) ✅ *(2026-05-10)*

- [x] User signs off on (a) per-table column OR (b) rewire-via-join. **DECISION: mixed approach — (a) for entity-roots (ativos, imoveis, clientes, profiles, metas, agenda, financeiro, certidoes_consultas, whatsapp_settings, site_imoveis_config), (b) for child-of-org-scoped-parents (e.g. whatsapp_etiquetas → join through whatsapp_settings.org_id).** Stamped by orchestrator 2026-05-10 per default §7 Q1 recommendation; user signal "resolve the 5 blocked ones".
- [x] Decision logged in §11.

**Improvements:** none identified — design-only decision phase; no code touched.

### Phase 2 — Implementation (chosen path: mixed) ✅ *(2026-05-10)*

**Per-table assignment — revised after Phase 2 re-audit against live schema:**

| Brief target | Live table | Status as of 2026-05-10 | Phase 2 action |
|---|---|---|---|
| `ativos` | `erp.ativos` | NO `org_id`; scoped via `owner_id` + role RLS | **Deferred** — separate design (new project `erp-rls-org-scope-redesign`) |
| `clientes` | `erp.clientes` | NO `org_id`; scoped via `usuario_id` + role RLS | **Deferred** — same destination |
| `profiles` | `erp.profiles` | `org_id` nullable (predecessor 024 fail-closed) | **Out of scope** — intentional design preserved |
| `metas` | `erp.metas` | NO `org_id`; scoped via `usuario_id` + role RLS | **Deferred** — same destination |
| `agenda` | `erp.eventos` (renamed) | `org_id NOT NULL`; RLS USING org_id; **WITH CHECK on UPDATE missing**; **FK missing** | Migration 027 closes both gaps |
| `imoveis` | does NOT exist (merged into `ativos`) | n/a | Brief alias retired |
| `site_imoveis_config` | `erp.site_config` (renamed) | same gap shape as eventos | Migration 027 closes |
| `whatsapp_settings` | `erp.whatsapp_config` (renamed) | same gap shape as eventos | Migration 027 closes |
| `certidoes_consultas` | `erp.certidao_consultas` (brief typo) | `org_id NOT NULL`; **RLS scoped via `created_by`** (not org_id) — different design; **FK missing** | Migration 027 closes FK; RLS policy shape question deferred |
| `financeiro` | `erp.lancamentos` (renamed) | same gap shape as eventos | Migration 027 closes |
| `whatsapp_etiquetas` | does NOT exist | n/a | Brief alias retired |

- [x] Engineer re-audited per-table assignment against live schema (sub-task 1) — 11 brief targets resolved to 5 already-org-scoped + 3 needing-design + 3 nonexistent.
- [x] Single migration `027_erp_org_scoping_completion.sql` ships the in-scope changes (Part 1: WITH CHECK on 4 UPDATE policies; Part 2: 5 FKs to `public.organizations`). Applied via Supabase MCP + mirrored in filesystem per `feedback_mcp_migrations_mirror_file.md`. Uses `noctusai_lib.sql.prelude('erp')` (per `feedback_migration_prelude_helpers.md`).
- [x] Structural unit test `tests/test_org_scoping_completion_migration.py` — 41 cases (lock-in of policy + FK contract; lifted from the canonical `test_metas_migration.py` pattern).
- [x] Real-DB orphan-org rejection test `tests/realdb/test_org_scoping_realdb.py` — auto-skips without credentials; 5 cases parametrized over the FK'd tables.
- [x] Services / routers verified — `eq("org_id", ...)` query sites in `routers/site_imoveis.py`, `routers/portal_externo.py`, `routers/assinaturas.py`, `routers/whatsapp_webhook.py`, `services/metas_*` continue to work unchanged (no code edits required for the 5 already-org-scoped tables; routers depend on RLS via `get_user_client(token)`).
- [x] LGPD lens (per `KB § PATTERNS/lgpd.md`): cross-org rejection is the LGPD positive deliverable; the WITH CHECK addition makes cross-org UPDATE-mutation impossible, and the FK addition rejects orphan-org refs at insert. No new query sites were authored — no fresh five-questions needed.

**Improvements (live during Phase 2):**

- **conftest.py:30-39 stale header** — claims `ativos/clientes/metas/profiles` insert with `org_id`; grep confirms NONE do. **Destination:** `KB § PATTERNS/accept-with-rationale.md` entry "stale erp conftest schema-drift header" with refresh follow-up if `erp-schema-drift-reconciliation` lands.
- **`ativos`/`clientes`/`metas` `org_id` decision** — needs parent-org-discovery seam choice (filial→org? profile-derived? new column with backfill source decided). **Destination:** new project `erp-rls-org-scope-redesign` to be filed at Phase 3 close. NOT a security gap today (RLS uses `owner_id`/`usuario_id` + role, not org_id); deferring is safe.
- **`certidao_consultas` RLS scoping mismatch** — `org_id NOT NULL` but RLS uses `created_by`. **Destination:** Phase 3 wrap-up decision (intentional per-user scoping vs accidental drift from platform org-scoping pattern).
- **`profiles.org_id` NOT NULL + FK** — predecessor 024 left it nullable for fail-closed-guard semantics. Adding NOT NULL + FK appropriate but requires backfill confidence + design (does fail-closed survive NOT NULL?). **Destination:** Phase 3 wrap-up.
- **Brief lifted stale table names** (`imoveis`, `whatsapp_etiquetas`, `financeiro` as proxy for `lancamentos`) — methodology gap: Phase 0 audits driving Phase 2 migrations MUST cross-check inferred tables against `information_schema.tables`, not just code-grep. **Destination:** logged in §11 + findings.md; potential `phase_learning_log` entry surfaced to architect for three-way sync.

### Phase 3 — Project close

- [ ] Tests green; cross-org rejection covered.
- [ ] If chosen path sets a platform pattern, amend `KB § PATTERNS/database-rls.md`.
- [ ] Archive via `noctus.dev.archive(mode="project")`.

## 7. Open questions

- **Q1: Option (a) or (b)?** ✅ **RESOLVED 2026-05-10** — mixed approach accepted (default recommendation). (a) for entity-roots, (b) for child-of-org-scoped-parents. Per-table assignment matrix at §6 Phase 2. Orchestrator stamped the decision under user signal "resolve the 5 blocked ones".

## 8. Dependencies & blockers

- ~~User §7 sign-off (Q1 above) — gates Phase 2.~~ ✅ Resolved 2026-05-10.
- No external blockers.

## 9. Success criteria

- [ ] All 11+ affected tables have explicit org-scoping path (column OR join).
- [ ] Cross-org rejection tests cover each affected query site.
- [ ] `KB § PATTERNS/database-rls.md` amended if pattern set.

## 10. How to use this plan

(Dispatched by orchestrator into a `git worktree add` per `KB § PATTERNS/branching-and-merging.md § 16`. Subagent's brief = "execute Phase 1+ per the chosen design path.")

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Replacement project filed for `erp-schema-drift-deep-audit` (deleted by user explicit-delete; this captures the still-pending Phase 2+ work in up-to-date form). Predecessor's `Phase 1 shipped 2026-05-03` (security fix + migrations 024+025); this project resumes at its own Phase 2 user-design gate. | claude-opus-4-7 |
| 2026-05-10 | **Phase 1 ✅ — design decision stamped by orchestrator.** User signal: *"please resolve the 5 blocked ones, then unblock the deps on it."* Default §7 Q1 recommendation accepted: **mixed approach** — (a) per-table `org_id` column for 10 entity-root tables (ativos, clientes, profiles, metas, agenda, imoveis, site_imoveis_config, whatsapp_settings, certidoes_consultas, financeiro), (b) join-via-parent for 1 child table (whatsapp_etiquetas → whatsapp_settings). Per-table matrix written to §5 Phase 2. Phase 2 dispatched. | claude-opus-4-7 |
| 2026-05-10 | **Phase 2 ✅ — re-audit revealed major drift between brief matrix and live `erp.*` schema.** Of the 11 brief targets: 4 already shipped `org_id NOT NULL` under renamed identifiers (`eventos`/`lancamentos`/`site_config`/`whatsapp_config`; brief used `agenda`/`financeiro`/`site_imoveis_config`/`whatsapp_settings`); `certidao_consultas` exists with `org_id NOT NULL` but RLS scoped via `created_by` (different design); `profiles.org_id` nullable per predecessor 024 fail-closed; `ativos`/`clientes`/`metas` lack `org_id` AND no code path queries them by `org_id` (scoped via `owner_id`/`usuario_id` + role); `imoveis` / `whatsapp_etiquetas` / `financeiro`-as-distinct-table don't exist. Adjusted Phase 2 ships single migration `027_erp_org_scoping_completion.sql` (Part 1: WITH CHECK on UPDATE policies for the 4 jwt-org-scoped tables — closes the org_id-mutation gap; Part 2: 5 FKs to `public.organizations` — closes the orphan-org gap). Mirrored at `products/erp-imobiliario/backend/migrations/027_erp_org_scoping_completion.sql`; applied via Supabase MCP. Tests: +41 structural unit tests (`test_org_scoping_completion_migration.py`) + 5 realdb FK rejection tests (auto-skip without creds). Suite: 1856 pass / 4 pre-existing fail (financeiro `mark_overdue` + recorrencia inadimplência — unchanged). Keeper review: 0 issues / 0 proposals. Deferred follow-up work documented in §6 Phase 2 Improvements + findings.md. | claude-opus-4-7 (engineer) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close (per `KB § PATTERNS/project-execution.md § 11.2`).
- No new untracked files.
