# Knowledge Base — Index

> **Purpose:** This is the structural catalog of the NoctusAI Knowledge Base. Agents and developers use it to answer: *"where is X?"*.
> For *"what is this place?"* — read `AGENT-CONTEXT.md` instead (prose onboarding).
>
> **Sync rule:** Kept in sync with `CLAUDE.md`'s map section. If you add, rename, or delete a file in the KB, update both.

---

## Layout

```
KNOWLEDGE-BASE/
├── INDEX.md                ← this file (the catalog)
├── AGENT-CONTEXT.md        ← "what is this place" (onboarding prose)
├── CONTEXT/                ← deep technical + architectural context
│   ├── 01-PHILOSOPHY.md    ← engineering principles (elaborated)
│   ├── 02-LANDSCAPE.md     ← products, schemas, ports, stack
│   ├── 03-SEED-ARCHITECTURE.md  ← the spine
│   ├── 04-SHARED-LIBRARY.md     ← reusable components catalog
│   ├── 05-INFRASTRUCTURE.md     ← deployment + self-hosted services
│   ├── 06-AGENTS.md        ← MCP dev toolkit (Claude-side agents)
│   ├── 07-GAMIFICATION.md  ← cross-product UX philosophy
│   ├── PATTERNS/           ← how-to technical patterns
│   │   ├── backend.md
│   │   ├── frontend.md
│   │   ├── testing.md
│   │   ├── database-rls.md
│   │   ├── environment.md
│   │   ├── notifications.md
│   │   ├── shared-library-conventions.md
│   │   ├── project-execution.md
│   │   ├── proposals-and-improvements.md  ← two-system protocol (improvements per-project, ONE bundled proposal per phase)
│   │   ├── lgpd.md
│   │   ├── llm-usage.md       ← Phase 15 DB-backed usage sink + admin endpoints
│   │   ├── logging.md         ← level guide, no-`# silent-ok` rule, correlation IDs
│   │   ├── seed-lib-layout.md ← 6-layer model + decision tree
│   │   ├── seed-fake-real-adapter.md ← canonical Protocol+Fake+Real+factory shape for IO-touching seed modules
│   │   ├── agent-reading-discipline.md ← narrow-read first; Explore delegation (forthcoming)
│   │   ├── webhook-signatures.md ← four shapes (Hub-Signature / hex HMAC / Svix / Stripe SDK); helpers in noctusai_lib.security.webhook_signatures
│   │   ├── accept-with-rationale.md ← pattern definition + durable catalog of every active accept-with-rationale on the platform
│   │   ├── ast.md                  ← AST-first toolchain (libcst / ts-morph / tree-sitter) + recipes + anti-patterns + boundary rule
│   │   ├── mcp-tool-conventions.md ← 3-segment dotted naming + Pydantic In/Out + hierarchical registration + lazy context + MCP-first principle
│   │   ├── seed-workspace.md   ← sibling consume-only workspace; "templates cannot modify noc" rule + 3-layer defense + promotion manifest
│   │   ├── llm-tool-audit.md       ← per-product tool_call_audits table + AuditRecord/AuditWriter + LGPD redaction + adoption checklist
│   │   ├── llm-bot-security.md     ← defense trio (sanitization / arg-validation / rate-limit) + confidence thresholds + prompt-injection mitigation + baseline checklist
│   │   ├── digest-seed.md          ← noctusai_lib.domain.digest — BaseDigestService template-method base + DigestWindow/DigestResult; 4-adopter cluster (audit/weekly-review/campaign-debrief/monthly-narrative)
│   │   ├── metas-seed.md           ← noctusai_lib.domain.metas — Goal/Target/Progress/Period value objects + state machine + period date-math + GoalRepository Protocol; lifted from PF/ERP/daily-life N=3
│   │   ├── scheduling-seed.md      ← noctusai_lib.domain.scheduling — engine + Conflict/Scorer/TravelLookup Protocols + wiring recipe
│   │   ├── whatsapp-chatbot-seed.md ← noctusai_lib.{integrations.whatsapp,domain.chatbot,integrations.{google_calendar,google_maps}} — connector + framework + adapters wiring recipe
│   │   ├── master-tree-parallel-batches.md ← multi-product orchestrator running same-shape phases as synchronized batches; live cross-pollination via shared scratchpad; divergent-batch carve-out
│   │   ├── branching-and-merging.md   ← end-to-end git workflow: branching (when, how, push semantics, mental model, naming, anti-patterns) + merging (non-FF integration, multi-branch convergence, conflict resolution discipline, long-running branch maintenance, recovery from bad merges)
│   │   ├── dev-team.md                ← agno multi-agent dev team (engine at dev_team/ + product at products/dev-team/); MCP exposure noctus.team.*; charter / tools / memory / telemetry / configs surfaces; "switch flip" UX
│   │   ├── dev-toolkit-scaffolders.md ← 7-tool noctus.dev.* program: codegen scaffolders (scaffold_seed_adapter/mcp_tool/keeper/memory — emit consumable boilerplate, return code not write, emitted-code-must-ast.parse gate) + orchestration (salvage_worktree/dispatch_preflight/findings — operationalize R6/R2/findings)
│   │   ├── seed-absorption.md         ← noctus.seed.* MCP tools (scan_repetition / list_capabilities / audit_drift / absorb_file / specify_capability / report / scan_fusions / scan_optimizations — the absorption+fusion+optimization trio) + noctus.hound.scan trio orchestrator + 4 absorption strategies (delete dead code / move to seed + re-export / factory / template + runtime substitution) + per-candidate loop + safety rules
│   │   ├── containerization.md         ← multi-layer Docker compose: per-product fragments + root orchestrator with `include:` + shared `noctus-net` + Redis/WAHA/tunnel profiles; canonical pattern at products/seed/; ./start.sh as Docker-default with tunnel <slug> mode (cloudflare quick-tunnel for OAuth callbacks / webhook testing / shared demos); native preserved as legacy; build/network/security/troubleshooting; improvement backlog
│   │   ├── chatbot-operational-readiness.md ← production-hardening checklist for LLM chatbot products (6 pillars: retries / structured logs / health / deployment doc / backup / metrics sink); first adopter imobi-scheduling; therapy/mailing/PF inherit; folded from sibling's production-hardening + operational-dashboards artifacts
│   │   ├── ci-security-gates.md     ← 3-gate CI security pass (Trivy fs + image scans / bandit Python SAST / gitleaks secrets) with allowlist + baseline patterns; canonical configs at repo root `.trivyignore` / `bandit.yml` / `bandit-baseline.json` / `.gitleaks.toml`; wiring at `.github/workflows/test.yml`
│   │   ├── pydantic-strict-http.md  ← StrictHttpModel base (`extra="forbid"`) at seed; closes silent-drop bug class; per-product migration is mechanical inheritance swap
│   │   ├── storage-hygiene.md       ← the `mole` (3rd member of keeper/hound/mole trio) — custodial agent for storage; 3 scopes (artifacts/environments/worktrees); active pre-dispatch+pre-commit+bootstrap; safety constraints; bash-3.x compat mandate (mapfile gap)
│   │   ├── autonomous-operator-via-subagent.md  ← Option D: single-session + ScheduleWakeup tick + specialized orchestrator-operator subagent drains dispatcher-inbox.md in isolated context; combines Options B+C; architect main context stays clean for user-conversation
│   │   ├── two-session-architect-operator.md ← two-Claude split — Session A Architect (conversation/KB/memory, no git) + Session B Operator (autonomous git mechanics, engineer dispatch exec, tail sweeps); coordination via gitignored dispatcher-inbox.md + dispatcher-outbox.md at repo root; strict git/memory/KB ownership; setup recipe + `/loop` variant + decision rubric + Option D trade-off
│   │   ├── methodology-codification-pipeline.md ← the 4-stage pipeline that turns conversation rules into keeper detectors (emerges → memory → KB/CLAUDE.md → keeper detector); names the keeper as the codification layer (Stage 4) rather than a regulatory silo; codification criteria (deterministic predicate / recurrence ≥3 / clear remediation); 5 worked examples (LGPD / webhook 5-pin / status-assertion / slowapi-pep563 / hygiene-compliance); what CAN'T be codified (judgment-dependent / context-dependent / in-pilot / aesthetic); how to promote a rule between stages; why naming the pipeline matters
│   │   └── doc-symbology.md ← lossless compression glossary; logic+set symbols (∧ ∨ ¬ ⇒ ↔ ∈ ⊂ ≡ ≠ ≈), status icons (✅ ⏳ ❌ 🔒 📋 🗑 ⭐ ⚠️), codification stages (s1/s2/s3/s4), triage outcomes ([F]/[R]/[A]), counts (N≥3 Δ Σ ±), prose-word abbreviations (DB/auth/config/req/res/fn/impl); fixed-meaning contract + lossless-swap test; caveman-skill provenance (validated ~61-75% token cut) — adopts prose-discipline layer + lite/full/ultra intensity ladder, rejects caveman `→`=causal (our `→`=routes locked, divergence register); where to use (MASTER-PROMPTs / CLAUDE.md / KB patterns / PROJECT.md §6+§11) vs NOT (error messages / first paragraph / quoted user / commit messages); 7 reference patterns codifying common rules in 1-line forms
│   ├── GUIDES/             ← task-oriented guides
│   │   ├── setup.md
│   │   ├── new-product.md
│   │   ├── seed-first-design.md
│   │   ├── deploy-workspace-online.md  ← "put X online" drill: verify docker artifacts → fill .env → docker compose up → verify; trigger phrases
│   │   ├── absorb-seed-workspace.md    ← absorb a separately-developed seed-workspace into noc as one product; 10 gates (snapshot → in-home → audit → interrogate → scaffold → full seed-reconcile → port+pilot-first → consumer-adapt → teardown → container-refactor → user-gated retirement); written from the proven social-wiring absorption 2026-05-16
│   │   └── google-oauth-setup.md       ← Google Cloud Console OAuth client + Calendar API + redirect URI + env wiring; first adopter therapy-platform; reusable for any future product
│   ├── INTEGRATIONS/       ← per-vendor integration references (auth, endpoints, error model, adapter contract)
│   │   ├── oauth-patterns.md ← cross-provider OAuth reference — 5-layer model + 5 patterns + G1-G6 gotchas + Meta token-chain/auth-matrix + Google↔Meta scope-discovery diff + setup-guide template + what's already in seed vs the residual gaps
│   │   ├── meta.md         ← Meta (Facebook Pages + Instagram Graph) consume-side reference — `noctusai_lib.integrations.meta` `__all__` + factory auth-resolution (system_user → user_oauth → Fake) + consume recipe + read-only-v1 gaps
│   │   ├── whatsapp.md     ← WhatsApp connector consume-side reference — `noctusai_lib.integrations.whatsapp` `__all__` + WAHA vs Meta-Cloud-API backends + factory + webhook-router seam + lid-auth/dedup
│   │   ├── google.md       ← Google integrations consume-side reference — Calendar/Maps/YouTube/Drive `__all__` + factories + resolver injection + quota-cost docs + seed-ahead consumer status
│   │   └── vista.md        ← Vista CRM REST API — public docs + live-probe results + adapter contract folded into one
│   ├── backend/            ← per-product backend details
│   │   ├── 01-CORE.md
│   │   ├── 02-ERP.md
│   │   ├── 03-PF.md
│   │   ├── 04-DATABASE.md
│   │   ├── 05-AI-FEATURES.md
│   │   ├── 06-THERAPY.md
│   │   ├── 07-AUTH-SECURITY.md
│   │   └── 08-DAILY-LIFE.md
│   └── frontend/           ← per-product frontend details
│       ├── 01-CORE.md
│       ├── 02-ERP.md
│       ├── 03-PF.md
│       └── 04-THERAPY.md
├── INSTRUCTIONS/           ← agent development / skill design
│   ├── 00-MASTER.md
│   ├── 01-SKILLS.md
│   ├── 02-MCP.md
│   ├── 03-AGENTIC-WORKFLOWS.md
│   ├── 04-DESIGN-PHASES.md
│   ├── 05-TESTING-EVALS.md
│   ├── 06-TECH-STACK.md
│   └── 07-TEMPLATES.md
├── EVALS/                  ← eval config + cases
├── SKILLS/                 ← skill definitions
├── WORKFLOWS/              ← multi-step workflows
└── MCP-SERVERS/            ← MCP server references
```

---

## By topic — "where do I find…"

| Topic | File |
|---|---|
| Engineering rules (seed-first, no quick fixes, DRY, etc.) | `CONTEXT/01-PHILOSOPHY.md` |
| Product landscape (names, ports, schemas, stack) | `CONTEXT/02-LANDSCAPE.md` |
| Seed framework APIs (`create_product_app`, `createProductApp`, etc.) | `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Reusable components catalog (before writing anything) | `CONTEXT/04-SHARED-LIBRARY.md` |
| Infrastructure (ports, Docker, WAHA, LiveKit, n8n) | `CONTEXT/05-INFRASTRUCTURE.md` |
| MCP dev toolkit (heal loop, proposals, tools) | `CONTEXT/06-AGENTS.md` |
| Gamification philosophy (ranks, points, subtle UX) | `CONTEXT/07-GAMIFICATION.md` |
| Backend patterns (auth, SSO, RLS, N+1, services) | `CONTEXT/PATTERNS/backend.md` |
| Frontend patterns (mobile-first, TanStack Query, hooks) | `CONTEXT/PATTERNS/frontend.md` |
| Testing discipline (3 layers, mocking, auth boundary) | `CONTEXT/PATTERNS/testing.md` |
| RLS + DB rules (`auth.uid()` subquery, search_path) | `CONTEXT/PATTERNS/database-rls.md` |
| Environment vars (single `.env`, VITE_ prefix, CORS) | `CONTEXT/PATTERNS/environment.md` |
| Notifications (`public.notifications`, field mapping) | `CONTEXT/PATTERNS/notifications.md` |
| Shared-library conventions (privatize / absorb / rename; catalog tool) | `CONTEXT/PATTERNS/shared-library-conventions.md` |
| Project execution (phase-header ticks, improvements block, improvements.md retrospective tool) | `CONTEXT/PATTERNS/project-execution.md` |
| Proposals & improvements (two systems — per-project folders, ONE bundled proposal per phase, promote boundary) | `CONTEXT/PATTERNS/proposals-and-improvements.md` |
| LGPD awareness (keeper principle, the five questions, noctus.dev.lgpd_flag tool) | `CONTEXT/PATTERNS/lgpd.md` |
| LLM usage tracking (SupabaseUsageSink, /api/llm/usage, cost estimation, RLS scoping) | `CONTEXT/PATTERNS/llm-usage.md` |
| Logging convention (when-to-log, level guide, no-`# silent-ok` rule, correlation IDs) | `CONTEXT/PATTERNS/logging.md` |
| Seed-lib layout (6 layers — primitives/config/testing/integrations/domain/api — where to put new helpers, where to find existing ones) | `CONTEXT/PATTERNS/seed-lib-layout.md` |
| Agent reading & research discipline (narrow-read first; Explore delegation rule forthcoming) | `CONTEXT/PATTERNS/agent-reading-discipline.md` |
| Webhook signature verification (the four shapes: Hub-Signature / hex HMAC / Svix / Stripe SDK; constant-time compare; helper module in `noctusai_lib.security.webhook_signatures`) | `CONTEXT/PATTERNS/webhook-signatures.md` |
| Accept-with-rationale catalog (durable home for every legitimate divergence on the platform — survives project folder deletion; how to add / retire entries) | `CONTEXT/PATTERNS/accept-with-rationale.md` |
| AST-driven code edits (libcst for Python / ts-morph for TypeScript / tree-sitter cross-language; recipes for rename / find-callers / codemods; anti-patterns; boundary rule) | `CONTEXT/PATTERNS/ast.md` |
| MCP tool conventions (3-segment dotted naming `noctus.dev.* / noctus.business.* / google.* / openai.*`, Pydantic In/Out per tool, hierarchical registration, lazy `NoctusContext` for business-logic tools, settings shim, MCP-first principle) | `CONTEXT/PATTERNS/mcp-tool-conventions.md` |
| Seed workspace (sibling-of-noc consume-only workspace; symlinks all 8 noc surfaces; pre-commit hook + chmod + KB rule = three-layer "templates can't modify noc" defense; promotion manifest for additions; bootstrap script + workspace.py resolver + `noctus.dev.promote_from_seed_workspace` MCP tool) | `CONTEXT/PATTERNS/seed-workspace.md` |
| LLM tool-call audit (`tool_call_audits` per-product table; `noctusai_lib.domain.ai.tool_audit::AuditRecord` + `make_audit_writer`; best-effort write; LGPD redaction at consumer; common BI queries) | `CONTEXT/PATTERNS/llm-tool-audit.md` |
| LLM bot security (defense trio: output sanitization + Pydantic-arg validation + rate-limit; confirm-then-execute for destructive tools; prompt-injection mitigation via instruction sandboxing + allowlists; baseline checklist) | `CONTEXT/PATTERNS/llm-bot-security.md` |
| Digest service primitive (`noctusai_lib.domain.digest`: `BaseDigestService` template-method base + `DigestWindow`/`DigestResult` types; 4-adopter cluster — core/audit, daily-life/weekly-review, mailing/campaign-debrief, PF/monthly-narrative; non-fits: ERP/metas-digest + daily-life/daily-brief documented) | `CONTEXT/PATTERNS/digest-seed.md` |
| Scheduling primitive (`noctusai_lib.domain.scheduling`: engine + `TravelLookup`/`Conflict`/`Scorer` Protocols + `ZeroTravelLookup`/`DefaultConflict`/`DefaultScorer` defaults; wiring recipe; what stays consumer-side) | `CONTEXT/PATTERNS/scheduling-seed.md` |
| Metas / goals primitive (`noctusai_lib.domain.metas`: `Goal`/`Target`/`Progress`/`Period`/`Contribution` value objects, `GoalStatus`/`PeriodKind` enums, `compute_progress` / `accumulate_contribution` / `period_bounds` / `proportional_target` / `next_status` pure functions, `GoalRepository` Protocol seam; lifted from PF/ERP/daily-life N=3 MUST-FORMALIZE; wiring recipe + status mapping + what stays consumer-side) | `CONTEXT/PATTERNS/metas-seed.md` |
| WhatsApp connector + chatbot framework (`noctusai_lib.integrations.whatsapp` WAHA parser/sender/router + `noctusai_lib.domain.chatbot` buffer/worker/dispatcher/summary + `noctusai_lib.integrations.{google_calendar,google_maps}` adapters; wiring recipe; debounce-race documented; what stays consumer-side) | `CONTEXT/PATTERNS/whatsapp-chatbot-seed.md` |
| Master-tree parallel batches (multi-product orchestrator: same-shape phases across N children execute as synchronized batches; live patterns log + absorption catalog as shared scratchpad; sync-gates pre/mid/post; divergent-batch carve-out; agent collaboration mechanics) | `CONTEXT/PATTERNS/master-tree-parallel-batches.md` |
| Branching and merging methodology — end-to-end git workflow (when to branch, how to branch from `origin/main`, push semantics — branch-to-branch + branch-tip-to-main fast-forward, naming convention, mental-model upgrade, anti-patterns; non-FF integration, multi-branch convergence, conflict resolution discipline, long-running branch maintenance, recovery from bad merges) | `CONTEXT/PATTERNS/branching-and-merging.md` |
| Seed Fake+Real adapter pattern — canonical shape (Protocol + Fake + Real + factory) for IO-touching seed modules; gold-standard reference modules; exemption test for pure-logic/pure-crypto modules; backfill audit trail | `CONTEXT/PATTERNS/seed-fake-real-adapter.md` |
| Seed absorption methodology + tools — the **absorption + fusion + optimization trio** (cross-product / cross-tool / intra-file scopes): `noctus.seed.scan_repetition` / `list_capabilities` / `audit_drift` / `absorb_file` / `specify_capability` / `report` rollup / `scan_fusions` meta-detector / `scan_optimizations` intra-file detector + **`noctus.hound.scan`** trio orchestrator (keeper-analog for code hygiene); four absorption strategies (delete dead code / move-and-re-export / factory / template + runtime substitution); per-candidate loop (scan → evaluate → self-audit → absorb → re-scan → build-verify); safety rules; relation to DRY recurrence rule + delete_product symmetry | `CONTEXT/PATTERNS/seed-absorption.md` |
| Containerization (multi-layer Docker: per-product `docker-compose.yml` + root orchestrator with `include:` + shared `noctus-net` fabric + per-product isolation networks; canonical Dockerfile/compose pattern at `products/seed/`; `./start.sh` Docker-default with `tunnel <slug>` cloudflare quick-tunnel mode for OAuth/webhook/demo testing; native legacy mode preserved; build process / layering / image footprint / network security model / troubleshooting / improvement backlog) | `CONTEXT/PATTERNS/containerization.md` |
| Chatbot operational readiness — production-hardening checklist for LLM chatbot products: 6 pillars (retries on transient external writes via `retry_call` composing seed `RetryPolicy` / structured logs via seed `configure_logging` / health endpoint via `standard_routers=["health"]` / `DEPLOYMENT.md` shape / Supabase backups + critical-tables enumeration / metrics-sink seam with `NoopCounter` default); first adopter imobi-scheduling; therapy/mailing/PF inherit at N=2 | `CONTEXT/PATTERNS/chatbot-operational-readiness.md` |
| CI security gates — 3-layer PR security pass (Trivy fs + image dep scans, bandit Python SAST, gitleaks secrets scan); allowlist patterns at repo root `.trivyignore` / `bandit.yml` / `bandit-baseline.json` / `.gitleaks.toml`; canonical job shape (action pin + SARIF upload `if: always()` + exit-code gate); baseline-grandfathering for pre-existing findings; relationship to accept-with-rationale catalog | `CONTEXT/PATTERNS/ci-security-gates.md` |
| Storage hygiene — the **`mole`** (3rd member of the keeper/hound/mole trio: regulatory/curatorial/custodial); three orthogonal scopes (**artifacts** regenerable caches/builds / **environments** venv+node_modules duplication — advisory-only / **worktrees** stale `.claude/worktrees/agent-*/`); single entry point `bash scripts/mole.sh scan`; destructive `sweep --force` (dry-run default); active triggers (pre-dispatch + pre-commit + bootstrap); safety constraints (never deletes uncommitted/main/sibling/unmerged/`.env`/migrations); severity grading; bash-3.x compat mandate (the `mapfile` silent-no-op gap that motivated the rule) | `CONTEXT/PATTERNS/storage-hygiene.md` |
| Autonomous operator via subagent — **Option D** (fusion of single-session continuity + specialized-subagent-per-tick): `ScheduleWakeup` fires → architect spawns `orchestrator-operator` subagent (defined at `.claude/agents/orchestrator-operator.md`) → subagent drains `dispatcher-inbox.md` tasks (dispatch-engineer / validate-worktree / cherry-pick-and-push / archive-project) in **isolated context** → appends `dispatcher-outbox.md` audit log → returns single summary text → architect main context stays clean for user ideation. A vs B vs C vs D comparison; 8-step flow; adaptive cadence (15min idle / 5min dispatch-heavy); FF-merge-to-main remains architect-only; setup recipe; anti-patterns | `CONTEXT/PATTERNS/autonomous-operator-via-subagent.md` |
| Two-session Architect/Operator pattern — split one Claude Code workspace into two concurrent sessions (A = Architect: conversation / planning / KB / memory writes / NO git; B = Operator: ALL git ops + engineer dispatch execution + hound/mole/verify sweeps); coordination via gitignored `dispatcher-inbox.md` + `dispatcher-outbox.md` at repo root; strict ownership maps (git / memory / KB / MCP); anti-patterns (concurrent git push, both editing outbox, operator surfacing to user, memory clobbers); setup recipe + smoke test + `/loop` variant + 5-question pilot-vs-defer rubric + Option-D (single-session subagent) trade-off table | `CONTEXT/PATTERNS/two-session-architect-operator.md` |
| Methodology codification pipeline — the 4-stage path that turns conversation rules into deterministic keeper detectors (Stage 1 emerges → Stage 2 memory entry → Stage 3 KB pattern doc + CLAUDE.md pointer → Stage 4 `check_*` function with colocated test); names the keeper as the **codification layer** of the methodology rather than a regulatory silo; codification criteria (deterministic predicate + recurrence ≥3 + clear remediation); 5 worked examples walked through all 4 stages (LGPD-first, webhook 5-pin, status-code-assertion rule, slowapi-pep563 gotcha, hygiene-compliance in-flight); what legitimately stays at Stage 3 (judgment-dependent / context-dependent / methodology-in-pilot / aesthetic); how to promote a rule between stages; why naming the pipeline matters | `CONTEXT/PATTERNS/methodology-codification-pipeline.md` |
| Doc symbology — lossless compression glossary defining a fixed-meaning symbol set (logic `∧ ∨ ¬ ⇒ ↔ ∈ ⊂ ≡ ≠ ≈`; status icons `✅ ⏳ ❌ 🔒 📋 🗑 ⭐ ⚠️`; codification stages `s1/s2/s3/s4`; triage outcomes `[F]/[R]/[A]`; counts `N≥3 N=2 Δ Σ`; prose-word abbreviations `DB/auth/config/req/res/fn/impl`); contract = lossless-swap test (reader with glossary recovers exact semantic of prose); caveman-skill provenance (`github.com/JuliusBrussee/caveman`, validated ~61-75% token cut, retrieved 2026-05-18) — adopts caveman prose-discipline layer (§6a) + lite/full/ultra intensity ladder (§3a.1), explicitly rejects caveman `→`=causal mapping (our `→`=routes is locked; divergence register in §1/§4); where to use (MASTER-PROMPTs / CLAUDE.md / KB patterns / PROJECT.md §6+§11) vs NOT (error messages / first-paragraph context / quoted user instructions / bug-fix code comments / commit messages); anti-patterns (stacking, inventing new symbols without adding here, symbol-loading low-traffic docs); reference patterns codify codification pipeline + 3-way triage + doc-code coherence + recurrence rule + status legend in 1-line forms | `CONTEXT/PATTERNS/doc-symbology.md` |
| First clone + starting servers | `CONTEXT/GUIDES/setup.md` |
| Creating a new product | `CONTEXT/GUIDES/new-product.md` |
| Seed-first design checklist (cross-product projects — REQUIRED at authoring time) | `CONTEXT/GUIDES/seed-first-design.md` |
| Putting a workspace product online for testing — the "deploy" drill (verify docker artifacts → fill `.env` → `docker compose up` → verify); trigger phrases the agent should recognise | `CONTEXT/GUIDES/deploy-workspace-online.md` |
| Absorbing a separately-developed seed-workspace into noc as one product — the repeatable 10-gate procedure (Gate 0 snapshot-preserve + sanctioned `--no-verify` · Gate 1 bring-source-in-home BEFORE plan depends on it + worktree-base-vs-uncommitted-inputs trap · Gate 2 completeness audit / UNMAPPED-useful · Gate 3 interrogate disposition before deletion · Gate 4 scaffold house-container · Gate 5 full seed-reconcile sibling-validated-wins + verify-the-seed-ships-it 4 shapes + master-tree-parallel zero-git + git-stash-forbidden · Gate 6 port + pilot-first + pause-on-dependency · Gate 7 mechanical consumer-adapt + git-log-S-before-attribution · Gate 8 teardown preservation-FIRST + hazard-group commits + registry-derive + content-form dangling-ref verify + KB-count-autostage footgun · Gate 9 container-refactor + user-gated workspace retirement); written from the proven social-wiring absorption 2026-05-16; self-contained | `CONTEXT/GUIDES/absorb-seed-workspace.md` |
| Google Cloud Console OAuth setup — Calendar API (project + consent screen + Calendar API enablement + Web client + redirect URI registration + scopes + env-var wiring + smoke test + troubleshooting); first adopter therapy-platform per-therapist `/api/scheduling/gcal/*`; reusable for any future product needing user-delegated GCal | `CONTEXT/GUIDES/google-oauth-setup.md` |
| OAuth integration patterns — cross-provider (5-layer model · scope auto-discovery · dual auth backends · single-consent bundling · post-consent introspection · CredentialStore Fernet · G1-G6 gotchas · Meta token-chain + auth-mode matrix · Google↔Meta scope-discovery diff · setup-guide template · in-seed-vs-gap audit) | `CONTEXT/INTEGRATIONS/oauth-patterns.md` |
| Meta Graph adapter consume-side (`noctusai_lib.integrations.meta` exact `__all__` · `get_meta_adapter` auth-resolution priority system_user→user_oauth→Fake · consume recipe with cited social-wiring consumer · `make_meta_router` seam · read-only-v1 out-of-scope: posting/ads/webhooks) | `CONTEXT/INTEGRATIONS/meta.md` |
| WhatsApp connector consume-side (`noctusai_lib.integrations.whatsapp` exact `__all__` · WAHA `get_whatsapp_client` vs Meta-Cloud-API `get_meta_cloud_client` backends · `create_whatsapp_webhook_router` seam · lid-auth + dedup + response-registry · cited ERP consumer) | `CONTEXT/INTEGRATIONS/whatsapp.md` |
| Google integrations consume-side — Calendar/Maps/YouTube/Drive (each exact `__all__` · resolver/credential-store factory injection · YouTube quota-cost-documented Protocol · Drive dual download+read Protocols · seed-ahead consumer status · cited social-wiring consumers) | `CONTEXT/INTEGRATIONS/google.md` |
| Vista CRM REST API (auth, query convention, response envelope, error hierarchy, endpoint inventory, adapter contract, per-tenant calibration gap) | `CONTEXT/INTEGRATIONS/vista.md` |
| Core backend (routers, services, tables) | `CONTEXT/backend/01-CORE.md` |
| ERP backend | `CONTEXT/backend/02-ERP.md` |
| PF backend | `CONTEXT/backend/03-PF.md` |
| Database inventory per schema | `CONTEXT/backend/04-DATABASE.md` |
| AI features (OpenAI, embeddings, summaries) | `CONTEXT/backend/05-AI-FEATURES.md` |
| Therapy backend | `CONTEXT/backend/06-THERAPY.md` |
| Auth + security deep-dive | `CONTEXT/backend/07-AUTH-SECURITY.md` |
| Daily Life backend | `CONTEXT/backend/08-DAILY-LIFE.md` |
| Core frontend | `CONTEXT/frontend/01-CORE.md` |
| ERP frontend | `CONTEXT/frontend/02-ERP.md` |
| PF frontend | `CONTEXT/frontend/03-PF.md` |
| Therapy frontend | `CONTEXT/frontend/04-THERAPY.md` |
| Skill design (composable agent units) | `INSTRUCTIONS/01-SKILLS.md` |
| MCP integration patterns | `INSTRUCTIONS/02-MCP.md` |
| Agentic workflows | `INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md` |
| Eval strategy | `INSTRUCTIONS/05-TESTING-EVALS.md` |
| Tech stack details | `INSTRUCTIONS/06-TECH-STACK.md` |
| Artifact templates | `INSTRUCTIONS/07-TEMPLATES.md` |

---

## By situation — "when I'm doing X, read Y"

| Situation | Start here |
|---|---|
| Fresh agent, zero context | `AGENT-CONTEXT.md` → `CONTEXT/01-PHILOSOPHY.md` → `CONTEXT/02-LANDSCAPE.md` |
| About to write new backend code | `CONTEXT/PATTERNS/backend.md` + product-specific `CONTEXT/backend/0X-*.md` |
| About to write new frontend code | `CONTEXT/PATTERNS/frontend.md` + product-specific `CONTEXT/frontend/0X-*.md` |
| Touching any DB migration | `CONTEXT/PATTERNS/database-rls.md` + `CONTEXT/backend/04-DATABASE.md` |
| Adding a new product | `CONTEXT/GUIDES/new-product.md` + `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Adding a shared component | `CONTEXT/04-SHARED-LIBRARY.md` (check existing first) |
| Working on tests | `CONTEXT/PATTERNS/testing.md` |
| Adding a `try/except` (production code) | `CONTEXT/PATTERNS/logging.md` (level guide, the no-`# silent-ok` rule) |
| Adding a new keeper detector | `CONTEXT/PATTERNS/testing.md § Regression-test-the-detector` + `CONTEXT/06-AGENTS.md § Detectors` |
| Adding a helper to seed lib (deciding which layer it lives in) | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to put a new helper` |
| Looking for an existing seed-lib helper | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to look` + `CONTEXT/04-SHARED-LIBRARY.md` (catalog) |
| Working on env / deployment | `CONTEXT/PATTERNS/environment.md` + `CONTEXT/05-INFRASTRUCTURE.md` |
| Touching UI with performance data / gamification | `CONTEXT/07-GAMIFICATION.md` |
| Reading a large/unfamiliar file (default — narrow-read first) | `CONTEXT/PATTERNS/agent-reading-discipline.md § Narrow-read first` |
| About to edit `.py` / `.ts` / `.tsx` source — rename, codemod, find-callers, anything beyond a 1-line targeted edit | `CONTEXT/PATTERNS/ast.md` (AST-first; never sed/regex on source) |
| Adding any helper or function an agent might want to call (Claude Code / future bot / future product agent) | `CONTEXT/01-PHILOSOPHY.md § MCP-first` (default surface is `mcp/noctusai/`) |
| Designing a new agent / skill / MCP | `INSTRUCTIONS/00-MASTER.md` |
| Touching Vista CRM (adapter, MCP server, endpoint surface, field-set calibration) | `CONTEXT/INTEGRATIONS/vista.md` |

---

## Sync with `CLAUDE.md`

`CLAUDE.md` at the repo root is the **outer map** — slim, loaded every Claude session, contains behavioral rules + pointers into this KB.

This `INDEX.md` is the **inner map** — the KB's own authoritative self-description. Kept in sync with CLAUDE.md's map section.

Sync enforcement (pick any/all):
1. **Rule** — when you change `CLAUDE.md`'s map or any KB file/folder, update both this INDEX and CLAUDE.md. Documented in `CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`.
2. **Script** — `scripts/verify-kb-sync.sh` validates that CLAUDE.md pointers resolve to real files and all KB files are indexed. Run pre-commit.
3. **MCP tool** — `python mcp/noctusai/cli.py verify-kb-sync` (same check, integrated into the heal loop).
