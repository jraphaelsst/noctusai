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
│   ├── PATTERNS/           ← how-to technical patterns (organized by ownership 2026-05-26)
│   │   ├── common/
│   │   │   ├── absorption-ships-consume-docs.md
│   │   │   ├── accept-with-rationale.md
│   │   │   ├── agent-context-architecture.md
│   │   │   ├── agent-reading-discipline.md
│   │   │   ├── ast.md
│   │   │   ├── branching.md
│   │   │   ├── cache-locking-discipline.md
│   │   │   ├── cache-telemetry.md
│   │   │   ├── claude-md-router-discipline.md
│   │   │   ├── code-embeddings.md
│   │   │   ├── code-recurrence-baseline.md
│   │   │   ├── defer-is-not-resolve.md
│   │   │   ├── doc-to-code-drift.md
│   │   │   ├── dont-block-on-background.md
│   │   │   ├── engineer-output-linter.md
│   │   │   ├── doc-symbology.md
│   │   │   ├── drift-fix-on-contact.md
│   │   │   ├── harness-overlay-worktree-divergence.md
│   │   │   ├── kb-recurrence-radar.md
│   │   │   ├── keeper-check-before-docing.md
│   │   │   ├── keeper-pattern-cache.md
│   │   │   ├── lossless-doc-refactor.md
│   │   │   ├── methodology-codification-pipeline.md
│   │   │   ├── orphan-branch-sweeper.md
│   │   │   ├── minimum-viable-rebuild.md
│   │   │   ├── persistent-files-absorption.md
│   │   │   ├── phased-push-policy.md
│   │   │   ├── proposals-and-improvements.md
│   │   │   ├── remediation-markers.md
│   │   │   ├── roadmap-tracking.md
│   │   │   ├── scan-repetition-semantic.md
│   │   │   ├── kb-vector-search.md
│   │   │   ├── scoped-auto-improvement.md
│   │   │   ├── self-branching-mode.md
│   │   │   ├── seven-way-sync.md
│   │   │   ├── storage-hygiene.md
│   │   │   ├── unified-query.md
│   │   │   ├── vector-baseline.md
│   │   │   ├── vector-calibration.md
│   │   │   ├── vector-cost-tracking.md
│   │   │   ├── verify-seed-on-fork-base.md
│   │   │   └── versioning.md
│   │   ├── architect/
│   │   │   ├── absorbed-product-seed-shape-seam.md
│   │   │   ├── autonomous-operator-via-subagent.md
│   │   │   ├── branching-and-merging.md
│   │   │   ├── branching-dispatch.md
│   │   │   ├── dev-team.md
│   │   │   ├── dev-toolkit-scaffolders.md
│   │   │   ├── dispatch-engineer-tuning.md
│   │   │   ├── master-tree-parallel-batches.md
│   │   │   ├── mcp-first-scripts.md
│   │   │   ├── mcp-tool-conventions.md
│   │   │   ├── noc-graph.md
│   │   │   ├── parallelization-first-orchestration.md
│   │   │   ├── project-execution.md
│   │   │   ├── seed-absorption.md
│   │   │   ├── seed-canonical-defaults.md
│   │   │   ├── seed-lib-layout.md
│   │   │   ├── seed-workspace.md
│   │   │   ├── shared-library-conventions.md
│   │   │   └── two-session-architect-operator.md
│   │   ├── backend/
│   │   │   ├── backend.md
│   │   │   ├── boundary-contract-tests.md
│   │   │   ├── chatbot-operational-readiness.md
│   │   │   ├── database-rls.md
│   │   │   ├── di-test-seam.md
│   │   │   ├── digest-seed.md
│   │   │   ├── llm-tool-audit.md
│   │   │   ├── llm-usage.md
│   │   │   ├── logging-at-except.md
│   │   │   ├── logging.md
│   │   │   ├── metas-seed.md
│   │   │   ├── notifications.md
│   │   │   ├── pydantic-strict-http.md
│   │   │   ├── scheduling-seed.md
│   │   │   ├── seed-fake-real-adapter.md
│   │   │   └── whatsapp-chatbot-seed.md
│   │   ├── frontend/
│   │   │   ├── core-url-routing.md
│   │   │   ├── frontend.md
│   │   │   ├── product-icon-registry.md
│   │   │   ├── product-internal-wiring.md
│   │   │   └── svg-render-mode.md
│   │   ├── devops/
│   │   │   ├── base-image-dep-freshness.md
│   │   │   ├── ci-security-gates.md
│   │   │   ├── container-sanitization.md
│   │   │   ├── containerization-operations.md
│   │   │   ├── containerization.md
│   │   │   ├── deploy-config-contract.md
│   │   │   ├── dev-prod-parity.md
│   │   │   └── environment.md
│   │   ├── security/
│   │   │   ├── lgpd.md
│   │   │   ├── llm-bot-security.md
│   │   │   └── webhook-signatures.md
│   │   ├── compliance/
│   │   │   ├── compliance-regression-baseline.md
│   │   │   └── testing.md
│   ├── GUIDES/             ← task-oriented guides
│   │   ├── setup.md
│   │   ├── new-product.md
│   │   ├── seed-first-design.md
│   │   ├── deploy-workspace-online.md  ← "put X online" drill: verify docker artifacts → fill .env → docker compose up → verify; trigger phrases
│   │   ├── absorb-seed-workspace.md    ← absorb a separately-developed seed-workspace into noc as one product; 10 gates (snapshot → in-home → audit → interrogate → scaffold → full seed-reconcile → port+pilot-first → consumer-adapt → teardown → container-refactor → user-gated retirement); written from the proven social-wiring absorption 2026-05-16
│   │   ├── google-oauth-setup.md       ← Google Cloud Console OAuth client + Calendar API + redirect URI + env wiring; first adopter therapy-platform; reusable for any future product
│   │   └── production-deploy.md         ← fleet-grade prod deploy to a VPS: git deploy-key → build-on-VPS runtime images → noctus-net → edge (Caddy-on-real-subdomains OR CF named tunnel) + volume-preserving PaaS (Coolify) decommission + LE-negative-cache/compose/cloudflared/OpenAI-LLM lessons; from the 2026-05-21 noctusai.com migration; self-contained
│   ├── INTEGRATIONS/       ← per-vendor integration references (auth, endpoints, error model, adapter contract)
│   │   ├── oauth-patterns.md ← cross-provider OAuth reference — 5-layer model + 5 patterns + G1-G6 gotchas + Meta token-chain/auth-matrix + Google↔Meta scope-discovery diff + setup-guide template + what's already in seed vs the residual gaps
│   │   ├── meta.md         ← Meta (Facebook Pages + Instagram Graph) consume-side reference — `noctusai_lib.integrations.meta` `__all__` + factory auth-resolution (system_user → user_oauth → Fake) + consume recipe + read-only-v1 gaps
│   │   ├── whatsapp.md     ← WhatsApp connector consume-side reference — `noctusai_lib.integrations.whatsapp` `__all__` + WAHA vs Meta-Cloud-API backends + factory + webhook-router seam + lid-auth/dedup
│   │   ├── google.md       ← Google integrations consume-side reference — Calendar/Maps/YouTube/Drive/Gmail `__all__` + factories + resolver injection + quota-cost docs + Gmail OAuth-only send+read v1 + seed-ahead consumer status
│   │   ├── vista.md        ← Vista CRM REST API — public docs + live-probe results + adapter contract folded into one
│   │   └── image-gen.md    ← Image generation consume-side reference — `noctusai_lib.integrations.image_gen` `__all__` + `get_image_gen_adapter` factory + Fake/Gemini-Real adapters + renderer-agnostic Protocol + cited social-wiring consumer + backend-extension recipe
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
| Backend patterns (auth, SSO, RLS, N+1, services) | `CONTEXT/PATTERNS/backend/backend.md` |
| Frontend patterns (mobile-first, TanStack Query, hooks) | `CONTEXT/PATTERNS/frontend/frontend.md` |
| Testing discipline (3 layers, mocking, auth boundary) | `CONTEXT/PATTERNS/compliance/testing.md` |
| RLS + DB rules (`auth.uid()` subquery, search_path) | `CONTEXT/PATTERNS/backend/database-rls.md` |
| Environment vars (single `.env`, VITE_ prefix, CORS) | `CONTEXT/PATTERNS/devops/environment.md` |
| Notifications (`public.notifications`, field mapping) | `CONTEXT/PATTERNS/backend/notifications.md` |
| Shared-library conventions (privatize / absorb / rename; catalog tool) | `CONTEXT/PATTERNS/architect/shared-library-conventions.md` |
| Project execution (phase-header ticks, improvements block, improvements.md retrospective tool) | `CONTEXT/PATTERNS/architect/project-execution.md` |
| Proposals & improvements (two systems — per-project folders, ONE bundled proposal per phase, promote boundary) | `CONTEXT/PATTERNS/common/proposals-and-improvements.md` |
| LGPD awareness (keeper principle, the five questions, noctus.dev.lgpd_flag tool) | `CONTEXT/PATTERNS/security/lgpd.md` |
| LLM usage tracking (SupabaseUsageSink, /api/llm/usage, cost estimation, RLS scoping) | `CONTEXT/PATTERNS/backend/llm-usage.md` |
| Logging convention (when-to-log, level guide, no-`# silent-ok` rule, correlation IDs) | `CONTEXT/PATTERNS/backend/logging.md` |
| Seed-lib layout (6 layers — primitives/config/testing/integrations/domain/api — where to put new helpers, where to find existing ones) | `CONTEXT/PATTERNS/architect/seed-lib-layout.md` |
| Agent reading & research discipline (narrow-read first; Explore delegation rule forthcoming) | `CONTEXT/PATTERNS/common/agent-reading-discipline.md` |
| Webhook signature verification (the four shapes: Hub-Signature / hex HMAC / Svix / Stripe SDK; constant-time compare; helper module in `noctusai_lib.security.webhook_signatures`) | `CONTEXT/PATTERNS/security/webhook-signatures.md` |
| Accept-with-rationale catalog (durable home for every legitimate divergence on the platform — survives project folder deletion; how to add / retire entries) | `CONTEXT/PATTERNS/common/accept-with-rationale.md` |
| Remediation markers — greppable in-code deferral for batch evaluation: the `NOC-REMEDIATE[<class>]: <what + why> — <date>` token (distinct from the ~1.7k noisy `TODO`s); a sanctioned NON-silent deferral channel (the marker is the named destination, satisfying defer-with-destination); NOT for fix-on-contact-able bugs, NEVER on an `except` (no error-suppression — the retired `# silent-ok` shape); batch sweep `grep -rn NOC-REMEDIATE` ∨ by class; recurrence `N≥3` ⇒ promote to a project/seed lift; Stage-4 candidate `noctus.dev.scan_remediation_markers` | `CONTEXT/PATTERNS/common/remediation-markers.md` |
| AST-driven code edits (libcst for Python / ts-morph for TypeScript / tree-sitter cross-language; recipes for rename / find-callers / codemods; anti-patterns; boundary rule) | `CONTEXT/PATTERNS/common/ast.md` |
| MCP tool conventions (3-segment dotted naming `noctus.dev.* / noctus.business.* / google.* / openai.*`, Pydantic In/Out per tool, hierarchical registration, lazy `NoctusContext` for business-logic tools, settings shim, MCP-first principle) | `CONTEXT/PATTERNS/architect/mcp-tool-conventions.md` |
| MCP-first scripts — `scripts/` specialization of MCP-first: new automation defaults to a `noctus.dev.*` MCP tool (+ `cli.py` flag + colocated `Test*`), NOT a `scripts/*.sh\|*.py` one-off; three named structural carve-outs (`[carve:hook]` git-hook entry → thin dispatcher · `[carve:bootstrap]` pre-venv · `[carve:docker]` thin docker-orch), each requiring an accept-with-rationale entry; classification manifest §3 = durable single source of truth, parsed by `check_new_script_lacks_mcp_analog` (asserts every top-level `scripts/*.{sh,py}` has a bucket row — undecided new script = warning) | `CONTEXT/PATTERNS/architect/mcp-first-scripts.md` |
| Seed workspace (sibling-of-noc consume-only workspace; symlinks all 8 noc surfaces; pre-commit hook + chmod + KB rule = three-layer "templates can't modify noc" defense; promotion manifest for additions; bootstrap script + workspace.py resolver + `noctus.dev.promote_from_seed_workspace` MCP tool) | `CONTEXT/PATTERNS/architect/seed-workspace.md` |
| LLM tool-call audit (`tool_call_audits` per-product table; `noctusai_lib.domain.ai.tool_audit::AuditRecord` + `make_audit_writer`; best-effort write; LGPD redaction at consumer; common BI queries) | `CONTEXT/PATTERNS/backend/llm-tool-audit.md` |
| LLM bot security (defense trio: output sanitization + Pydantic-arg validation + rate-limit; confirm-then-execute for destructive tools; prompt-injection mitigation via instruction sandboxing + allowlists; baseline checklist) | `CONTEXT/PATTERNS/security/llm-bot-security.md` |
| Digest service primitive (`noctusai_lib.domain.digest`: `BaseDigestService` template-method base + `DigestWindow`/`DigestResult` types; 4-adopter cluster — core/audit, daily-life/weekly-review, mailing/campaign-debrief, PF/monthly-narrative; non-fits: ERP/metas-digest + daily-life/daily-brief documented) | `CONTEXT/PATTERNS/backend/digest-seed.md` |
| Scheduling primitive (`noctusai_lib.domain.scheduling`: engine + `TravelLookup`/`Conflict`/`Scorer` Protocols + `ZeroTravelLookup`/`DefaultConflict`/`DefaultScorer` defaults; wiring recipe; what stays consumer-side) | `CONTEXT/PATTERNS/backend/scheduling-seed.md` |
| Metas / goals primitive (`noctusai_lib.domain.metas`: `Goal`/`Target`/`Progress`/`Period`/`Contribution` value objects, `GoalStatus`/`PeriodKind` enums, `compute_progress` / `accumulate_contribution` / `period_bounds` / `proportional_target` / `next_status` pure functions, `GoalRepository` Protocol seam; lifted from PF/ERP/daily-life N=3 MUST-FORMALIZE; wiring recipe + status mapping + what stays consumer-side) | `CONTEXT/PATTERNS/backend/metas-seed.md` |
| WhatsApp connector + chatbot framework (`noctusai_lib.integrations.whatsapp` WAHA parser/sender/router + `noctusai_lib.domain.chatbot` buffer/worker/dispatcher/summary + `noctusai_lib.integrations.{google_calendar,google_maps}` adapters; wiring recipe; debounce-race documented; what stays consumer-side) | `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md` |
| Master-tree parallel batches (multi-product orchestrator: same-shape phases across N children execute as synchronized batches; live patterns log + absorption catalog as shared scratchpad; sync-gates pre/mid/post; divergent-batch carve-out; agent collaboration mechanics) | `CONTEXT/PATTERNS/architect/master-tree-parallel-batches.md` |
| Branching — the unified methodology (FRONT-DOOR for all branching/worktree/dispatch): the one primitive (isolate writes in a worktree off `origin/dev` → integrate clean → never switch a shared `HEAD`) · decision spine (read→dev · solo→self-branch · parallel→dispatch · multi-product→master-tree) · the worktree-sensitivity MAP (tools that read the working tree ⇒ phantom regressions on a busy checkout; verify on a clean worktree before chasing a red) · known-errors bump catalog (B1–B13) · self-improvement loop (bumps → catalog → three-way sync → Stage-4); routes into self-branching-mode / branching-dispatch / branching-and-merging / master-tree-parallel-batches | `CONTEXT/PATTERNS/common/branching.md` |
| Branching and merging methodology — end-to-end git workflow (when to branch, how to branch from `origin/main`, push semantics — branch-to-branch + branch-tip-to-main fast-forward, naming convention, mental-model upgrade, anti-patterns; non-FF integration, multi-branch convergence, conflict resolution discipline, long-running branch maintenance, recovery from bad merges) | `CONTEXT/PATTERNS/architect/branching-and-merging.md` |
| Branching-dispatch — the parallel-agent operations RUNBOOK (sibling of branching-and-merging.md's reference): when-to-dispatch (trigger phrases + inline cutoff) · 3-branch model (main frozen / `feat/<project>` integration / `feat/<project>-<slice>` worker — DASH form, slash collides with the leaf integration ref) · 10-step protocol (decompose file-disjoint → isolated worktrees → dispatch-in-one-message → collect signal [branch·HEAD·files + `/tmp` patch overlay-divergence safety] → detect collisions: (a) path-overlap git-flags + (b) SEMANTIC-DUPLICATE different-paths-same-content architect-must-catch → merge `--no-ff` provenance → dedicated honest reconciliation commit keeping agents' commits → verify → cleanup → gate `main` at 100%) · Worker Contract paste-in · safety rules; absorbed from the knowledge-extractor sibling repo 2026-05-23, reconciled with noc's collision-class/wave/overlay-safety/dispatch_preflight additions | `CONTEXT/PATTERNS/architect/branching-dispatch.md` |
| Dispatch-engineer tuning — making background engineers FAST ∧ CHEAP (per-engine efficiency layer under branching-dispatch.md): a live audit measured a dispatched engineer booting at ~65k tokens before any work, most of it waste (a ~400-name deferred-tool list it never calls; root: `engineer-default.md` shipped without a `tools:` allowlist ⇒ inherited all tools); levers — L1 scope `tools:` (`Bash,Read,Edit,Write,Grep,Glob,mcp__noctusai__*` — removes the deferred bloat, confirmed real token cut + least-privilege + no `Agent` ⇒ engineers can't dispatch) · L2 `model: sonnet` default + architect Opus-per-dispatch escalation (the wall-clock lever, reversible 1-line knob) · L3 worktree env pre-wire (`task_branch … wire_env=True`) · L4 scoped verification (engineer narrowest-check; full gate = architect's single integration run) · L5 tight briefs (exploration not model-speed dominates a loose dispatch) · L6 stale-worktree hygiene; repeatable measurement = read the engineer's first-message `usage` in its task JSONL; born 2026-05-25 | `CONTEXT/PATTERNS/architect/dispatch-engineer-tuning.md` |
| Seed Fake+Real adapter pattern — canonical shape (Protocol + Fake + Real + factory) for IO-touching seed modules; gold-standard reference modules; exemption test for pure-logic/pure-crypto modules; backfill audit trail | `CONTEXT/PATTERNS/backend/seed-fake-real-adapter.md` |
| SVG render mode — deterministic brand-locked slides (the media-creator absorption residual): the seed **`noctusai_lib.integrations.svg_render`** primitive (SVG→PNG via `resvg-py` — self-contained Rust wheel, NO system libs ⇒ slim-image-safe — + **bundled OFL fonts** Cormorant+Inter passed `skip_system_fonts=True` for dev↔prod-parity text; Protocol+Fake+Real+factory) **and** its first consumer the **`svg` render mode** in `social-wiring/media_creation` (`render_post(mode="svg")`: `DesignTokens` generic premium/educational presets + per-brand `mc_brand_kits.design_tokens` JSONB override + 4 token-driven role builders cover/develop/insight/cta, XML-escaped; `svg_markup` persisted, PNG as `data:` URL or via `upload_url_resolver`); forward migration `002`; slim-smoke-verified | `CONTEXT/PATTERNS/frontend/svg-render-mode.md` |
| Seed absorption methodology + tools — the **absorption + fusion + optimization trio** (cross-product / cross-tool / intra-file scopes): `noctus.seed.scan_repetition` / `list_capabilities` / `audit_drift` / `absorb_file` / `specify_capability` / `report` rollup / `scan_fusions` meta-detector / `scan_optimizations` intra-file detector + **`noctus.hound.scan`** trio orchestrator (keeper-analog for code hygiene); four absorption strategies (delete dead code / move-and-re-export / factory / template + runtime substitution); per-candidate loop (scan → evaluate → self-audit → absorb → re-scan → build-verify); safety rules; relation to DRY recurrence rule + delete_product symmetry | `CONTEXT/PATTERNS/architect/seed-absorption.md` |
| Containerization (multi-layer Docker: per-product `docker-compose.yml` + root orchestrator with `include:` + shared `noctus-net` fabric + per-product isolation networks; canonical Dockerfile/compose pattern at `products/seed/`; `./start.sh` Docker-default with `tunnel <slug>` cloudflare quick-tunnel mode for OAuth/webhook/demo testing; native legacy mode preserved; build process / layering / image footprint / network security model / troubleshooting / improvement backlog) | `CONTEXT/PATTERNS/devops/containerization.md` |
| Containerization OPERATIONS (runbook + methodology sibling to containerization.md's architecture: source-of-truth chain · operational primitives · growing codified-bumps catalog · diagnostic flowchart A-G · 8-step safe-change methodology · meta-arc) | `CONTEXT/PATTERNS/devops/containerization-operations.md` |
| Chatbot operational readiness — production-hardening checklist for LLM chatbot products: 6 pillars (retries on transient external writes via `retry_call` composing seed `RetryPolicy` / structured logs via seed `configure_logging` / health endpoint via `standard_routers=["health"]` / `DEPLOYMENT.md` shape / Supabase backups + critical-tables enumeration / metrics-sink seam with `NoopCounter` default); first adopter imobi-scheduling; therapy/mailing/PF inherit at N=2 | `CONTEXT/PATTERNS/backend/chatbot-operational-readiness.md` |
| CI security gates — 3-layer PR security pass (Trivy fs + image dep scans, bandit Python SAST, gitleaks secrets scan); allowlist patterns at repo root `.trivyignore` / `bandit.yml` / `bandit-baseline.json` / `.gitleaks.toml`; canonical job shape (action pin + SARIF upload `if: always()` + exit-code gate); baseline-grandfathering for pre-existing findings; relationship to accept-with-rationale catalog | `CONTEXT/PATTERNS/devops/ci-security-gates.md` |
| Storage hygiene — the **`mole`** (3rd member of the keeper/hound/mole trio: regulatory/curatorial/custodial); three orthogonal scopes (**artifacts** regenerable caches/builds / **environments** venv+node_modules duplication — advisory-only / **worktrees** stale `.claude/worktrees/agent-*/`); single entry point `python mcp/noctusai/cli.py --mole scan`; destructive `sweep --force` (dry-run default); active triggers (pre-dispatch + pre-commit + bootstrap); safety constraints (never deletes uncommitted/main/sibling/unmerged/`.env`/migrations); severity grading; bash-3.x compat mandate (the `mapfile` silent-no-op gap that motivated the rule) | `CONTEXT/PATTERNS/common/storage-hygiene.md` |
| Autonomous operator via subagent — **Option D** (fusion of single-session continuity + specialized-subagent-per-tick): `ScheduleWakeup` fires → architect spawns `orchestrator-operator` subagent (defined at `.claude/agents/orchestrator-operator.md`) → subagent drains the `## Pending` queue in `.claude/dispatcher.md` (dispatch-engineer / validate-worktree / cherry-pick-and-push / archive-project) in **isolated context** → appends the `## Outbox` section audit log → returns single summary text → architect main context stays clean for user ideation. A vs B vs C vs D comparison; 8-step flow; adaptive cadence (15min idle / 5min dispatch-heavy); FF-merge-to-main remains architect-only; setup recipe; anti-patterns | `CONTEXT/PATTERNS/architect/autonomous-operator-via-subagent.md` |
| Two-session Architect/Operator pattern — split one Claude Code workspace into two concurrent sessions (A = Architect: conversation / planning / KB / memory writes / NO git; B = Operator: ALL git ops + engineer dispatch execution + hound/mole/verify sweeps); coordination via gitignored `.claude/dispatcher.md` (unified Inbox `## Pending`/`## Completed` + Outbox `## Outbox`); strict ownership maps (git / memory / KB / MCP); anti-patterns (concurrent git push, both editing outbox, operator surfacing to user, memory clobbers); setup recipe + smoke test + `/loop` variant + 5-question pilot-vs-defer rubric + Option-D (single-session subagent) trade-off table | `CONTEXT/PATTERNS/architect/two-session-architect-operator.md` |
| Methodology codification pipeline — the 4-stage path that turns conversation rules into deterministic keeper detectors (Stage 1 emerges → Stage 2 memory entry → Stage 3 KB pattern doc + CLAUDE.md pointer → Stage 4 `check_*` function with colocated test); names the keeper as the **codification layer** of the methodology rather than a regulatory silo; codification criteria (deterministic predicate + recurrence ≥3 + clear remediation); 5 worked examples walked through all 4 stages (LGPD-first, webhook 5-pin, status-code-assertion rule, slowapi-pep563 gotcha, hygiene-compliance in-flight); what legitimately stays at Stage 3 (judgment-dependent / context-dependent / methodology-in-pilot / aesthetic); how to promote a rule between stages; why naming the pipeline matters | `CONTEXT/PATTERNS/common/methodology-codification-pipeline.md` |
| Doc symbology — lossless compression glossary defining a fixed-meaning symbol set (logic `∧ ∨ ¬ ⇒ ↔ ∈ ⊂ ≡ ≠ ≈`; status icons `✅ ⏳ ❌ 🔒 📋 🗑 ⭐ ⚠️`; codification stages `s1/s2/s3/s4`; triage outcomes `[F]/[R]/[A]`; counts `N≥3 N=2 Δ Σ`; prose-word abbreviations `DB/auth/config/req/res/fn/impl`); contract = lossless-swap test (reader with glossary recovers exact semantic of prose); caveman-skill provenance (`github.com/JuliusBrussee/caveman`, validated ~61-75% token cut, retrieved 2026-05-18) — adopts caveman prose-discipline layer (§6a) + lite/full/ultra intensity ladder (§3a.1), explicitly rejects caveman `→`=causal mapping (our `→`=routes is locked; divergence register in §1/§4); where to use (MASTER-PROMPTs / CLAUDE.md / KB patterns / PROJECT.md §6+§11) vs NOT (error messages / first-paragraph context / quoted user instructions / bug-fix code comments / commit messages); anti-patterns (stacking, inventing new symbols without adding here, symbol-loading low-traffic docs); reference patterns codify codification pipeline + 3-way triage + doc-code coherence + recurrence rule + status legend in 1-line forms | `CONTEXT/PATTERNS/common/doc-symbology.md` |
| Lossless doc-refactor — the standing framework for any change to the durable doc-set itself (CLAUDE.md / KB / MEMORY.md / `.claude/agents` / MASTER-PROMPTs); fires on "compact / token-optimize docs", "refactor doc/architecture structure", "merge/split rules", "fold in an external pattern"; prime directive = lossless **proven not asserted** via 5 diff gates (pointer-set / rule-section / line-structure / index-pointer / hook-grade — line-structure is a distinct gate per the 2026-05-18 newline-eaten-by-Edit lesson); gated-aggressiveness ladder (s-lossless no-approval · s-moderate show-diff-first · s-plan-only); source-of-truth trim rule (cut only what the pointer target provably carries; registers/catalogs/ledgers are data not prose); symbol-first caveman-aligned + `check_doc_symbology_drift` zero-drift enforcement; safe parallelization = strictly file-disjoint worktree off real-HEAD + architect true-disk 100%-certification before merge + inline-architect fallback if not disjoint; fix-on-contact during refactor; three-way-sync close-out; the doc governs itself | `CONTEXT/PATTERNS/common/lossless-doc-refactor.md` |
| CLAUDE.md router discipline — CLAUDE.md is the always-on auto-loaded router; §1 carries PRINCIPLE + MAP (rule + one-clause why + `→` pointer, one line each), PROCEDURE lives in `.claude/skills/noc-*`, depth in `KB § …`; the v4.0 **synthesis** = moderate §1 (why-based, higher quality) + aggressive §2 (shortlist + `→ INDEX.md`, no duplicated roster → drift-free); 3 deterministic invariants (whole-file word budget ≤2500 / each §1 rule one-line carrying `→` ≤60 words / no §1 prose bodies) gated by Stage-4 keeper `check_claude_md_router` (registered in `check_all_products` + `--check-claude-md-router` pre-commit block; mirrors `check_doc_symbology_drift`; colocated `TestClaudeMdRouter`); three poles preserved in `backup/` (original/aggressive/moderate); born `harness-agents-skills` 2026-05-25 | `CONTEXT/PATTERNS/common/claude-md-router-discipline.md` |
| Compliance regression-baseline gate — why `score==100` is aspirational not a regression detector; the Option-A re-spec (no NEW high/critical vs a committed fingerprint baseline + absolute score informational); line-churn-robust fingerprint; env-artifact exclusions; the deterministic `refresh_compliance_baseline.py` contract; where the 2 gate tests / fixture / regenerator live | `CONTEXT/PATTERNS/compliance/compliance-regression-baseline.md` |
| DI-test seam — the named remediation convention for the `test_patch_target` / self-monkeypatch compliance class; the rule (no `patch`/`monkeypatch` of our own symbols) + the 3 legitimate seams (DI default · `MockRequestBuilder.inserted_payloads` read-side · external-boundary-only); routes to the full refactor playbook in `testing.md` | `CONTEXT/PATTERNS/backend/di-test-seam.md` |
| Logging-at-except — the named remediation convention for the silent-except compliance class; every `except` logs ∨ raises ∨ returns-error-bearing; no `# silent-ok` escape hatch (retired 2026-04-28); level guide; routes to the full when-to-log rationale in `logging.md` | `CONTEXT/PATTERNS/backend/logging-at-except.md` |
| Absorption ships consume-docs (R1) — an absorption is not complete until its consume-side `KB § INTEGRATIONS/<x>.md` ships in the SAME project that lifts the code; doc carries what-ships / consume-recipe-via-named-seams / auth-modes / gaps; documentation sibling of "absorption = methodology-epoch merge — reconcile the derived surfaces"; evidence social-wiring-absorption lifted meta/whatsapp/google but shipped zero consume docs; completeness test + 4 anti-patterns; sibling of R5; s1→s3 with s4-keeper candidate noted | `CONTEXT/PATTERNS/common/absorption-ships-consume-docs.md` |
| Verify-the-seed-ships-it binds to the engineers' fork base (R2) — the architect's dispatch-time check runs `git ls-tree origin/main -- <path>` (the tree the worktree forks from), NOT `ls` in the architect's working tree; unmerged feature-branch lifts are invisible to engineers; the existence-in-some-tree vs existence-in-fork-base conflation; evidence META + DOCS-CONSUME both correctly STOPPED on stale origin/main (full re-dispatch wave cost); structurally cured by R4 (keep origin/main current); pairs with §16.7 preamble | `CONTEXT/PATTERNS/common/verify-seed-on-fork-base.md` |
| Phased-push policy for large commit backlogs (R4) — long-lived feature branches phase-merge to main at project/wave-close boundaries only when 100%-sure (touched-product builds ∧ pytest ∧ verify-kb-sync ∧ increment criteria); ≥1 closed-project unmerged is the phase-push signal; human-gated protocol (architect PRESENTS push cmd + range + evidence → user explicit per-increment go/no-go → architect executes; direct-to-main without presented+approved gate forbidden, harness-classifier-enforced); `scripts/merge-debt-monitor.sh` custodial sibling of disk-usage/mole/hound wired pre-dispatch + project-close; structural cure for the R2 stale-fork-base class; proven end-to-end A→B→C→D 2026-05-18 | `CONTEXT/PATTERNS/common/phased-push-policy.md` |
| Defer ≠ resolve (R5) — a follow-up project filed for work already inside the active project's explicit scope is a deferral slip, not a triage outcome; the recurrence/triage register + "file a follow-up" is for newly-discovered cross-cutting work, never de-scoping the active brief; scope test = "was this in the user's original explicit ask / stated scope?" (yes ⇒ resolve in-project); evidence gmail-seed-lift filed for Gmail though "google = …+gmail+…" was the original ask; sibling of R1 (both completeness ≠ deferral); legitimately stays s3 (scope test is judgment-dependent) | `CONTEXT/PATTERNS/common/defer-is-not-resolve.md` |
| Harness overlay ⊥ worktree divergence (R6) — the harness file overlay can report `Edit`/`Write`/`Read` success while the on-disk git worktree stays clean (work overlay-only, lost when agent ends); the agent's OWN git status/grep are served the same diverged overlay so naive self-verification passes falsely; engineer-side recipe (stage → git diff --cached + grep -c the ACTUAL file → re-author via Bash on divergence → paste proof lines); architect-side (verify every salvaged worktree from own separate Bash context; divergence-clean ⇒ apply architect-inline, never loop-redispatch; "nothing to commit" is the tell); ≥2 lost-work incidents (DOCS-CONSUME-2 recovered / SW-RLS vanished twice); strict instance of codebase-is-source-of-truth; engineer-default §1a is the enforcement surface | `CONTEXT/PATTERNS/common/harness-overlay-worktree-divergence.md` |
| Dev↔prod parity — verify in the PRODUCTION SHAPE, not just dev-green (the DISCIPLINE; executable form = deploy-config-contract). "Works in dev" ≠ "works in prod": the slim prod image is STRUCTURALLY different (no `start.sh`/registry/`node`, baked `dist`, env-only config) ⇒ code deriving from a dev-only artifact or a dev-convenience default silently breaks in prod; the platform's **highest-recurrence drift class** (N≥3 — infra.tsx-localhost / nav→localhost / CORS-registry-empty-in-slim, apex login down); §2 dev↔prod difference checklist (open taxonomy) + §3 authoring-time parity question + §4 deploy-time live-probe; special cases = seed-canonical-defaults (wrong value) / boundary-contract-tests B4 (env propagation) / containerization §12b (stale container); born 2026-05-22 (nav-remap → prod-CORS) | `CONTEXT/PATTERNS/devops/dev-prod-parity.md` |
| Deploy-config contract — the EXECUTABLE form of dev↔prod-parity §2/§4: every dev↔prod-divergent config knob routes through the seed deploy-config primitive (`noctusai_lib.config.deploy_config` — `resolve_config` / `require_prod_config` / `is_deploy_context` / `MissingProdConfigError`; canonical default ∧ aggregate-fail-loud-if-required-in-prod, no-op in dev) ⇒ a product cannot silently ship a dev value to prod (the nav→localhost / CORS-empty / infra.tsx-localhost class, N≥3); consume recipe + Wave-2 startup guard wired into `create_product_app` + the `check_derives_from_dev_only_artifact` keeper (flags seed code deriving from a dev-only artifact without an env fallback) + the parity-checklist→seam table; value-correctness sibling = seed-canonical-defaults; shipped via `projects/seed-deploy-config-contract` 2026-05-23 (parallel branching-dispatch: A primitive / B keeper / C docs) | `CONTEXT/PATTERNS/devops/deploy-config-contract.md` |
| Seed defaults are canonical-shared answers, not consumer-#1 coincidences — a seed fallback literal (`\|\| "X"` / `getenv(..., "X")`) must be the **architectural canonical answer** for the module's contract (e.g. same-origin `""` for the house single-container HTTP model), not a value that happens to work for consumer #1; the bug stays silent because consumer #1 works + consumers #2..N either mask-by-override or misroute-with-opaque-error; "no canonical answer at seed-level" carve-out (`""` / `None` / typed-error, never a literal pretending to know); **paired rule**: multi-stage Dockerfile env-inheritance (stage A's ENV doesn't reach stage B unless `B FROM A` — every build-running stage re-declares); worked examples table (HTTP URL · DB schema · auth · LLM model · storage · webhook · Redis); detection-by-keeper deferred to N=3; bit 2026-05-20 social-wiring (`infra.tsx` defaulted to `localhost:8000` → silent CORS misroute → "Servidor indisponivel" toasts) | `CONTEXT/PATTERNS/architect/seed-canonical-defaults.md` |
| Boundary-contract tests — named class for "tests-green-dashboard-red" bugs where unit tests cover each side of a seam but nothing covers the **contract crossing it**; five recurring boundaries (B1 build-injection via vite define / B2 HTTP schema FE↔BE caps / B3 third-party library contract — TanStack v5 `queryFn` return-type / B4 container env propagation across .env→stage→runtime / B5 library-default propagation from seed default to N consumers); each shape has the same anatomy (contract crosses process/build/wire/runtime boundary · each side independently tested · contract itself untested · bug surfaces only in production-shape execution); authoring-time discipline ("if this contract drifts, what existing test fails?" — none ⇒ file boundary test or accept-w/-destination); §4 shipped-detector status table by boundary; §5 detector specification for `check_query_fn_returns_undefined` (Stage-4 keeper, AST-light brace walk over `queryFn:` arrow bodies, escape hatch `query-fn-undefined-ok`, 0 live baseline at ship time); §7 anti-pattern (more unit tests = same class re-emerges; structural fix = static detector for B1/B3/B5 + contract-extraction or runtime smoke for B2/B4); recurrence-rule integration (N=1 fix in-flight + memory / N=2 triage / N=3 MUST formalize); bit chain 2026-05-20 social-wiring (`infra.tsx` localhost:8000 / vite-factory `\|\| 8000` / ENCRYPTION_KEY-empty / `le=20`-vs-top-50 / useLLMSpend-`return undefined`-data-is-undefined) | `CONTEXT/PATTERNS/backend/boundary-contract-tests.md` |
| Core-URL routing — the **MANDATORY** system for how a product reaches core (SSO callback, "back to dashboard" nav, any product→core XHR): resolve core's URL through the canonical seed getter `env.CORE_URL` / `env.CORE_API_URL` (`@noctusai/lib`, source `seed/lib/frontend/src/env.ts`) — NEVER hand-roll `import.meta.env.VITE_CORE_* \|\| "<literal>"`; the recurrence it closes (N≥3, prod SSO outage 2026-05-25): a bare `localhost:8000` default → "Failed to fetch" for any product baking only VITE_CORE_URL, a stale `localhost:5173` default (dead pre-house vite port) → dead nav; getViteVar dynamic access proven prod-safe (createProductSupabase reads env.SUPABASE_* the same way); the ONE legitimate hand-roll = core's same-origin `lib/api.ts` (window.location.origin fallback); new products get working SSO+nav **by construction** (seed `app.tsx` SSOCallback + `products/seed` template pages + Dockerfile VITE_CORE_URL bake); two-layer system (FE→core getter + launcher→product `resolve_product_url`); enforced by the `check_handrolled_core_url` Stage-4 keeper (high; carve-out core api.ts); siblings boundary-contract-tests B1 / seed-canonical-defaults / dev-prod-parity | `CONTEXT/PATTERNS/frontend/core-url-routing.md` |
| Dev↔prod parity — UMBRELLA class: "works in dev" ≠ "works in prod"; a change is **not done** until verified in the **production shape** (slim image / live VPS), not just dev-green; the slim prod `runtime` image is structurally **not** a dev box — ships **no `start.sh`/PRODUCTS registry, no node, baked `dist`, env-only config** → code that derives behavior from a dev-only artifact (registry, build tool) or sets a dev-convenience default silently breaks in prod; the **noc dev↔prod difference checklist** (start.sh-absent · node-absent · `VITE_*`-baked-at-CI-build · BE-config-env-only-must-be-SET · DB-`url_base`-localhost-by-design-override-via-env · CORS-must-include-prod-origins-derive-from-`PRODUCT_URL_<SLUG>`-env-directly · `public.products`-rows-only-what-was-mirrored · CI-installs-root-superset-not-per-product-reqs · LLM-OpenAI/Gemini-no-Anthropic; **open taxonomy**); §3 authoring-time **parity question** ("does this hold in the slim prod container, not just my dev box?") + §4 deploy-time **live-probe** discipline (verify FE bake, OPTIONS-preflight the prod origin, keep the override safety during a risky cutover); [[seed-canonical-defaults]] (wrong value) / [[boundary-contract-tests]] B4 (env propagation) / [[containerization]] §12b (stale container) are **special cases**; detection — wrong-value sub-class already Stage-4 (`check_seed_canonical_default`), derives-from-dev-only-artifact sub-class Stage-3 deferred-to-N=2, verify-in-prod-shape judgment-dependent Stage-3-by-design; bit chain 2026-05-20 `infra.tsx`-localhost + 2026-05-22 nav→localhost + CORS-registry-empty-in-slim-container (apex login `Servidor indisponível`) | `CONTEXT/PATTERNS/devops/dev-prod-parity.md` |
| Rebuild only modified products, never the whole fleet — container rebuild scope = the products whose code was actually modified this session (`git diff --name-only origin/main..HEAD` → `products/<slug>/` prefixes), NOT the fleet (even when a seed-level change technically affects every product); other products catch up **lazily** on their next own-modify rebuild because every Dockerfile `FROM noctus-seed-*-base` (the structural cure); per-change-shape scope table (seed-only → base images only · 1 product → just that product · N products → just those N · fleet smoke-test → explicit-ask carve-out) + 2026-05-20 worked example + when-to-fan-out carve-outs (explicit user ask / fleet-blocking validation / CI) + composes with [[pilot-products-first]] (3-pilot bound for validating; modified-only bound for normal-dev building) + [[estimate-off-evidence]] (read the diff, don't assume from "seed touches the fleet"); bit 2026-05-20 — fleet-wide rebuild reflex repeated mid-session after parallel-build daemon crash despite the user having a learned-error tag on it | `CONTEXT/PATTERNS/common/minimum-viable-rebuild.md` |
| First clone + starting servers | `CONTEXT/GUIDES/setup.md` |
| Creating a new product | `CONTEXT/GUIDES/new-product.md` |
| Seed-first design checklist (cross-product projects — REQUIRED at authoring time) | `CONTEXT/GUIDES/seed-first-design.md` |
| Putting a workspace product online for testing — the "deploy" drill (verify docker artifacts → fill `.env` → `docker compose up` → verify); trigger phrases the agent should recognise | `CONTEXT/GUIDES/deploy-workspace-online.md` |
| Absorbing a separately-developed seed-workspace into noc as one product — the repeatable 10-gate procedure (Gate 0 snapshot-preserve + sanctioned `--no-verify` · Gate 1 bring-source-in-home BEFORE plan depends on it + worktree-base-vs-uncommitted-inputs trap · Gate 2 completeness audit / UNMAPPED-useful · Gate 3 interrogate disposition before deletion · Gate 4 scaffold house-container · Gate 5 full seed-reconcile sibling-validated-wins + verify-the-seed-ships-it 4 shapes + master-tree-parallel zero-git + git-stash-forbidden · Gate 6 port + pilot-first + pause-on-dependency · Gate 7 mechanical consumer-adapt + git-log-S-before-attribution · Gate 8 teardown preservation-FIRST + hazard-group commits + registry-derive + content-form dangling-ref verify + KB-count-autostage footgun · Gate 9 container-refactor + user-gated workspace retirement); written from the proven social-wiring absorption 2026-05-16; self-contained | `CONTEXT/GUIDES/absorb-seed-workspace.md` |
| Google Cloud Console OAuth setup — Calendar API (project + consent screen + Calendar API enablement + Web client + redirect URI registration + scopes + env-var wiring + smoke test + troubleshooting); first adopter therapy-platform per-therapist `/api/scheduling/gcal/*`; reusable for any future product needing user-delegated GCal | `CONTEXT/GUIDES/google-oauth-setup.md` |
| Production deploy of the noc fleet to a VPS (the *external server* deploy, NOT the local `./start.sh` drill) — git deploy-key code delivery · build-ON-VPS slim `runtime` images (VITE baked) · external `noctus-net` · edge **A** Caddy-on-real-subdomains (DNS-record-only path, auto-LE) **or B** Cloudflare named tunnel (zone-on-CF path) + A→B zero-URL-change migration · volume-preserving PaaS (Coolify) decommission · 6 evidence-tested lessons (LE DNS negative-cache · compose `--env-file` · `depends_on` over-start · cloudflared nonroot creds · local-resolver-lies · product-LLM=OpenAI/Gemini-no-Anthropic); from the 2026-05-21 `noctusai.com` migration; self-contained | `CONTEXT/GUIDES/production-deploy.md` |
| OAuth integration patterns — cross-provider (5-layer model · scope auto-discovery · dual auth backends · single-consent bundling · post-consent introspection · CredentialStore Fernet · G1-G6 gotchas · Meta token-chain + auth-mode matrix · Google↔Meta scope-discovery diff · setup-guide template · in-seed-vs-gap audit) | `CONTEXT/INTEGRATIONS/oauth-patterns.md` |
| Meta Graph adapter consume-side (`noctusai_lib.integrations.meta` exact `__all__` · `get_meta_adapter` auth-resolution priority system_user→user_oauth→Fake · consume recipe with cited social-wiring consumer · `make_meta_router` seam · read-only-v1 out-of-scope: posting/ads/webhooks) | `CONTEXT/INTEGRATIONS/meta.md` |
| WhatsApp connector consume-side (`noctusai_lib.integrations.whatsapp` exact `__all__` · WAHA `get_whatsapp_client` vs Meta-Cloud-API `get_meta_cloud_client` backends · `create_whatsapp_webhook_router` seam · lid-auth + dedup + response-registry · cited ERP consumer) | `CONTEXT/INTEGRATIONS/whatsapp.md` |
| Google integrations consume-side — Calendar/Maps/YouTube/Drive/Gmail (each exact `__all__` · resolver/credential-store factory injection · YouTube quota-cost-documented Protocol · Drive dual download+read Protocols · Gmail OAuth-only send+read v1 with `OAuthGmailCredentials`/`GmailCredentialResolver`/`make_gmail_client` · seed-ahead consumer status · cited social-wiring + mcp/google/tools/gmail consumers) | `CONTEXT/INTEGRATIONS/google.md` |
| Vista CRM REST API (auth, query convention, response envelope, error hierarchy, endpoint inventory, adapter contract, per-tenant calibration gap) | `CONTEXT/INTEGRATIONS/vista.md` |
| Image generation consume-side (`noctusai_lib.integrations.image_gen` exact `__all__` · `get_image_gen_adapter` factory · `FakeImageGenAdapter` deterministic-URL signal · `GeminiImageGenAdapter` lazy-SDK Real backend · renderer-agnostic Protocol · cited social-wiring/media_creation consumer; v1 Gemini-only — OpenAI/Stability/Replicate extension recipe documented) | `CONTEXT/INTEGRATIONS/image-gen.md` |
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
| About to write new backend code | `CONTEXT/PATTERNS/backend/backend.md` + product-specific `CONTEXT/backend/0X-*.md` |
| About to write new frontend code | `CONTEXT/PATTERNS/frontend/frontend.md` + product-specific `CONTEXT/frontend/0X-*.md` |
| Touching any DB migration | `CONTEXT/PATTERNS/backend/database-rls.md` + `CONTEXT/backend/04-DATABASE.md` |
| Adding a new product | `CONTEXT/GUIDES/new-product.md` + `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Adding a shared component | `CONTEXT/04-SHARED-LIBRARY.md` (check existing first) |
| Working on tests | `CONTEXT/PATTERNS/compliance/testing.md` |
| Adding a `try/except` (production code) | `CONTEXT/PATTERNS/backend/logging.md` (level guide, the no-`# silent-ok` rule) |
| Adding a new keeper detector | `CONTEXT/PATTERNS/compliance/testing.md § Regression-test-the-detector` + `CONTEXT/06-AGENTS.md § Detectors` |
| Adding a helper to seed lib (deciding which layer it lives in) | `CONTEXT/PATTERNS/architect/seed-lib-layout.md § Where to put a new helper` |
| Looking for an existing seed-lib helper | `CONTEXT/PATTERNS/architect/seed-lib-layout.md § Where to look` + `CONTEXT/04-SHARED-LIBRARY.md` (catalog) |
| Working on env / deployment | `CONTEXT/PATTERNS/devops/environment.md` + `CONTEXT/05-INFRASTRUCTURE.md` |
| Touching UI with performance data / gamification | `CONTEXT/07-GAMIFICATION.md` |
| Reading a large/unfamiliar file (default — narrow-read first) | `CONTEXT/PATTERNS/common/agent-reading-discipline.md § Narrow-read first` |
| About to edit `.py` / `.ts` / `.tsx` source — rename, codemod, find-callers, anything beyond a 1-line targeted edit | `CONTEXT/PATTERNS/common/ast.md` (AST-first; never sed/regex on source) |
| Adding any helper or function an agent might want to call (Claude Code / future bot / future product agent) | `CONTEXT/01-PHILOSOPHY.md § MCP-first` (default surface is `mcp/noctusai/`) |
| Designing a new agent / skill / MCP | `INSTRUCTIONS/00-MASTER.md` |
| Touching Vista CRM (adapter, MCP server, endpoint surface, field-set calibration) | `CONTEXT/INTEGRATIONS/vista.md` |

---

## Sync with `CLAUDE.md`

`CLAUDE.md` at the repo root is the **outer map** — slim, loaded every Claude session, contains behavioral rules + pointers into this KB.

This `INDEX.md` is the **inner map** — the KB's own authoritative self-description. Kept in sync with CLAUDE.md's map section.

Sync enforcement (pick any/all):
1. **Rule** — when you change `CLAUDE.md`'s map or any KB file/folder, update both this INDEX and CLAUDE.md. Documented in `CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`.
2. **Script** — `noctus.dev.kb_sync` validates that CLAUDE.md pointers resolve to real files and all KB files are indexed. Run pre-commit.
3. **MCP tool** — `python mcp/noctusai/cli.py verify-kb-sync` (same check, integrated into the heal loop).
