# CLAUDE.md · v3.0 — router

> **What this file is.** Auto-loaded every session. Two jobs: (a) the universal behavioral rules Claude obeys every turn, (b) routing pointers into `CLAUDE/<topic>.md` (topical rules, on-demand) and `KNOWLEDGE-BASE/` (depth, on-demand). Kept lean on purpose — the auto-loaded budget compounds across every reply.
>
> **What this file is NOT.** A tutorial, changelog, spec sheet, manual, or rule body container. Bodies and depth go elsewhere. If you find yourself writing >80 words on a single rule here, push the long-form into KB and shorten the rule to a pointer.
>
> **When you can't find a rule:** open `CLAUDE/<topic>.md` (sibling of this file) for topical rules, or `KNOWLEDGE-BASE/INDEX.md` for depth.

---

## 0 · How this file is organized

| Section | Job | Use |
|---|---|---|
| **§1 Universal rules** | Behavioral rules that apply regardless of task. | Read every session. |
| **§2 The Map** | Pointers into `CLAUDE/<topic>.md` and `KNOWLEDGE-BASE/`. | Open *on-demand* — never pre-load. |
| **§3 When to read what** | Task → "open this first" lookup, including topical `CLAUDE/*.md` files. | Scan before starting any non-trivial work. |
| **§4 Sync rule** | How CLAUDE.md, topical files, KB, and memory stay aligned. | Enforced by pre-commit hook. |

---

## 1 · Universal rules

Each bullet is rule + one-clause why + pointer. Bodies / examples / slip-history live in the pointer target. Soft cap ≤80 words/bullet (`KB § PATTERNS/project-execution.md § 2.8`).

- **Vocabulary — methodology, not doctrine.** Use *methodology / rule / principle / convention / pattern / working agreement.* Avoid "doctrine / doctrinal" — hierarchical framing runs counter to how this team operates. → `KB § 01-PHILOSOPHY.md § Vocabulary — methodology, not doctrine`
- **Seed first. Always.** Every product inherits via `create_product_app()` (backend) / `createProductApp()` (frontend). Customizations flow through NAMED seams (`standard_routers=[...]`, `authProvider`, `lifespan_*`, …). A customization NOT through a named seam = structural fork — refactor or accept-with-rationale. **Don't ask whether to use the seed; the seed IS the approach.** Run the 4-question Practical Decision Test before any structural change. → `KB § 03-SEED-ARCHITECTURE.md § Seed as Skeleton` + `§ Practical decision test`
- **Verify the seed ships it — before locking any "consume the seed X" decision.** Read the module's `__init__.py` exports + the concrete adapter file; confirm runtime path covered, not just the Protocol or Fake. Gap + N=1 consumer → ship against Fake, surface follow-up. Gap + N=2+ consumers → DRY-recurrence, file the seed real-adapter project. Slip looks like *"the seed has Protocol X, so we can do Y"* when only the Fake ships. → `KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test`
- **Seed IO modules ship Fake+Real with factory.** Every seed module touching IO (HTTP, DB, vendor SDK) ships in **Protocol + Fake + Real + factory** shape mirroring `integrations/google_calendar` + `google_maps`. Pure-logic / crypto / shaping modules exempt — exemption test: *"would a Fake here exercise different code than the Real?"* If no, exempt. Half-shipped (Protocol+Real only OR Protocol+Fake only) generates consumer-side forks at the seed level — fix at the seed before consuming. → `KB § PATTERNS/seed-fake-real-adapter.md`
- **No incomplete commits.** Backend and frontend at the same maturity. "Scaffolded" is not "complete." If one side is real and the other is a placeholder, stop and flag.
- **No quick fixes.** A fix that touches multiple products for the same reason is at the wrong level — go up to seed / shared lib / config and let it propagate. Thirty minutes on the root beats five minutes on a patch that generates future work.
- **No workarounds — and no monkey-patching, in production OR tests.** Use the real API/SDK/framework. **The rule applies to test code too.** Never `monkeypatch.setattr(our_module, "our_guard", _noop)` — that test no longer exercises the guard. Right shape: seed real underlying data; use dependency injection for write side-effects; read inserts via `MockRequestBuilder.inserted_payloads`. `unittest.mock.patch.object(<external_integration>, ...)` for **external services** (LLM APIs, transcription, network) is fine. → `KB § 01-PHILOSOPHY.md § No workarounds` + `KB § PATTERNS/testing.md`
- **Estimate off evidence, not structure.** Before offering A/B/C, a session-size, or "this is quick" — open the files the change would actually touch. If it touches `seed/`, a shared lib, a factory, or any cross-cutting layer, read that code first. → `KB § 01-PHILOSOPHY.md § Estimate off evidence`
- **DRY — the recurrence rule.** **N=2 → triage time** (formalize / refactor / accept-with-rationale; decision recorded; silently moving on forbidden). **N=3+ → MUST formalize** (extract into seed-lib / framework / shared library; minimum response = file a follow-up project; silently shipping the 4th instance forbidden). When the rule fires: STOP, name the pattern, decide the destination, file or apply, resume. → `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
- **Componentize everything.** Check `KB § 04-SHARED-LIBRARY.md` before writing anything new. If another product will need it, build it shared from day one. → `KB § 04-SHARED-LIBRARY.md`
- **Narrow-read first.** Default to **structure before bodies** for any file >200 lines or whenever you don't know the exact range. Outline via grep on top-level symbols (or a small-`limit` `Read`), fetch bodies only for what you'll actually edit, cite, or reason about. Whole-file reads reserved for short files, full reviews/rewrites, or content-is-structure files. → `KB § PATTERNS/agent-reading-discipline.md § Narrow-read first`
- **Explore-agent delegation.** Delegate to the **Explore subagent** when answering requires **3+ targeted greps, multi-file walking, or open-ended discovery**. Use direct `Read` / `grep` when the exact file path or symbol is already known. *The trigger is research breadth, not product count.* Prefer dedicated `noctusai_*` scan tools (refs, recurrence, status) when available. → `KB § PATTERNS/agent-reading-discipline.md § Explore-agent delegation`
- **Replication-to-seed symmetry — fires at READ/PLAN/DESCRIBE time.** *The trigger is LANGUAGE.* Phrasings like **"per-product X"**, **"mount across N products"**, **"for each product Y"** ARE the slip — wherever they appear (your reply, project docs, user prompt). The right per-product code count for a cross-product concern is **zero**. Authoring-time corrective: every `PROJECT.md` MUST include §3a Seed-first analysis BEFORE §6. → `KB § PATTERNS/project-execution.md § The replication-to-seed symmetry rule` + `KB § GUIDES/seed-first-design.md`
- **AST-first — never regex code edits.** Code changes go through an AST tool: `libcst` for Python, `ts-morph` for TypeScript, `tree-sitter` for cross-language analysis. Regex / sed / awk only for prose, search, and log inspection. Boundary rule: *if the file is parsed by a compiler / interpreter / type-checker, use the AST tool.* **Structural-refactor corollary**: grep misses segmented construction (`Path / "a" / "b"`, `os.path.join`, template literals, dynamic imports) — pytest + builds are the oracle, not grep. → `KB § 01-PHILOSOPHY.md § AST-first` + `KB § PATTERNS/ast.md`
- **Flag MCP-first / AST-first opportunities proactively.** Both default-surface rules fire when the surface is the *target*. This rule fires when it's a *bystander* — you're working elsewhere and spot a missed exposure (a capability that should land in MCP, or a sed/regex code edit that should be AST). Surface every spotted opportunity: **apply now** if cheap, or **defer with destination** in the active project's `**Improvements:**` block / accept-with-rationale catalog / a follow-up project. Silent skipping is forbidden — same shape as silent errors. The MCP server is a living organism (`KB § PATTERNS/mcp-tool-conventions.md`); we actively scan for project improvement ops, so we do the same for the platform's two default surfaces. → `KB § 01-PHILOSOPHY.md § Flag MCP-first / AST-first opportunities proactively`
- **Absorption-search is a standing duty in product code.** Whenever editing a product's services / routers / hooks / components — *even for an unrelated task* — keep the recurrence rule active and run the MCP scans before walking away from the file. Run **all relevant modes from the sextet** (full list in KB), notably `noctus.dev.scan_cross_product_helpers` + `noctus.dev.scan_within_product_helpers` (catches N≥3 within one product — the gap that surfaced an N=2 PF dashboard duplication in Batch 1C audit) + `noctus.dev.scan_service_line_recurrence` + `noctus.dev.scan_block_patterns`. Use BEFORE writing a new helper/DTO/service shell; use AFTER a cleanup pass as the calibration check. **Within-product duplications at N=2 require architect-eyes during Phase 0 audit** — automated scanners threshold at N≥3 to suppress noise. → `KB § 06-AGENTS.md § Absorption-search sextet`
- **Triage at decision time — formalize / refactor / accept-with-rationale.** Every divergence from ideals lands on one of three explicit outcomes: **formalize** (extend framework/seed), **refactor** (align with contract), or **accept-with-rationale** (catalog the entry in `KB § PATTERNS/accept-with-rationale.md` — durable register that survives project folder deletion). "Accept" is a real landing — paperwork keeps it from going silent. Recurrence flips prior `accept` outcomes toward `formalize`. → `KB § 01-PHILOSOPHY.md § Triage at decision time` + `KB § PATTERNS/accept-with-rationale.md`
- **Safety nets capture failures; failures become learnings; methodology evolves.** Methodology is incomplete by design. Safety nets — `git merge` for the merging gap, drive-by-exception for hook false-positives, `git stash` for switch blockers — keep the system working when methodology hits a gap. **Capture the learning** (`KB § PATTERNS/project-execution.md § 2.11 Phase enrichment loop`), **update the methodology** (three-way sync), **gap closes structurally** so future occurrences hit the updated rule, not the gap. The safety net activating IS the methodology working — it caught what the rule didn't yet cover. Anti-patterns: bypassing the safety net to avoid surfacing the gap (`--force` push instead of merging); capturing the failure but skipping the methodology update (lives only in §11 prose); repeating the same safety-net catch without ever formalizing (recurrence rule fires but methodology never evolves). → `KB § 01-PHILOSOPHY.md § Safety nets capture failures; failures become learnings; methodology evolves`
- **Branching-first orchestration — parallelize by default; orchestration STAYS with the orchestrator. Architect plans + dispatches + stays-with-user; engineers build.** The dev methodology is branching-first. **The orchestrator IS the architect** — plans + dispatches + evaluates + stays available for user-facing ideation while engineers (subagents) do the heavy lifting in isolated worktrees. **Subagents ARE engineers** (single engineer or team of engineers depending on parallelism opportunity) — focused briefs, narrow context, build the chunks the architect defined, report back. Architect's default mental model on incoming work: "can this be chunked into parallel branches?" If yes — set up `git worktree add` per engineer (`KB § PATTERNS/branching-and-merging.md § 16`); dispatch engineers in a single `Task` tool-use turn (true parallelism); maintain findings.md aggregating their slips / errors / lessons / surprises (§ 17). If no — serial, OR master-tree-parallel-batches for N≥2 same-shape children. **Engineers are EXECUTORS of focused chunks; they are never PLANNERS of orchestration** — architect's broad-context + session-spanning conversation IS the planning value. **Engineer findings are evaluated locally by the architect + applied immediately when applicable** — methodology gaps with clear fixes get amended SAME SESSION (KB/CLAUDE/memory three-way sync); small in-scope cleanups go inline; cross-product follow-ups file future projects; routine completions bundle in retrospective. Deferring an applicable fix = silent-error shape; defaulting to immediate implementation is the rule. **Serial requires justification** (logged as a learning). Anti-patterns: serial-by-default when parallel was feasible; engineers in separate messages (= serial); forcing parallel when chunks depend; skipping chunk identification; **delegating the orchestration itself to an engineer**; **dispatching N engineers into the same worktree** (race-prone); **deferring fixes that could be applied now** (silent-error shape — the finding becomes debt). The conversational dimension: architect stays available for the user while engineers work — the user thinks-with the architect, not with engineers. → `KB § 01-PHILOSOPHY.md § Branching-first orchestration` + `§ Roles: Architect + Engineers` + `§ Knowledge tracking — durable findings file`
- **Knowledge tracking — durable findings file for any non-trivial work.** Any non-trivial project / feature / orchestration maintains a `findings.md` at its root capturing slips / errors / mistakes / lessons / interesting findings / discovered knowledge. Five standard categories. Append in-the-moment for surprises (freshness matters); synthesize at close into a curated knowledge artifact. Default-on for projects + master-trees + parallel-orchestration; optional for trivial direct fixes (skip silently is forbidden — log absence to `phase_learnings` SQLite so the absence is explicit). Distinct from `phase_learnings.db` (atomic per-phase learnings) + `live-patterns-log.md` (master-tree per-batch raw log) + §11 Change log (what-we-did): findings.md is what-we-LEARNED, curated. **Architect dispatch briefs MUST include an explicit Write-authorization paragraph for `findings.md` / `PROJECT.md` / proposal `.md` files** — engineer subagents inherit the "*NEVER create *.md files*" default and may refuse without explicit override (template at KB §17.6). → `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md § 17.6`
- **No silent errors — always explicit fix opportunities.** No `except: pass`, no silent degraded fallbacks, no deferred items without a named destination, no "verification ✓" when the tail showed red. Ambiguity is a silent error — ask. Absence of findings is a claim — quote the command that confirms it. → `KB § 01-PHILOSOPHY.md § No silent errors`
- **Three-way sync — KB, CLAUDE.md (or topical CLAUDE/<topic>.md), and memory move together.** Any rule/methodology/behavior change lives in **all three layers simultaneously**. **NEW rule ordering**: KB-first, then CLAUDE.md (or topical) pointer, then memory entry + MEMORY.md index line. **Amending an existing rule**: all three layers same session. `verify-kb-sync.sh` catches dangling KB↔CLAUDE.md pointers but not missing memory entries — that's the agent's discipline. → `KB § 01-PHILOSOPHY.md § Docs stay in sync`
- **Finish the session — verify, don't assume.** End-of-session checklist: `cd products/<touched>/frontend && npx vite build`; `cd products/<touched>/backend && pytest`; `cd mcp/noctusai && pytest tests/` if MCP-toolkit changed; report any regression. Don't mark "done" while a build or test is red. *Every in-session change must land on green.*
- **Never auto-commit or push, except project gates; commit + push only your own work.** Two carve-outs: (a) end-of-phase local commit (no push); (b) final commit + `git push` at project close (literal last step, after folder deletion). `git status` first; never `git add .` / `-A`. Stage only files YOU authored this session — explicit-path `git add` does NOT validate authorship. Verify via `git diff --cached --name-only` before commit, `git log origin/<branch>..HEAD` before push; surprise entries → unstage / ask. → `CLAUDE/projects.md § Commit per phase, push at project close` + `KB § PATTERNS/project-execution.md § 2.10`
- **Context budget discipline.** `CLAUDE.md` (this file) = router. `CLAUDE/<topic>.md` = topical rules, read on-demand by agent discipline (see §3). `KNOWLEDGE-BASE/` = depth. **MCP keep-list**: `noctusai` + `supabase` only — anything else needs explicit user approval. **Skills keep-list**: `update-config` / `loop` / `schedule` / `security-review` only. New rule → KB-first → CLAUDE.md (or topical) pointer → memory. New §1 bullet >80 words → trim and push depth to KB. → `KB § 01-PHILOSOPHY.md § Context budget discipline`
- **Templates cannot modify noc.** A template workspace is a sibling of noc that consumes 8 noc surfaces (CLAUDE.md, CLAUDE/, KNOWLEDGE-BASE/, .claude/, mcp/, seed/, noctusai_lib/, templates/) via read-only symlinks. Three-layer defense: (1) PRIMARY — template's pre-commit hook refuses commits touching symlinked paths AND non-sandbox additions without a `.promotions/<slug>.md` entry, (2) AGENT — this rule + KB depth + memory entry, (3) SYMBOLIC — chmod -h a-w on symlinks (no-op on macOS; symbolic only). Edits to symlinked surfaces belong in noc; additions destined for noc go through the promotion manifest + `noctusai_promote_from_template`. → `KB § PATTERNS/template-workspace.md`
- **Seed workspaces inherit noc whole, not trimmed.** Sibling workspaces consume all 8 noc surfaces via read-only symlinks; *trim none*. Auto-load is already minimal by design (`CLAUDE.md` is a router; KB depth loads on-demand — unread = uncost; `MEMORY.md` is an index). Trimming breaks **seed-first analysis** (needs cross-product visibility to spot absorption candidates), **recurrence-rule scans** (need every product in tree to detect N≥2/N≥3), **KB pointer integrity** (cross-refs flagged by `verify-kb-sync.sh`), and **three-way sync**. Per-product focus belongs in `products/<slug>/MASTER-PROMPT.md`, not in pruning. The workspace IS `noc + product`, not `subset(noc) + product`. → `KB § PATTERNS/seed-workspace.md § Why the inherited surface is not trimmed`
- **Parallel-agent collision protocol — STOP, wait, continue.** When a shared-file edit is reverted by another agent's work AND re-applying would loop, do not loop-fight. STOP after the second revert. **Do NOT file a collision-report project** — wait for the parallel agent to finish. Continue with non-colliding deliverables; catalog the deferred work in `accept-with-rationale.md` so the design intent survives the wait. Surface in end-of-work summary (name the seam + the parallel project + the catalog entry's short-title). Re-apply when the user signals or the parallel project closes (one apply + verify no further reverts → flip catalog entry to FORMALIZED). N=2 collisions on different files in same session → pause project, surface to user. → `KB § PATTERNS/project-execution.md § 2.9`

---

## 2 · The Map

Pointers into `CLAUDE/<topic>.md` and `KNOWLEDGE-BASE/`. Open *on-demand*. If nothing here matches, open `KNOWLEDGE-BASE/INDEX.md`.

### Topical behavioral rules (sibling files; read by agent discipline)
- Backend rules — `CLAUDE/backend.md`
- Frontend rules — `CLAUDE/frontend.md`
- Project-execution rules — `CLAUDE/projects.md`
- Cross-cutting platform rules (MCP toolkit, MCP-first, clean folder, LGPD-first) — `CLAUDE/platform.md`

### Architecture & context (KB depth)
- Product landscape (products, schemas, ports, stack) → `KB § 02-LANDSCAPE.md`
- Seed framework (factories, layer split, how products inherit) → `KB § 03-SEED-ARCHITECTURE.md`
- Shared library catalog → `KB § 04-SHARED-LIBRARY.md`
- Infrastructure (ports, deploy, self-hosted services) → `KB § 05-INFRASTRUCTURE.md`
- MCP dev toolkit → `KB § 06-AGENTS.md`
- Gamification philosophy → `KB § 07-GAMIFICATION.md`

### Patterns (KB depth)
- Backend patterns → `KB § PATTERNS/backend.md`
- Frontend patterns → `KB § PATTERNS/frontend.md`
- Testing → `KB § PATTERNS/testing.md`
- Database & RLS → `KB § PATTERNS/database-rls.md`
- Environment / `.env` → `KB § PATTERNS/environment.md`
- Notifications → `KB § PATTERNS/notifications.md`
- Shared-library conventions → `KB § PATTERNS/shared-library-conventions.md`
- Project execution → `KB § PATTERNS/project-execution.md`
- Proposals & improvements → `KB § PATTERNS/proposals-and-improvements.md`
- LGPD awareness → `KB § PATTERNS/lgpd.md`
- LLM usage tracking → `KB § PATTERNS/llm-usage.md`
- Logging convention → `KB § PATTERNS/logging.md`
- Seed-lib layout (6 layers) → `KB § PATTERNS/seed-lib-layout.md`
- AST-driven code edits → `KB § PATTERNS/ast.md`
- Agent reading & research discipline → `KB § PATTERNS/agent-reading-discipline.md`
- Webhook signature verification → `KB § PATTERNS/webhook-signatures.md`
- Accept-with-rationale catalog → `KB § PATTERNS/accept-with-rationale.md`
- MCP tool conventions (dotted naming, Pydantic schemas, hierarchical registration, lazy context) → `KB § PATTERNS/mcp-tool-conventions.md`
- LLM tool-call audit (`tool_call_audits` per-product table, `AuditRecord` + `make_audit_writer`, LGPD redaction) → `KB § PATTERNS/llm-tool-audit.md`
- LLM bot security (sanitize / validate / rate-limit trio, confirm-then-execute, prompt-injection mitigation) → `KB § PATTERNS/llm-bot-security.md`
- Template workspace (sibling consume-only workspace; "templates can't modify noc" rule + 3-layer defense + promotion manifest) → `KB § PATTERNS/template-workspace.md`
- Scheduling primitive (`noctusai_lib.domain.scheduling` — engine + Conflict/Scorer/TravelLookup Protocols + defaults + wiring recipe) → `KB § PATTERNS/scheduling-seed.md`
- Metas / goals primitive (`noctusai_lib.domain.metas` — Goal/Target/Progress/Period value objects + GoalStatus/PeriodKind enums + compute_progress / accumulate_contribution / period_bounds / proportional_target / next_status pure fns + GoalRepository Protocol; lifted from PF/ERP/daily-life N=3) → `KB § PATTERNS/metas-seed.md`
- WhatsApp connector + chatbot framework (`noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.chatbot` + `noctusai_lib.integrations.{google_calendar,google_maps}` — WAHA parser/sender/router + Redis-backed buffer/worker/LLM-dispatcher + Calendar/Maps adapters; wiring recipe) → `KB § PATTERNS/whatsapp-chatbot-seed.md`
- Digest service base class (`noctusai_lib.domain.digest.BaseDigestService` template-method base — window → fetch → aggregate → narrate → render → result orchestration shared; 4-adopter cluster — core/audit, daily-life/weekly-review, mailing/debrief, PF/narrative; non-fits documented) → `KB § PATTERNS/digest-seed.md`
- Master-tree parallel batches (multi-product orchestrator: same-shape phases across N children execute as synchronized batches; live cross-pollination via shared scratchpad; sync-gates pre/mid/post; divergent-batch carve-out) → `KB § PATTERNS/master-tree-parallel-batches.md`
- agno multi-agent dev team (engine at `dev_team/` + product at `products/dev-team/`; MCP exposure `noctus.team.*` — run/status/route/metrics/agent_metrics/configure; 11 specialists + 3 sub-teams; per-turn telemetry; "switch flip" UX gated by `ANTHROPIC_API_KEY`) → `KB § PATTERNS/dev-team.md`
- Containerization (multi-layer Docker: per-product `docker-compose.yml` + root `include:` orchestrator + shared `noctus-net` + per-product `<slug>-net` isolation; canonical pattern at `products/seed/`; `./start.sh` Docker-default with `tunnel <slug>` cloudflare quick-tunnel for OAuth/webhook/demo online testing; `native` legacy preserved) → `KB § PATTERNS/containerization.md`

### Guides
- First-time setup → `KB § GUIDES/setup.md`
- Creating a new product → `KB § GUIDES/new-product.md`
- Seed-first design checklist → `KB § GUIDES/seed-first-design.md`
- Putting a workspace product online for testing (the "deploy" drill) → `KB § GUIDES/deploy-workspace-online.md`

### Integrations (KB depth — vendor references)
- Vista CRM REST API (auth, endpoints, error model, adapter contract, per-tenant calibration gap) → `KB § INTEGRATIONS/vista.md`

### Per-product details — open only the product you're working on
- Backend specs → `KB § backend/{01-CORE, 02-ERP, 03-PF, 04-DATABASE, 05-AI-FEATURES, 06-THERAPY, 07-AUTH-SECURITY, 08-DAILY-LIFE}.md`
- Frontend specs → `KB § frontend/{01-CORE, 02-ERP, 03-PF, 04-THERAPY}.md`

### Agent / skill / workflow design
- Entry point → `KB § INSTRUCTIONS/00-MASTER.md`

> Throughout this file `KB § X` is shorthand for `KNOWLEDGE-BASE/X`.

---

## 3 · When to read what

| Situation | Read first |
|---|---|
| Fresh session, need orientation | `KB § AGENT-CONTEXT.md` + `KB § 02-LANDSCAPE.md` |
| Writing/editing backend code | `CLAUDE/backend.md` + `KB § PATTERNS/backend.md` + `KB § backend/0X-*.md` |
| Writing/editing frontend code | `CLAUDE/frontend.md` + `KB § PATTERNS/frontend.md` + `KB § frontend/0X-*.md` |
| Starting / executing / closing a project; handling a phase; touching `*-PROJECT.md` | `CLAUDE/projects.md` + `KB § PATTERNS/project-execution.md` |
| Cross-cutting platform work (MCP toolkit, MCP server design, LGPD data, root hygiene, KB depth) | `CLAUDE/platform.md` + relevant KB pattern |
| Writing a migration | `CLAUDE/backend.md` + `KB § PATTERNS/database-rls.md` + `KB § backend/04-DATABASE.md` |
| Wiring auth on a new product / route (`Depends(get_current_user_org)` shape; the `make_get_current_user_org` factory) | `KB § PATTERNS/backend.md § Auth — canonical pattern` |
| Adding a shared component | `KB § 04-SHARED-LIBRARY.md` (check first — it might exist) |
| Creating a new product | `KB § GUIDES/new-product.md` + `KB § 03-SEED-ARCHITECTURE.md` |
| User says "put X online" / "bring it up" / "deploy for testing" / "let me test it" / "spin up the stack" | `KB § GUIDES/deploy-workspace-online.md` (the drill: verify docker artifacts → fill `.env` → `docker compose up` → verify) |
| Starting a new project | `CLAUDE/projects.md` first; copy `templates/PROJECT-TEMPLATE.md` per `KB § PATTERNS/project-execution.md §1` |
| Writing tests | `KB § PATTERNS/testing.md` |
| Adding a `try/except` (production code) | `KB § PATTERNS/logging.md` (level guide, no-`# silent-ok` rule) |
| Editing `.py` / `.ts` / `.tsx` source (rename, codemod, find-callers, multi-file change) | `KB § PATTERNS/ast.md` (AST-first — never sed/regex on source) |
| Exposing a new capability to agents | `CLAUDE/platform.md` + `KB § 01-PHILOSOPHY.md § MCP-first` |
| Adding / amending a keeper detector | `KB § PATTERNS/testing.md § Regression-test-the-detector` |
| Adding a helper to `noctusai_lib` | `KB § PATTERNS/seed-lib-layout.md` |
| Touching gamified UI | `CLAUDE/frontend.md` + `KB § 07-GAMIFICATION.md` |
| Designing an agent / MCP / skill | `KB § INSTRUCTIONS/00-MASTER.md` |
| Touching Vista CRM (showcase adapter, future MCP server, endpoint surface, field-set calibration) | `KB § INTEGRATIONS/vista.md` |
| Anything not listed | `KB § INDEX.md` |

---

## 4 · Sync rule

CLAUDE.md, `CLAUDE/<topic>.md` files, and `KNOWLEDGE-BASE/INDEX.md` stay in sync — when you add, rename, or delete any KB file or folder, every layer that references it gets updated.

**Pre-commit hook enforces it** (`scripts/pre-commit` → installed by `scripts/install-hooks.sh`). On every commit:
1. Syncs `products/seed/` → `templates/product-seed/` if staged.
2. Runs `scripts/update-kb-counts.py` — regenerates auto-derived count blocks.
3. Runs `scripts/verify-kb-sync.sh` — **blocks the commit** if any literal `KNOWLEDGE-BASE/…md` pointer in CLAUDE.md or `CLAUDE/*.md` doesn't resolve, or any KB doc is missing from `INDEX.md`.

Manual runs:
- `bash scripts/verify-kb-sync.sh`
- `python scripts/update-kb-counts.py [--check]`
- `python mcp/noctusai/cli.py --verify-kb-sync`

Install hooks in a fresh clone: `bash scripts/install-hooks.sh` (full setup: `bash scripts/setup.sh`).

Bypass (rarely correct): `git commit --no-verify`.
leak
