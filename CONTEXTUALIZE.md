# CONTEXTUALIZE.md — fresh-agent read map (pointer-only)

> **Trigger.** Clean-context agent **AND** user said "contextualize" / "please contextualize" / "I don't know this platform." Read once, follow the pointers, proceed. **Already working / oriented? Skip — re-reading wastes tokens** (re-bloat is keeper-gated by `check_contextualize_alignment`).
>
> Pointer-only map (mirrors CLAUDE.md §1 pattern: rule + one-clause why + `→` pointer). Bodies live at the pointers; nothing inlined here drifts.

---

## 1 · Core read order (each line: what to read → what you'll know after; stop when enough)

- **`CLAUDE.md` §1** → the always-on behavioral contract (auto-loaded; actually read §1, don't skim).
- **`KNOWLEDGE-BASE/AGENT-CONTEXT.md`** → fresh-session orientation + "what is this place" prose.
- **`KB § CONTEXT/02-LANDSCAPE.md`** → products / schemas / ports / stack — *what exists*.
- **`KB § CONTEXT/01-PHILOSOPHY.md`** → engineering principles — *how we think*.
- **`KB § CONTEXT/03-SEED-ARCHITECTURE.md`** → the spine; the single most load-bearing architectural rule.
- **`KB § CONTEXT/04-SHARED-LIBRARY.md`** → reusable components catalog (`noctusai_lib` + `@noctusai/lib`).
- **`KB § CONTEXT/05-INFRASTRUCTURE.md`** → deployment + self-hosted services + the VPS fleet.
- **`KB § CONTEXT/06-AGENTS.md`** → the MCP dev toolkit (130 tools) + Claude-side agents.
- **`KB § INDEX.md`** → the full KB catalog; where depth lives (pull on-demand, never cover-to-cover).
- **`MEMORY.md`** → working-agreement index (auto-loaded; one line each, expand the relevant ones).

## 2 · Universal patterns to recognize before editing anything

- **Agent-context architecture** — `.claude/agents/<name>.md` are lean L1 INDEX over KB depth; frontmatter `owns_kb:` declares full-domain territory. → `KB § PATTERNS/common/agent-context-architecture.md`
- **Drift-fix-on-contact + scoped auto-improvement** — drift = PAUSE → resolve → surface-if-blocked → DOC → continue. Tech-lead RESOLVES; engineers SURFACE in `drift-found:` / `scoped-improvement:` lines (two-leg footer mandatory every dispatch). → `KB § PATTERNS/common/drift-fix-on-contact.md` · `KB § PATTERNS/common/scoped-auto-improvement.md`
- **Cache family — consult-before-editing** — three keeper-mirror caches (keeper-pattern + agent-context + auto-improvement). Query the cache BEFORE editing a gated doc/agent. → `KB § PATTERNS/common/keeper-pattern-cache.md` · `KB § PATTERNS/common/keeper-check-before-docing.md`
- **Self-branching mode** — 🔴 ABSOLUTE: never work on `dev`; every writing task auto-isolates off `origin/dev`. → `KB § PATTERNS/common/self-branching-mode.md` · skill `noc-self-branch`
- **AST-first** — code edits via `libcst` / `ts-morph` / `tree-sitter` — never regex/sed on source. → `KB § PATTERNS/common/ast.md`
- **DRY — the recurrence rule** — N=2 → triage; N=3+ MUST formalize; the 4th instance is forbidden. → `KB § PATTERNS/architect/project-execution.md`
- **Triage at decision time — accept-with-rationale** — every divergence lands on `[F]/[R]/[A]` with paperwork (catalog survives folder deletion). → `KB § PATTERNS/common/accept-with-rationale.md`
- **Methodology codification pipeline** — s1 emergent → s2 memory → s3 KB+CLAUDE.md → s4 keeper detector. → `KB § PATTERNS/common/methodology-codification-pipeline.md`
- **Three-way sync + symbol-first + lossless doc-refactor** — rule changes live in KB↔CLAUDE.md↔memory same commit; symbol glossary gates dense docs; doc-refactor is methodology surgery. → `KB § PATTERNS/common/claude-md-router-discipline.md` · `KB § PATTERNS/common/doc-symbology.md` · `KB § PATTERNS/common/lossless-doc-refactor.md`
- **Persistent-files absorption + storage hygiene** — durable content in `projects/`/`worktrees/` is absorbed to KB/memory BEFORE archive/teardown; salvage-before-delete via `noctus.dev.task_branch action=cleanup`. → `KB § PATTERNS/common/persistent-files-absorption.md` · `KB § PATTERNS/common/storage-hygiene.md`
- **Remediation markers + no silent errors** — `NOC-REMEDIATE[<class>]` for named-destination deferrals; no `except: pass`, no silent fallbacks. → `KB § PATTERNS/common/remediation-markers.md`

## 3 · Domain map (high-traffic patterns by area — first stop when working in that domain)

- **Backend** (FastAPI / Pydantic / RLS / migrations) → `KB § PATTERNS/backend/backend.md` · `database-rls.md` · `pydantic-strict-http.md` · `di-test-seam.md` · `logging.md` · `seed-fake-real-adapter.md`. Specialist agent: `backend-engineer`.
- **Frontend** (React / TanStack Query / vite / seed factories) → `KB § PATTERNS/frontend/frontend.md` · `core-url-routing.md` · `product-internal-wiring.md` · `product-icon-registry.md`. Specialist agent: `frontend-engineer`.
- **DevOps / containers / deploy** → `KB § PATTERNS/devops/containerization.md` · `container-sanitization.md` · `base-image-dep-freshness.md` · `dev-prod-parity.md` · `deploy-config-contract.md` · `KB § GUIDES/production-deploy.md`. Specialist agent: `devops-engineer`.
- **Security / LGPD / webhook signatures** → `KB § PATTERNS/security/webhook-signatures.md` · `lgpd.md` · `llm-bot-security.md`. Specialist agent: `security` (advisor).
- **Compliance / testing / regression baseline** → `KB § PATTERNS/compliance/compliance-regression-baseline.md` · `testing.md`. Specialist agent: `compliance-reviewer` (advisor).
- **Integrations** (Google / Meta / WhatsApp / OAuth / image-gen) → `KB § INTEGRATIONS/*.md`.
- **Branching / dispatch / parallel waves** → `KB § PATTERNS/common/branching.md` · `branching-and-merging.md` (§18/§21 collision-class) · `branching-dispatch.md` · `dispatch-engineer-tuning.md` · `parallelization-first-orchestration.md`. Specialist agent: `architect`.

## 4 · Specialist agents + procedure skills

- **Specialist subagents** (`.claude/agents/`) — advisors `architect` · `security` · `compliance-reviewer` (read-only); executors `backend-engineer` · `frontend-engineer` · `devops-engineer` · `engineer-seed` (worktree + commit-own-branch-only); meta `skill-scout` · `orchestrator-operator`. **Tech-lead = the conversational session** (owns all git/merge/deploy).
- **Procedure skills** (`.claude/skills/`, auto-trigger on phrases) — `noc-contextualize` · `noc-new-product` · `noc-absorb-product` · `noc-ship` · `noc-branch-dispatch` · `noc-self-branch` · `noc-wiring-audit` · `noc-container-debug` · `noc-hygiene` · `skill-creator` (+ `codify`).

## 5 · Conditional reads (only if the task is that)

| Task | First stop |
|---|---|
| Create / scaffold / absorb a product · deploy/ship · branch/dispatch · self-branch · wiring audit · container debug · cleanup | matching `noc-*` skill (auto-triggers) |
| Dispatched as engineer | `.claude/agents/engineer-seed.md` (standing protocol) |
| Starting / closing a project; touching `*-PROJECT.md` | `CLAUDE/projects.md` + `KB § PATTERNS/architect/project-execution.md` |
| Trigger phrases the user might say | `CLAUDE.md` §3 routing table |

## 6 · You're contextualized

Proceed with the user's task. Pull depth on-demand via `CLAUDE.md` §2/§3 + `KB § INDEX.md` — don't pre-read everything; the methodology values lean context.

> *Provenance: clean-context-agent-verified 2026-05-18; re-run the self-test after material changes to the core onboarding docs (memory `feedback_new_session_contextualization`). Conformance enforced by `check_contextualize_alignment` (pre-commit) — pointer-only discipline + canonical-cores covered + line cap.*
