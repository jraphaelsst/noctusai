# Agent refinement — master-level dev team — Project Document

> Owner request 2026-11-05: make every dev-team specialist a "master-doctor-level"
> specialist — very detailed, quality over speed, reliable online sources cited,
> frameworks / architecture / methodologies / good practices / examples — and hire
> whoever is missing. Integration branch: `feat/agent-refinement` (tech-lead).
> 🔴 dev FROZEN by noctusai-3d's git redesign: commit on own worktree branches only;
> no push/integrate to dev until noctusai-3d sends RESUME.

## 1. Context & Purpose

Seven read-only audits (2026-11-05, `audits/audit-*.md` — every URL fetched/confirmed)
found one pattern across all 13 agents: rich in **house lessons** (incident → keeper),
poor in **the profession's canon** (frameworks, methods, standards); several L1 files
bloated or carrying stale/wrong pointers. The upgrade keeps the house shape
(`KB § PATTERNS/common/agent-context-architecture.md`): the agent `.md` stays a lean
L1 index, depth goes into a per-agent cited **craft canon** KB doc.

## 2. Confirmed constraints (owner decisions, 2026-11-05)

- Order: (1) Claude agents → (2) repo-root `dev_team/` (agno) filled from them →
  (3) team/orchestration research incl. orchestrator↔orchestrator peer comms.
- Hires approved: ai-engineer · product-designer · legal-advisor (incl. LGPD) ·
  tooling-engineer · "bring more if you find value" ⇒ + test-engineer + integrations-engineer.
- skill-scout: upgrade (not retire). accountant: widen to NoctusAI's own finances + SaaS metrics.
- orchestrator-operator: retire together with noctusai-3d's merge queue landing (their call + timing).
- Real code defects found by the audits: fix AFTER the agents (follow-up list §6).
- Merge-flow lines in any agent/KB file: leave verbatim, list them for noctusai-3d.

## 3. Standards every slice follows

### 3a. Craft-canon KB doc
- Path `KNOWLEDGE-BASE/CONTEXT/PATTERNS/<domain>/<name>.md`; added to the agent's
  `owns_kb:` + a `KB § …` body pointer + a `KB § INDEX.md` row, same commit.
- Opens with: what it is · why · **how to use it** (the house mechanism wins over the
  general canon) · a **standard term ↔ house term** map.
- Each section: principle → how it applies HERE (file:line) → checklist → anti-patterns.
- 2–3 **worked examples grounded in this codebase** (file:line), per the audit outline.
- `## Sources`: title — URL — what it supports — accessed date. Only URLs verified
  (the audit's verified list, or fetched by you). Primary/reputable sources first.
- Respect `KB § PATTERNS/common/doc-symbology.md`. Split a doc that passes ~1000 lines.

### 3b. Agent L1 file
- Lean index: every rule = **bold rule** + one-clause why + `→ KB § …`, ≲40 words.
  No repeats of CLAUDE.md §1 or the engineer-seed protocol. Incident narrative moves
  to the owning KB doc **losslessly** (KB § PATTERNS/common/lossless-doc-refactor.md).
- Sections: Mission · Domain rules · Craft canon (frameworks named, one line each →
  pointer) · Workflow/Output shape · Owned KB depth (all owns_kb paths) · Composes-with.
- Frontmatter: owns_kb updated; description gains routing triggers; tools fixed per audit.
- Keepers stay green: `check_agent_kb_alignment`, `check_agent_context_cache_freshness`,
  `kb_sync` (pre-commit).

## 4. Slice plan

### 4a. Dispatch routing

#### 4a.1 Slice → lens table (Wave 1 — the 12 existing agents; 6 parallel slices)

| Slice | Agents | New canon docs (min.) | Files | Lens |
|---|---|---|---|---|
| W1-S1 | architect · engineer-seed | `architect/architecture-craft-canon.md` · `common/engineer-operating-discipline.md` (+ unowned-allowlist row) | their .md + owned architect KB (non-merge-flow) + compliance.py allowlist | architect |
| W1-S2 | security · agents-security | `security/appsec-craft-canon.md` · `security/secure-code-review-checklist.md` · `security/incident-response-playbook.md` · `security/ai-agent-security-canon.md` | their .md + PATTERNS/security/* | security |
| W1-S3 | backend-engineer | `backend/backend-craft-canon.md` | its .md + owned backend KB | backend-engineer |
| W1-S4 | frontend-engineer | `frontend/frontend-craft-canon.md` | its .md + owned frontend KB | frontend-engineer |
| W1-S5 | devops-engineer · ops-steward | `devops/sre-craft-canon.md` · `devops/ops-craft-canon.md` | their .md + owned devops KB (non-merge-flow) | devops-engineer |
| W1-S6 | compliance-reviewer · skill-scout · reverse-engineer · accountant | `compliance/code-review-craft.md` · `common/vendored-skills.md` · `common/reverse-engineering-craft.md` · `finance/br-tax-advisor-canon.md` · `finance/managerial-and-saas-metrics.md` | their .md + owned KB + skill-scout owns_kb pin (compliance.py + its test) | compliance-reviewer |

Wave 2 (after Wave 1 lands on `feat/agent-refinement`): the 6 hires — new agent file +
canon doc + ownership transfers out of the overloaded agents (LLM docs ← backend;
MCP/cache/keeper docs ← architect/devops; integrations ← backend; prototype/a11y ←
frontend; testing harness half ← compliance; contracts/LGPD legal ← security).
Wave 3 (tech-lead inline): roster sync (CLAUDE.md §2 · CONTEXTUALIZE.md §4 · INDEX ·
06-AGENTS · dev-team.md), reassign the `_AGENT_KB_UNOWNED_ALLOWLIST` domain docs,
archetype check reads a frontmatter role (3 agents unchecked today).

#### 4a.2 Codification expectations
s3 = yes for every slice (new KB canon + L1 rules). s4 = no new keepers in Wave 1
(only the allowlist / owns_kb pin edits named above).

#### 4a.3 Routes not taken
- Fat agent files with depth inline — rejected (per-dispatch token cost; house rule).
- Cross-slice ownership transfers in Wave 1 — deferred to Wave 2/3 (collision).
- Fixing the product-code defects inside these slices — owner said after (§6).
- Editing merge-flow lines — noctusai-3d's zone.

#### 4a.4 Notes
Surface mid-flight via `noctus.dev.surface_to_tech_lead`; return the engineer-seed
short form + the merge-flow lines you left untouched + KB defects fixed on contact.

## 5. Shared-file rule
Slices may touch `KB § INDEX.md` only to ADD their rows (C2 additive; tech-lead
resolves count blocks with `kb_sync` at merge). Nobody edits CLAUDE.md, CONTEXTUALIZE.md
or 06-AGENTS.md in Wave 1.

## 6. Follow-up — code defects (after the agents; owner decision)
1. Seed webhook default accepts unsigned requests when the secret is unset
   (`products/seed/backend/app/routers/webhook_router.py:16,69`; igig/erp/commerce inherit) — P0.
2. No backup/DR (RPO/RTO, restore drill); Supabase backups exclude Storage; cache-pg backup "future".
3. No container log rotation in prod compose (verify VPS `daemon.json`).
4. `formatCurrency(null)` renders "R$ 0,00" (`seed/lib/frontend/src/utils.ts:26-31`).
5. TS `strict` off in every product tsconfig (seed scaffold included) — seed-level ratchet.
6. Migrations not zero-downtime safe (no `lock_timeout`; runner wraps each file in one tx).
7. No ANPD incident decision/register for the erp-certidoes public-bucket exposure.
8. LLM rate-limit/anomaly fail-open when Redis is down (`conversation_rate_limit.py:156`).
CI items (SHA-pinning 79 `uses:`, trivy-action, dormant FE lint target) → noctusai-3d, accepted.

## 7. Open questions
- Who owns `PRODUCTS/**` + `ABSORPTIONS/**` (outside the ownership keeper today)? → Wave 3.
