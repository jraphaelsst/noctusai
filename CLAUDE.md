# CLAUDE.md · v2.1

<!--
  Version:   2.1 (compaction)
  Date:      2026-05-02
  Author:    Raphael (joaoraphaelsst@gmail.com) — product owner, platform architect
  AI coauthor: Claude Opus 4.7 (1M context) — iterative collaboration
  Shift:     v2.0 was instructive but every rule had ballooned into a paragraph.
             v2.1 trims each rule to its minimum viable form. The wealth of
             detail (caught-instance audit trails, load-bearing implementations,
             anti-pattern examples) lives in the KB anchors each rule points to.
             Every rule and every pointer is preserved.
  Enforced:  scripts/pre-commit verifies every pointer resolves before any commit.
-->

> **What this file is.** Claude's **outer map**. Loaded every session. Holds
> (a) the behavioral rules Claude obeys every turn, and (b) where to jump in
> `KNOWLEDGE-BASE/` for depth. **No specs or technical depth here** — depth
> lives in the KB. If you find yourself writing an architecture paragraph
> in this file, it belongs in `KNOWLEDGE-BASE/CONTEXT/` with a pointer here.
>
> **What this file is NOT.** A tutorial, a changelog, a spec sheet, or a
> reference manual. It's a thin router with behavioral rules on top.
>
> When you can't find something, open **`KNOWLEDGE-BASE/INDEX.md`** — the
> authoritative catalog of every KB doc.
>
> **Cross-model DRY rule.** `CLAUDE.md` and `OPENAI.md` are sibling outer
> maps for different model families, not separate sources of truth. Shared
> methodology lives in `KNOWLEDGE-BASE/`; model-specific root files stay
> lean and point to the same KB. KB-first, then sync the pointer in both
> outer maps.

---

## 0 · How this file is organized

| Section | Job | Use |
|---|---|---|
| **§1 Engineering Philosophy** | Behavioral rules. | Read every session. When a rule applies, it wins. |
| **§2 The Map** | Pointers into `KNOWLEDGE-BASE/` grouped by topic. | Open the linked file *on-demand* — never pre-load. |
| **§3 When to read what** | Task → "open this first" lookup. | Scan before starting work. |
| **§4 Sync rule** | How CLAUDE.md and KB stay aligned. | Enforced by pre-commit hook. |

Each rule is terse on purpose: rule + key pointer. Long-form reasoning, history, caught instances, and worked examples all live in the KB anchor at the end of each rule.

---

## 1 · Engineering Philosophy

Behavioral rules. Long-form reasoning lives at **`KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`** and the per-rule pointers below.

> **Vocabulary.** These are our **methodology** — not a "doctrine". Use *methodology / rule / principle / convention / pattern / working agreement*. Avoid "doctrine / doctrinal / doctrinally" — the framing is hierarchical and runs counter to how this team operates. → `KB § 01-PHILOSOPHY.md § Vocabulary — methodology, not doctrine`

- **Seed is the skeleton. First rule.** `seed/` owns structural bones; products are organs that attach via **runtime import**, not copy-paste. Backend: `create_product_app()` from `noctusai_seed`. Frontend: `createProductApp()` from `@noctusai/seed`. Every customization flows through a NAMED seam (`standard_routers=[...]`, `authProvider`, `Layout`, `lifespan_*`, …). A customization NOT flowing through a named seam is a **structural fork** — refactor to an existing seam, extend a seam, or formalize a new one. **Don't ask whether to use the seed; the seed IS the approach.** Run the **4-question Practical Decision Test** before any structural change. Non-compliance is never grandfathered: file a `<product>-seed-wiring` project (located at `products/<product>/projects/<product>-seed-wiring/`) or accept-with-rationale per § Seed Contract § 4. → `KB § 03-SEED-ARCHITECTURE.md § Seed as Skeleton` + `§ Seed Contract` + `§ Practical decision test` + `§ Control-plane vs. consumer products` + `KB § 01-PHILOSOPHY.md § Seed first — Always § Compliance`
- **MCP toolkit reviews after every change (observation-only).** `python mcp/noctusai/cli.py --review` after modifying code. Detects compliance issues deterministically; LLM (OpenAI, `OPENAI_API_KEY`) authors a proposal per issue. Keeper proposals → `products/<product>/proposals/`. Project-scoped proposals → the project's own `proposals/` folder. **The tool NEVER modifies code.** Loop: change → review → triage → apply manually → commit. (Old auto-fix `--heal` retired — text rewrites corrupt code, string-match checks rot.) → `KB § 06-AGENTS.md`
- **No incomplete commits.** Backend and frontend at the same maturity. "Scaffolded" is not "complete." If one side is real and the other is a placeholder, stop and flag.
- **No quick fixes.** A fix that touches multiple products for the same reason is at the wrong level — go up to seed / shared lib / config and let it propagate. Thirty minutes on the root beats five minutes on a patch that generates future work.
- **No workarounds — and no monkey-patching, in production OR tests.** Use the real API/SDK/framework. **The rule applies to test code too.** Never `monkeypatch.setattr(our_module, "our_guard", _noop)` — that test no longer exercises the guard. Right shape: seed real underlying data (e.g. `ai_consent` rows for `noctusai_lib.ai.consent.require`); use dependency injection for write side-effects (optional kwarg, default real client, tests pass mock); read inserts via `MockRequestBuilder.inserted_payloads`. `unittest.mock.patch.object(<external_integration>, ...)` for **external services** (LLM APIs, transcription, network) is fine — that's mocking the boundary. → `KB § PATTERNS/testing.md § Consent-guard product conftest pattern § Service-layer guards` + `KB § 01-PHILOSOPHY.md § No workarounds`
- **Estimate off evidence, not structure.** Before offering A/B/C, a session-size, or "this is quick" — open the files the change would actually touch. If it would affect `seed/`, a shared lib, a factory, or any cross-cutting layer, read that code first. If a shallow estimate is already on the table and reality is bigger, stop and re-scope as a proper project. → `KB § 01-PHILOSOPHY.md § Estimate off evidence`
- **DRY.** Three similar blocks is a pattern — extract it. Single authoritative source for every piece of logic, every config, every doc.
- **Componentize everything.** Check **`KB § 04-SHARED-LIBRARY.md`** before writing anything new. If another product will need it, build it shared from day one.
- **Narrow-read first.** Default to **structure before bodies** for any file >200 lines or whenever you don't know the exact range. Outline via grep on top-level symbols (or a small-`limit` `Read`), fetch bodies only for what you'll actually edit, cite, or reason about. Whole-file reads are reserved for short files, full reviews/rewrites, or content-is-structure files (configs, migrations). *Most edits need 1-2 functions; whole-file reads burn 5-10K tokens of irrelevant context per turn.* AST outline tools forthcoming. → `KB § PATTERNS/agent-reading-discipline.md § Narrow-read first`
- **Explore-agent delegation.** Delegate to the **Explore subagent** when answering requires **3+ targeted greps, multi-file walking, or open-ended discovery** ("where is X defined / which files reference Y", broad audits). Use direct `Read` / `grep` when the exact file path or symbol is already known. *The trigger is research breadth, not product count* — 3 directories in one product is a delegate; one file across 5 products is direct. The Explore subagent runs in its own context window and returns a synthesized digest, so the raw search output never lands in the main conversation; for one-shot lookups the spin-up cost outweighs the savings. Prefer dedicated `noctusai_*` scan tools (refs, recurrence, status) when available — those are the digest. → `KB § PATTERNS/agent-reading-discipline.md § Explore-agent delegation`
- **Replication-to-seed symmetry — fires at READ/PLAN/DESCRIBE time.** *The trigger is LANGUAGE, not action.* Phrasings like **"per-product X"**, **"mount across N products"**, **"for each product Y"**, **"every product gets its own ___"** ARE the slip — wherever they appear (your reply, project docs, user prompt). The right per-product code count for a cross-product concern is **zero** — products opt in via a kwarg or auto-on convention. When reading a PROJECT.md that uses replication framing, challenge the framing in Phase 0; don't parrot it. **Authoring-time corrective: every `PROJECT.md` MUST include §3a Seed-first analysis (six-question checklist + per-product code-count litmus) BEFORE §6 phase planning** — even single-product projects (the seed is every product's skeleton). A PROJECT.md lacking §3a is a bug. → `KB § PATTERNS/project-execution.md § The replication-to-seed symmetry rule` + `KB § GUIDES/seed-first-design.md` + `templates/PROJECT-TEMPLATE.md § 3a`
- **Module-scope imports.** Python imports go at the top of the file. Don't defer into function bodies unless solving a documented circular dependency.
- **FastAPI dep factories defer config to request time.** Routers decorate at import-time but `create_product_app(...)` wires `configure_X_module(...)` later — a fail-fast factory crashes router imports. Pattern: module-level slots default `None`, `configure_X_module(...)` populates them, factory returns dep without checking, dep reads slots at request time. Ship a `bind_X_module_to_mock(mock_sb)` helper in `noctusai_lib.testing` for product conftests. Reference adopters: `noctusai_lib.ai.consent.consent_required` + `noctusai_lib.llm.budget.configure_budget_module`. → `KB § PATTERNS/backend.md § FastAPI dependency factories with module-level injection`
- **Phase 0 audits are the highest-leverage work — *expand loudly* on invalidation.** Every project's first phase reads the actual files / runs the actual commands / queries the actual DB before any code lands. **When findings invalidate §6, REVISE §6 in-place + log in §11 + continue.** Do NOT silently absorb; do NOT halt indefinitely. **STOP is still required** for hard-to-reverse + multi-agent-shared actions, security/LGPD design-class discoveries, or scope changes the user explicitly asked to confirm. Phase 0 takes 5-30 min; mis-scopes it prevents take 2-8 hr. → `KB § PATTERNS/project-execution.md § 2.5 Phase 0 audits`
- **The execution workflow — top-to-bottom rigor, every project.** Canonical loop: SCAFFOLD (§3a seed-first) → PRE-PHASE (§2.5 audit + absorption scan) → EXECUTE one phase (§2.6 active robustness review, §2 live ticking, mid-phase scan checkpoints, §6↔§11 self-check) → PHASE-END VERIFICATION (tests + keeper + scan rerun + KB sync + §6↔§11) → CLOSE-PHASE (synthesize improvements → ONE bundled proposal → apply-inline-then-delete → **commit the phase locally, no push**) → PROJECT-END VERIFICATION (cross-product builds + backend tests + MCP tests + full keeper + sync verifiers + final scan + three-way sync + end-of-work summary) → PROJECT CLOSE (folder deletion → **final commit + push as the literal last step**). **Code-quality bias**: when picking between quick and thorough, pick thorough. The discipline at each step is non-negotiable. → `KB § PATTERNS/project-execution.md § 0 The execution workflow`
- **Commit per phase, push at project close — the only auto-commit/push gates.** Two new gates amend the never-auto-commit rule: (1) at the end of every phase, stage the phase's diff with explicit file paths and create a phase-scoped local commit (no push); (2) at project close (after folder deletion), stage anything still uncommitted and `git push`. Push is the literal last step of project implementation — it makes the work visible to other agents and pins it in remote history. Never push partway through. The "explicit-delegation" carve-out: when the user gives a project-close instruction like "commit and push the project", this gate runs without re-confirmation; outside the project-close gate, the never-auto-commit rule still binds. Always `git status` first; never `git add .` / `-A`. → `KB § PATTERNS/project-execution.md § 0 The execution workflow`
- **The recurrence rule — formalize at threshold.** **N=2 → triage time** (formalize / refactor / accept-with-rationale; decision recorded; silently moving on forbidden). **N=3+ → MUST formalize** (extract into seed-lib / framework / shared library; minimum response = file a follow-up project; silently shipping the 4th instance forbidden). When the rule fires: STOP, name the pattern, decide the destination, file or apply, resume. Companion to language-time, execution-time, and retroactive triggers — the four together fence DRY-into-seed at every observation moment. → `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
- **Absorption-search is a standing duty in product code.** Whenever editing a product's services / routers / hooks / components — *even for an unrelated task* — keep the recurrence rule active and run the MCP scans before walking away from the file. Three modes: `noctusai_scan_cross_product_helpers` (function/class NAMES across products), `noctusai_scan_service_line_recurrence` (verbatim service/router LINES across products), `noctusai_scan_recurrence` (entry/conftest/config line replication). Use BEFORE writing a new helper/DTO/service shell; use AFTER a cleanup pass as the calibration check. → `KB § 06-AGENTS.md § Cross-cutting utilities § Absorption-search trio`
- **Active robustness review during execution.** Phase execution is *also* a proactive inspection pass on the code you touch + its surroundings. Eyes open: silent error swallows (`except: pass`), stale TODOs, untyped `any`/`unknown`, async races, hardcoded magic numbers, missing trust-boundary validation, fields populated-and-never-read, mock-vs-real divergence. Capture findings live in the phase's `**Improvements:**` block — in-the-act, NOT saved for later. Apply low-risk inline, scope-creep refactors are forbidden. *Empty improvements after a non-trivial multi-file phase ≈ inspection skipped.* → `KB § PATTERNS/project-execution.md § 2.6 Active robustness review`
- **§6 ↔ §11 consistency self-check before claiming a phase is done.** Before any reply that claims a phase is closed, verify all five: (1) §6 header carries `✅`, (2) every sub-task `- [x]`, (3) `**Improvements:**` block filled (or `none identified.`), (4) §11 entry exists, (5) `improvements.md` regenerated. If any of 1-5 is missing, the phase is NOT closed. Live state never lags the narrative. → `KB § PATTERNS/project-execution.md § 2 Self-check before claiming a phase is done`
- **Projects live next to the code they touch — three valid locations, scope-scoped.** `projects/<slug>/` for **cross-product / seed / platform-infra / not-yet-a-product**; `products/<product>/projects/<slug>/` for **single-product scope**; `core/projects/<slug>/` for **core-platform-control-plane** (auth, SSO, billing, orgs, entitlements). Every product has a `projects/` folder (`.gitkeep` if empty), including core. Slugs are globally unique — the MCP tool resolves `project="<slug>"` to whichever folder. Each folder holds `PROJECT.md` + `improvements.md` + `proposals/`. **Always start by copying `templates/PROJECT-TEMPLATE.md`.** Slug convention: `<subject>-<intent>`. **Interrogate the user before drafting** (clarifying questions, constraints, edge cases — never assume). **Write for a zero-context reader** — inline §1 context, quote user in §2, file paths in §5, every §7 Open Question paired with an evidence-backed recommendation, §10 commands copy-paste ready. **During execution, tick tasks live** (`- [ ]` → `- [x]`, saved immediately). **Cadence is phase-by-phase by default** — pause and wait for "continue" between phases unless the user asks for throughput. **Phase headers carry status icons** (no icon = pending, `⏳` = partial, `✅` = complete, `❌` = blocked). **Improvement flow is capture-then-synthesize**: drop in-the-act bullets in `**Improvements:**` during the phase, then at end-of-phase BEFORE flipping `✅`, file ONE bundled proposal via `noctusai_file_proposal(project="<slug>", ...)` with `Origin: project:<slug>:phase-<N>`. Then flip header, run `python mcp/noctusai/cli.py --improvements <PROJECT.md path>`. → `KB § 01-PHILOSOPHY.md § Projects are living` + `KB § PATTERNS/project-execution.md §1` + `KB § PATTERNS/proposals-and-improvements.md`
- **Triage at decision time — formalize / refactor / accept-with-rationale.** Every divergence from ideals lands on one of three explicit outcomes: **formalize** (extend framework/seed), **refactor** (align with contract), or **accept-with-rationale** (catalog the entry in `KB § PATTERNS/accept-with-rationale.md` — the durable register that survives project folder deletion). "Accept" is a real landing — paperwork keeps it from going silent. Recurrence flips prior `accept` outcomes toward `formalize`. The workflow evaluates itself as it goes — no upfront ideological rulings. → `KB § 01-PHILOSOPHY.md § Triage at decision time` + `KB § PATTERNS/accept-with-rationale.md`
- **No silent errors — always explicit fix opportunities.** No `except: pass`, no silent degraded fallbacks, no deferred items without a named destination, no "verification: ✓" when the tail showed red. Ambiguity is a silent error — ask. Absence of findings is a claim — quote the command that confirms it. Load-bearing impl: `MockSupabaseClient(validate_schema=True)` default + `check_mock_schema_validation` keeper detector. → `KB § 01-PHILOSOPHY.md § No silent errors`
- **Clean folder — every artifact has a home.** Repo root holds only platform-wide files (CLAUDE.md, README.md, docker-compose.yml, .gitignore, scripts pointer). Audits / proposal drafts / design notes / scratch `.md` files belong inside a project folder as first-class reference artifacts quoted by `PROJECT.md §1/§5`. Stray root file → scaffold the project, move the file in, inline load-bearing bits into PROJECT.md, delete root copy. Prefer ONE umbrella project over N scattered one-finding folders. → `KB § PATTERNS/project-execution.md § 11 Clean-folder principle`
- **Auto-improvement at phase close — apply, don't ask.** At end of phase, read the `**Improvements:**` block and **apply every in-scope, low-risk, self-contained item INLINE in the same session — no `noctusai_file_proposal` artifact, no user prompt**. Mark each item as `applied` or `deferred → <destination>` in the block; that block + §11 ARE the audit trail. **Defer** items that are out-of-scope or need their own project (scaffold the follow-up from `templates/PROJECT-TEMPLATE.md` — broken pointers forbidden). **Still file a formal proposal** when items need scheduling, explicit human approval (security/public-API), or batch-review across deliverables; that path keeps §4b's apply-inline-then-delete mechanics. End every non-trivial reply with a list-shaped summary (applied / deferred / verification). Phase cadence is unaffected — auto-improvement closes the current phase; the next phase still waits for user "continue". *Default protocol for every agent*, not a user override. → `KB § PATTERNS/proposals-and-improvements.md § 4d + § 4c`
- **Finish the session — verify, don't assume.** End-of-session checklist: `cd products/<touched>/frontend && npx vite build`; `cd products/<touched>/backend && pytest`; `cd mcp/noctusai && pytest tests/` if MCP-toolkit changed; report any regression. Don't mark "done" while a build or test is red. *Every in-session change must land on green.*
- **Gamification is subtle.** Rankings, points, progress bars — discrete; with a ⓘ icon explaining the formula; tied to real business activity (never "logged in today"-style rewards). → `KB § 07-GAMIFICATION.md`
- **Three-way sync — KB, CLAUDE.md, and memory move together.** Any rule/methodology/behavior change lives in **all three layers simultaneously**: (1) topical KB file + `INDEX.md`, (2) CLAUDE.md pointer, (3) memory file under `~/.claude/projects/.../memory/` + `MEMORY.md`. **Triggers**: a `feedback_*.md` memory file added/modified → KB section + CLAUDE.md pointer must exist; a KB rule change → memory entry filed (if user-preference-shaped) + CLAUDE.md pointer updated; a CLAUDE.md rule change → KB depth + memory must back it. **NEW rule ordering**: KB-first, then CLAUDE.md pointer, then memory entry. **Amending an existing rule**: all three layers same session. Tiny typo-only fixes are exempt. `verify-kb-sync.sh` catches dangling KB↔CLAUDE.md pointers but not missing memory entries — that's the agent's discipline. Also: `mcp/noctusai/README.md` if tooling changed. → `KB § 01-PHILOSOPHY.md § Docs stay in sync`
- **MCP migrations mirror the file.** Any DDL applied via Supabase MCP (`apply_migration` / `execute_sql`) MUST also exist as a numbered migration file at `products/<name>/backend/migrations/NNN_<name>.sql` — commit both together. The DB is mutable state; migration files are the authoritative replay log. → `KB § PATTERNS/database-rls.md`
- **Supabase MCP is the agent's tool — use it proactively.** When a task needs DB access (apply migration, audit schema, verify RLS, seed/inspect data), execute it directly through `mcp__claude_ai_Supabase__*`. **Never** ask the user to paste SQL. Blanket approval stands. Use `apply_migration` for DDL; `execute_sql` for read-only inspection.
- **`CLAUDE.md` vs `KNOWLEDGE-BASE/` — the token budget rule.** This file is loaded every turn; keep it lean. The KB is loaded on-demand; put depth there. If CLAUDE.md grows, context degrades.
- **Every product has `README.md` + `MASTER-PROMPT.md`.** README for humans browsing the repo; MASTER-PROMPT for agents building features. Both mandatory from day one. → `KB § GUIDES/new-product.md`
- **LGPD-first, always.** Whenever code touches personal data (identity, financial, clinical, behavioral, derived embeddings, …), the LGPD lens is the **first** lens — before functionality, performance, UX. Clinical text is Art. 11 sensitive data; never leaves Therapy schema without a documented basis, never hits a response cache. When in doubt: `noctusai_lgpd_flag(...)` — records to `LGPD-WARNINGS.md`, notifies the user, **does not block**. The flag is a checklist item, ticked when resolved. → `KB § PATTERNS/lgpd.md`
- **Webhook receivers verify before any side effect.** Every inbound webhook in this monorepo authenticates the payload's origin via `noctusai_lib.security.webhook_signatures` (HMAC `sha256=…` / bare hex / Svix protocol) before parsing the body, writing to the DB, or dispatching downstream work. Stripe ships its own verifier — use the SDK, don't wrap it. Constant-time compare always; replay-window enforcement when the provider sends a timestamp. Bypass on unset secret = WARNING + 200 (early-dev affordance only); production sets the secret. → `KB § PATTERNS/webhook-signatures.md` + `KB § 04-SHARED-LIBRARY.md § security/`

---

## 2 · The Map

Pointers into `KNOWLEDGE-BASE/`. Open *on-demand* — never pre-load. If nothing here matches, open `KNOWLEDGE-BASE/INDEX.md`.

### Architecture & context — "what the platform is"
- **Product landscape** (products, schemas, ports, stack) → `KB § 02-LANDSCAPE.md`
- **Seed framework** (factories, layer split, how products inherit) → `KB § 03-SEED-ARCHITECTURE.md`
- **Shared library catalog** (check before building anything) → `KB § 04-SHARED-LIBRARY.md`
- **Infrastructure** (ports, deploy, self-hosted services) → `KB § 05-INFRASTRUCTURE.md`
- **MCP dev toolkit** (review loop, proposals, CLI) → `KB § 06-AGENTS.md`
- **Gamification philosophy** (subtle rankings, ⓘ icons, Metas as reference) → `KB § 07-GAMIFICATION.md`

### Patterns — "how we write it"
- **LLM access** (multi-provider via `noctusai_lib.llm`; never `from openai import`; `cache=False` for clinical text) → `KB § 04-SHARED-LIBRARY.md § llm/`
- **Backend patterns** (auth, SSO, RLS, N+1, service layer) → `KB § PATTERNS/backend.md`
- **Frontend patterns** (TanStack Query, hooks-per-entity, mobile-first) → `KB § PATTERNS/frontend.md`
- **Testing** (three-layer discipline + auth boundary) → `KB § PATTERNS/testing.md`
- **Database & RLS** (subquery `auth.uid()`, `search_path`, policy templates) → `KB § PATTERNS/database-rls.md`
- **Environment / `.env`** (single root, VITE_ security rule, CORS_ORIGINS) → `KB § PATTERNS/environment.md`
- **Notifications** (proxy, shape, shared `NotificationBell`) → `KB § PATTERNS/notifications.md`
- **Shared-library conventions** (privatize / absorb / rename, catalog tool) → `KB § PATTERNS/shared-library-conventions.md`
- **Project execution** (phase-header checkboxes, live ticking, improvements block, retrospective tool, slug convention, tests-land-with-implementation, write-for-zero-context-reader) → `KB § PATTERNS/project-execution.md`
- **Proposals & improvements** (two-system protocol, ONE bundled proposal per phase, PROPOSAL-TEMPLATE.md fields, promote boundary) → `KB § PATTERNS/proposals-and-improvements.md`
- **LGPD awareness** (keeper principle, the five questions, `noctusai_lgpd_flag` tool) → `KB § PATTERNS/lgpd.md`
- **Logging convention** (level guide, no-`# silent-ok` rule, bootstrap-time pattern, correlation IDs) → `KB § PATTERNS/logging.md`
- **Seed-lib layout** (6 layers — primitives/config/testing/integrations/domain/api — decision tree) → `KB § PATTERNS/seed-lib-layout.md`

### Guides — "how to do a task"
- **First-time setup** (clone → install → run) → `KB § GUIDES/setup.md`
- **Creating a new product** (mandatory files + checklist) → `KB § GUIDES/new-product.md`

### Per-product details — open only the product you're working on
- Backend specs → `KB § backend/{01-CORE, 02-ERP, 03-PF, 04-DATABASE, 05-AI-FEATURES, 06-THERAPY, 07-AUTH-SECURITY, 08-DAILY-LIFE}.md`
- Frontend specs → `KB § frontend/{01-CORE, 02-ERP, 03-PF, 04-THERAPY}.md`

### Agent / skill / workflow design
- Entry point → `KB § INSTRUCTIONS/00-MASTER.md`

### Two maps, two audiences
- **This file** (`CLAUDE.md`) — outer map, every session, lean.
- **`KNOWLEDGE-BASE/INDEX.md`** — inner map, by-topic and by-situation tables.

---

## 3 · When to read what

| Situation | Start here |
|---|---|
| Fresh session, need orientation | `KB § AGENT-CONTEXT.md` + `KB § 02-LANDSCAPE.md` |
| Writing backend code | `KB § PATTERNS/backend.md` + `KB § backend/0X-*.md` |
| Writing frontend code | `KB § PATTERNS/frontend.md` + `KB § frontend/0X-*.md` |
| Writing a migration | `KB § PATTERNS/database-rls.md` + `KB § backend/04-DATABASE.md` |
| Adding a shared component | `KB § 04-SHARED-LIBRARY.md` (check first — it might exist) |
| Creating a new product | `KB § GUIDES/new-product.md` + `KB § 03-SEED-ARCHITECTURE.md` |
| Starting a new project | Copy `templates/PROJECT-TEMPLATE.md` into `projects/<slug>/`, `products/<product>/projects/<slug>/`, or `core/projects/<slug>/` per `KB § PATTERNS/project-execution.md §1`. Never hand-roll. |
| Changing env vars | `KB § PATTERNS/environment.md` |
| Writing tests | `KB § PATTERNS/testing.md` |
| Adding a `try/except` (production code) | `KB § PATTERNS/logging.md` (level guide, no-`# silent-ok` rule) |
| Adding / amending a keeper detector | `KB § PATTERNS/testing.md § Regression-test-the-detector` (CI gate) |
| Adding a helper to `noctusai_lib` | `KB § PATTERNS/seed-lib-layout.md` (6-layer model + decision tree) |
| Touching gamified UI | `KB § 07-GAMIFICATION.md` |
| Designing an agent / MCP / skill | `KB § INSTRUCTIONS/00-MASTER.md` |
| Anything not listed | `KB § INDEX.md` |

> Throughout this file `KB § X` is shorthand for `KNOWLEDGE-BASE/X`.

---

## 4 · Sync rule

CLAUDE.md and `KNOWLEDGE-BASE/INDEX.md` stay in sync — when you add, rename, or delete any KB file or folder, both get updated.

**Pre-commit hook enforces it** (`scripts/pre-commit` → installed by `scripts/install-hooks.sh`). On every commit:
1. Syncs `products/seed/` → `templates/product-seed/` if staged.
2. Runs `scripts/update-kb-counts.py` — regenerates auto-derived count blocks.
3. Runs `scripts/verify-kb-sync.sh` — **blocks the commit** if any pointer in this file doesn't resolve, or any KB doc is missing from `INDEX.md`.

Manual runs:
- `bash scripts/verify-kb-sync.sh`
- `python scripts/update-kb-counts.py [--check]`
- `python mcp/noctusai/cli.py --verify-kb-sync`

Install hooks in a fresh clone: `bash scripts/install-hooks.sh` (full setup: `bash scripts/setup.sh`).

Bypass (rarely correct): `git commit --no-verify`.

---

<!-- Version history
  2.1 (2026-05-02) — compaction: each rule trimmed to minimum viable form;
                     deep elaborations preserved at the KB anchors. Every
                     rule and every pointer retained. Token budget recovered.
  2.0 (2026-04-18) — instructive rewrite: each rule what/what-not/why/deepen.
                     Added §0 organization table.
  1.0 (2026-04-18) — pointer/map split: specs moved to KNOWLEDGE-BASE/.
  0.x  — legacy: everything in one long file; spec + rules conflated.
-->
