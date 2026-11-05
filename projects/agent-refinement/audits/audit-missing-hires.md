# Who else should be on the team? (audit, 2026-11-05, read-only)

## Short answer

Yes, there are four real gaps. Each has an owner today only by accident, and each has commit and memory evidence behind it.

1. **ai-engineer**: the LLM and agent builder (prompts, evals, model routing, RAG, cost). This is the biggest gap.
2. **tooling-engineer**: the engineer for the internal `mcp/noctusai` toolkit, the keepers and the caches.
3. **product-designer**: makes the clickable mockups the 2026-11-04 rule now requires, and owns accessibility.
4. **legal-advisor**: Brazilian contract, consumer and LGPD law, following the `accountant` pattern.

A fifth change is a repurpose rather than a new agent. `orchestrator-operator` is dormant and should become the **integration-steward** that owns the merge queue and the train. One more split is worth doing later: `integrations-engineer`, carved out of backend.

Your own product already planned for these roles. The in-repo agno dev team (`products/dev-team`, `KB § PATTERNS/architect/dev-team.md` §6) defines 11 roles: `qa_engineer`, `ux_designer`, `product_manager` and `technical_writer` are among them. The Claude Code team has none of those four. Below I say which ones are worth adding and which are not.

## How I measured (and where the limits are)

- **Window:** `origin/dev` since 2026-09-01. That is 4,035 non-merge commits.
- **Work by path:**
  - `products/social-wiring`: 1,020 commits
  - KB, CLAUDE.md and `.claude`: 1,096
  - `mcp/`: 644
  - `products/agents`: 281
  - `products/seed`: 32
- **Commit subjects by keyword** (counts overlap):
  - migration, rls, schema: 301
  - contract: 381
  - LLM, eval, prompt, model: 140
  - integrations (Meta, WAHA, Google, OAuth, Vista, Asaas, D4Sign…): 140
  - LGPD, privacy, consent, PII: 104
  - mockup, design-system, a11y: 30, of which 1 is a11y
- **Ownership:** 284 KB docs in total. 175 are claimed in `owns_kb:` across 13 agents. Load is lopsided:
  - backend-engineer: 72
  - devops-engineer: 37
  - architect: 32
  - frontend-engineer: 19
  - compliance-reviewer: 6
  - security: 3
  - accountant: 1
  - agents-security: 1
- **The keeper passes:** `check_agent_kb_alignment` returns 0 issues (I ran the function in-process, read-only). It passes only because `_AGENT_KB_UNOWNED_ALLOWLIST` in `mcp/noctusai/tools/noctus/dev/compliance.py` holds 86 entries: all 78 `PATTERNS/common/*` docs plus 2 architect docs plus the root docs. Many of these are domain docs, not universal commons (for example `vector-calibration`, `dispatch-token-log`, `versioning`).
- **Limit on measuring agent use:** `project-history/dispatch-budget.ndjson` has 1 row, and the `Lenses:` trailer appears once since September. Commit-message mentions are the only proxy:
  - backend-engineer: 89
  - security: 83
  - engineer-seed: 72
  - frontend-engineer: 48
  - architect: 26
  - accountant: 10
  - reverse-engineer: 10
  - devops-engineer: 6
  - agents-security: 2
  - ops-steward: 2
  - compliance-reviewer: 1
  - **skill-scout: 0, and its file is untouched since 2026-05-26**
  - **orchestrator-operator: 0, and `.claude/dispatcher.md` was last modified 2026-09-11**

## Ranked recommendations

### 1. ai-engineer: EXECUTOR, sonnet by default, opus per the dispatch-engineer-tuning §4·1 triggers

**Why.** The agents product is the platform's newest stream of work and has no specialist.
- 281 commits since September.
- 2,595 test functions.
- `products/agents/backend/app/studio/` contains `evals.py`, `eval_driver_live.py`, `eval_mecanismo*.py`, `eval_sinteticos.py`, `eval_pii.py`, `compiler.py`, `geracao*.py`, `prontidao.py` and `vazamento.py`. 115 backend files mention eval.
- There is a model-routing tool (`noctus.dev.roteamento_modelos_recalibrar`) and the `qualificacao` engine.

**The knowledge has no home:**
- No KB pattern exists for evals, judges or prompt design.
- There is no `KB/CONTEXT/PRODUCTS/agents/`.
- The LLM docs (`llm-usage`, `llm-provider-selection`, `llm-tool-audit`, `GUIDES/agent-creation`, `INTEGRATIONS/agents-org-specs`, `backend/05-AI-FEATURES`) sit inside backend-engineer's 72-doc index.
- The `noc-new-agent` skill (definition → draft → specs → evals → prontidão → publish) names no agent except security.

**Friction on record:** memory `agent-studio-eval-cost-shape` records the owner reacting to $20 in one day of live evals (an Opus generator plus a Sonnet judge on 160 cases). The live-eval cost discipline is exactly what this role would own.

**Boundary.** `agents-security` stays the adversarial reviewer. This agent builds, and that one attacks: the same builder-and-auditor split as backend-engineer and security.

**Owns:**
- Moved from backend-engineer: `backend/llm-usage.md`, `llm-provider-selection.md`, `llm-tool-audit.md`, `backend/05-AI-FEATURES.md`, `GUIDES/agent-creation.md`, `INTEGRATIONS/agents-org-specs.md`.
- New: `PATTERNS/ai/agent-evals.md` (judge vs mechanism suites, hash-pinned runs, failures-only re-runs, cost cap) and `PATTERNS/ai/model-routing.md`.
- New: `PRODUCTS/agents/` overview.

**Relieves:** backend-engineer, plus the tech-lead, who currently carries the eval and cost judgment.

**Triggers:** "eval", "judge", "prompt", "agent draft", "prontidão", "model routing", "which model", "RAG", "transcription quality", "Julia behaves wrong", "LLM cost".

### 2. tooling-engineer: EXECUTOR, sonnet

**Why.** `mcp/` is the third-largest work area: 644 commits since September, more than `products/agents` and 20× `products/seed`.
- About 300 `noctus.*` tools.
- 592 `check_*` keepers in one compliance module of more than 21k lines.
- Machinery under active work: gate_sweep, task_branch and train, hw-admission (12+8+4 commits in the last 300), caches and vectors.

No executor owns it. `engineer-seed` is a generic protocol. Architect owns `mcp-tool-conventions` only as an advisor. devops-engineer owns 6 of the cache-family docs, while the other ~16 members are unowned. This is the Team Topologies "platform team" ("Provides internal services that speed up other teams": https://teamtopologies.com/key-concepts).

**Owns** (moved off the unowned allowlist):
- Cache and vector family: `cache-auto-freshness`, `cache-locking-discipline`, `cache-telemetry`, `code-embeddings`, `code-recurrence-baseline`, `kb-recurrence-radar`, `kb-vector-search`, `keeper-pattern-cache`, `scoped-auto-improvement`, `unified-query`, `vector-baseline`, `vector-calibration`, `vector-cost-tracking`, `scan-repetition-semantic`, `product-centroid-drift`, `extractor-correctness-vs-mirror`.
- Keeper machinery: `auto-author-scaffolds`, `doc-staleness-gate`, `doc-to-code-drift`, `engineer-output-linter`, `gate-methodology-sync`.
- Taken over from devops-engineer: the 6 cache docs, so the family has one owner.
- Taken over from architect: `mcp-tool-conventions`, `dev-toolkit-scaffolders`, `noc-graph`.

**Relieves:** devops-engineer (which goes back to containers, CI and deploy) and the tech-lead.

**Triggers:** "keeper", "check_*", "MCP tool", "noctus.dev.*", "gate_sweep", "task_branch", "cache stale", "embedding", "vector", "hook", "harness".

### 3. product-designer: EXECUTOR of mockups only, opus (low volume, shown to the owner)

**Why.**
- **New mandatory step.** Memory `feedback_mockup_before_ui` and `KB § PATTERNS/frontend/prototype-on-real-data.md` (2026-11-04) make a clickable mockup a required step before any UI is coded. It must use seed tokens and the app shell, work in light and dark mode, use real data where it exists, and avoid any vendor's look (`feedback-noc-pattern-not-vendor-look`).
- **Nobody owns it.** frontend-engineer builds in worktrees, and the tech-lead does design by hand. Since 2026-11-04 this step recurs on every new screen.
- **Accessibility is effectively zero:**
  - 1 a11y commit out of 4,035.
  - 0 accessibility keepers.
  - No accessibility pattern doc.
  - This matters because the products serve the public: Store, the community portal, the white-label approval portal.

**Shape.**
- Writes HTML mockups to the scratchpad. The tech-lead publishes them as artifacts, since subagents have no Artifact tool.
- Reads the design system and the organ catalog (`noc-organ-consume-check`).
- Hands a click-through-approved mockup to `noc-contract-first`.

**Owns:**
- Moved from frontend-engineer: `frontend/prototype-on-real-data.md` and `frontend/product-icon-registry.md`.
- New: `PATTERNS/design/mockup-protocol.md`, `PATTERNS/design/accessibility.md`.

**Relieves:** frontend-engineer and the tech-lead.

**Triggers:** "mockup", "prototype", "how should this screen look", "layout", "dark mode", "a11y", "redesign".

### 4. legal-advisor: ADVISOR, read-only, opus, built like the `accountant` agent

**Why.**
- **Volume:** "contract" appears in 381 commit subjects since September. Social-wiring generates real-estate purchase-and-sale contracts (roadmaps `social-wiring-contract-automation`, `sw-contract-reliability`, `sw-parte-pj-fgts-contract`, `signature-integration-CONTRACT`, `abnt-formatting-CONTRACT`). `noctus.dev.contract_score` grades the generator against real signed contracts. Store sells a "Contrato Blindado" kit. Certidões work runs through Infosimples.
- **It is blocking work:** owner reminder `reminder_contrato_pj_qualificacao` has been open since 2026-10-02. Until the wording for company (PJ) parties is decided, the contract generator stops with the error `partes.pj_sem_qualificacao`. A legal advisor would draft the wording options, cite sources, and say when a licensed lawyer (OAB) must sign off, the same way `accountant` defers to a licensed accountant (CRC).
- **Health data:** Therapy and Monica handle LGPD sensitive data (art. 11). Today `security` owns `lgpd.md` from the technical side. The legal side has no owner: legal basis, privacy and terms texts on the seed consent routes, records of processing, and consumer-law rules for Store and Community.

**Owns:**
- New: `PATTERNS/legal/contract-clauses.md`, `PATTERNS/legal/lgpd-legal-basis.md`, `PATTERNS/legal/consumer-ecommerce.md`.
- Co-reads (does not own) the social-wiring contract docs under `PRODUCTS/social-wiring/`.

**Relieves:** the owner's open reminders and `security`'s LGPD remit.

**Triggers:** "contract wording", "cláusula", "is this legal", "LGPD legal basis", "terms/privacy policy text", "CDC", "PJ party".

### 5. Repurpose orchestrator-operator into integration-steward (no new headcount)

**Why.**
- orchestrator-operator is dormant: 0 commit mentions since September, and its dispatcher inbox has not been touched since 2026-09-11.
- Integration is where the time goes:
  - Memory `feedback_train_integrate_all_ready_branches`: each integrate takes 30–40 minutes, and 9 serial integrates come to about 5 hours.
  - Memories `feedback_branches_green_alone_break_when_merged`, `feedback_check_dev_ci_before_stacking_merges` and `feedback_prerequisite_merge_before_dispatch` record the related failures.
  - 11 memory files are about merging and integration.
  - The CLAUDE.md §1 rule "per-branch green ≠ integration green" exists because of this.
- Another session is designing a merge queue right now. It needs an owning agent from day one.

**Owns** (moved off the allowlist): `auto-generated-merge-drivers`, `phased-push-policy`, `orphan-branch-sweeper`, `session-end-sweep`, `claim-vs-evidence-shared-state`, plus the merge-queue doc that session ships.

**Model and permissions:** sonnet. Commits and pushes only `dev` and train branches; `main` stays consent-gated through `noc-ship`.

**Triggers:** "integrate", "train", "merge queue", "ready branches", "land these".

### 6. Later: split integrations-engineer out of backend-engineer (EXECUTOR, sonnet)

**Why it is worth doing:**
- backend-engineer's 72-doc index is the largest on the team and includes 21 `INTEGRATIONS/*` docs plus 3 OAuth and console guides.
- Integration volume: 140 commits since September and 19 memory files (`feedback_integration_{meta,google,whatsapp}_consume`, `integration_keys_in_db_not_env`, and others).
- The work is mostly external-console knowledge (Meta App Review, Google OAuth consoles, WAHA sessions, Asaas and Stripe webhooks), which suits a Team Topologies "complicated subsystem".

**Why it is not ranked higher:** the code is still FastAPI backend.

**Do it when:** backend dispatches start getting mis-routed or the backend agent's context grows enough to hurt.

## Considered and rejected

| Role | Why not (evidence) | Revisit when |
|---|---|---|
| QA / test engineer | Every executor writes its own tests by protocol. compliance-reviewer owns `testing.md` and the auth false-green rule. e2e churn is mostly the domain-specific contract replay (owned by the ai-engineer or social-wiring work). Only 21 e2e spec files fleet-wide. | `gate_sweep` "inconclusive" or flaky rates become a recurring finding |
| Product manager / requirements analyst | The owner forbids inferring specs (`feedback_interview_never_assume_specs`: "never guess, assume, infer"). Subagents cannot call AskUserQuestion. `noc-questionnaire` (ops-steward) and the reverse-engineer spec-gap checklist already cover question preparation. | Never as a decider; maybe as a question-batch preparer |
| Data / DB engineer | Real load (654 migration-file touches, 24 DB/RLS memories), but migrations are coupled to features through contract-first API, DB and RLS work, and security reviews RLS. A separate executor would split every feature in two. | RLS or migration incidents keep recurring after keepers |
| SRE / observability | Covered by devops-engineer, ops-steward and the `prod_watchdog` + `deploy_image` auto-rollback. Only 12 incident or rollback commits. | Fleet wakes up from prod-only |
| Methodology steward / technical writer | Docs are a quarter of commits, but the rule is that a doc lands in the same commit as the change. A separate writer would break that. Give the doc-discipline cluster to compliance-reviewer instead (below). `/gc` and `/codify` already exist, and auto-improvement has 0 open entries. | Exhaust work piles up |
| Privacy officer (DPO) | Fold into the legal-advisor (legal basis, texts) plus security (controls). | |
| Growth / marketing / content strategist | 65 content commits. IG analysis is already a skill (`noc-ig-analysis`) owned by reverse-engineer. | A paying content product |
| Customer support / CS ops | No support-channel volume in the tree. Julia is the product, not support. | |
| Data analyst / BI | accountant (DRE) and ops-steward (platform metrics) cover it. No BI product. | |

**Offsetting cost:** consider retiring or merging `skill-scout` (0 uses, file untouched since May). Anthropic advises the "simplest solution possible", adding complexity only when needed (https://www.anthropic.com/engineering/building-effective-agents). Claude Code warns when subagent descriptions together exceed 15k tokens and routes on `description` (https://code.claude.com/docs/en/sub-agents). Net headcount change with this plan: +4 new, −1 to 2 repurposed or retired.

## Ownership fixes: no hire needed, do them now

Shrink `_AGENT_KB_UNOWNED_ALLOWLIST` (86 entries) to the genuine commons:
- the 6 family indexes
- `ast`
- `canonical-identifiers`
- `agent-reading-discipline`
- `bypass-rationalization-anti-patterns`
- `drift-fix-on-contact`
- `build-learn-cache-mindset`
- `remediation-markers`
- `storage-hygiene`
- `funnel-self-satisfies-preconditions`
- `minimum-viable-rebuild`
- the root `0x-` docs

Reassign the rest:

| Cluster | Docs | To |
|---|---|---|
| Doc and methodology discipline | `claude-md-router-discipline`, `memory-index-topic-split`, `doc-symbology`, `lossless-doc-refactor`, `eight-way-sync` (already in its description), `keeper-check-before-docing`, `methodology-gc`, `methodology-codification-pipeline`, `repetitive-task-skill-codification`, `versioning`, `live-state-alignment`, `agent-context-architecture` | **compliance-reviewer** (it already verifies eight-way-sync and owns `method-trials`) |
| Knowledge lifecycle | `accept-with-rationale`, `defer-is-not-resolve`, `learn-before-archive`, `persistent-files-absorption`, `proposals-and-improvements`, `roadmap-tracking`, `methodology-execution-discipline`, `product-dev-learning-ground` | **architect** (owns `project-execution`) |
| Dispatch | `branching`, `self-branching-mode`, `dispatch-budget-telemetry`, `dispatch-token-log`, `dispatch-warmup`, `dispatch-with-project-and-notes`, `brief-similarity-radar`, `background-engineer-safety-discipline`, `dont-block-on-background`, `harness-overlay-worktree-divergence`, `surface-and-resume-tooling`, `lenses-applied-trailer` | **architect** (owns `branching-dispatch`, `dispatch-engineer-tuning`) |
| Integration | merge drivers, phased push, orphan sweeper, session-end sweep, claim-vs-evidence | integration-steward (item 5) |
| Seed and organ | `verify-seed-on-fork-base`, `products-consume-canonical-organs`, `seed-organ-canonical-set`, `absorption-tracking`, `absorption-ships-consume-docs` | **architect** |
| LGPD | `lgpd-entry-keeper` | **security** (owns `lgpd.md`) |
| Cache and keeper machinery | listed in item 2 | tooling-engineer; until hired, **devops-engineer** |

**Two more gaps:**
- **Out of keeper scope:** `KB/CONTEXT/PRODUCTS/**` and `ABSORPTIONS/**`, which includes 5 social-wiring and 15 orbity docs.
- **Two telemetry rails are dead:** `dispatch-budget.ndjson` (1 row) and the Lenses trailer (1 use). Revive one before hiring, so each hire's utilization can be measured.
