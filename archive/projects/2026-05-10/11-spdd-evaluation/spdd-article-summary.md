# SPDD — Structured-Prompt-Driven Development (article summary)

> Source: https://martinfowler.com/articles/structured-prompt-driven/
> Authors: Wei Zhang & Jessie Jie Xia, Thoughtworks Global IT Services
> Published: 28 April 2026
> Captured here: 2026-05-09

This document is a faithful, exhaustive summary of the article. Treat it as a frozen reference; original article is the authority.

---

## 1 · Methodology name & origin

**Structured-Prompt-Driven Development (SPDD)** — developed inside Thoughtworks' Global IT Services. Article framing is engineering-organizational, not academic.

## 2 · Problem it addresses

When teams adopt LLM-assisted coding, **individual developer speed goes up but system-level throughput drops** — ambiguous requirements scale into code fast, reviews can't keep up, integration/test failures multiply, production-risk reasoning breaks down at scale.

Article verbatim: *"local speed improves. But that doesn't automatically translate into system-level throughput."*

Mission: make AI-generated changes **governable, reviewable, and reusable**. Treat structured prompts as first-class, versioned, governed delivery artifacts that travel alongside code (not disposable chat logs).

## 3 · The two pillars

### 3a · The REASONS Canvas — a fixed 7-part template

| Layer | Letter | Role |
|---|---|---|
| **Intent & Design (abstract)** | **R** Requirements | Problem + Definition of Done |
| | **E** Entities | Domain objects + relationships |
| | **A** Approach | Strategy to meet requirements |
| | **S** Structure | System placement, components, dependencies |
| **Execution (specific)** | **O** Operations | Concrete, testable implementation steps — down to method signatures, parameter types, execution order |
| **Governance (common)** | **N** Norms | Cross-cutting standards (naming, observability, defensive coding) |
| | **S** Safeguards | Non-negotiable boundaries (invariants, performance, security) |

### 3b · Core philosophy

> *"When reality diverges, fix the prompt first — then update the code."*

Prompts are versioned, governed team assets. Two-way sync keeps Canvas and code aligned bidirectionally.

## 4 · The 6-step workflow

| # | Step | Command | Driver | Artifact produced |
|---|---|---|---|---|
| 1 | Create initial requirements | `/spdd-story` (optional) | AI splits, human refines | INVEST user-story `.md` files |
| 2 | Clarify analysis | — (human only) | Human | Internal clarity notes (3 dims: core logic / scope boundaries / DoD) |
| 3 | Generate analysis context | `/spdd-analysis` | AI scans codebase + extracts keywords; human validates | `[Analysis]-…md` (domain concepts, risks, gaps, edge cases) |
| 4 | Generate structured prompt | `/spdd-reasons-canvas` | AI writes Canvas; human reviews | `[Feat]-…md` full REASONS Canvas |
| 5 | Generate code | `/spdd-generate` (+ `/spdd-api-test`) | AI generates, human reviews | Production source + cURL test script |
| 6 | Generate unit tests | (template-driven, not yet finalized) | AI dedupes vs. existing; human reviews | `[Test]-…md` + test files |

### Step-by-step detail

**Step 1 — `/spdd-story`** (optional)
- INVEST principle (1–5 days each), independent + deliverable user stories.
- Acceptance criteria in Given/When/Then format.
- Manual creation acceptable.

**Step 2 — Clarify Analysis** (human-led)
- 3 dimensions: core business logic / explicit IN-vs-OUT scope / acceptance scenarios with concrete numeric examples.
- Align with PO/BA when gaps exist.
- No versioned artifact — just clarity before AI involvement.

**Step 3 — `/spdd-analysis`**
- AI extracts keywords from business requirements, scans only relevant codebase sections (not entire system).
- Identifies existing-vs-new domain concepts, surfaces business rules + technical risks.
- Filename pattern: `GGQPA-001-202603191100-[Analysis]-multi-plan-billing-model-aware-pricing.md`.

**Step 4 — `/spdd-reasons-canvas`**
- AI reads analysis context + existing codebase, generates all 7 REASONS dimensions.
- Operations down to method signatures, parameter types, execution steps.
- Encodes Norms + Safeguards.
- **Critical:** if modifications needed, never hand-edit the Canvas file. Use `/spdd-prompt-update` — AI updates only affected sections, preserves untouched content.
- Filename: `GGQPA-001-202603191105-[Feat]-multi-plan-billing-model-aware-pricing.md`.

**Step 5 — `/spdd-generate` + `/spdd-api-test`**
- AI generates code task-by-task following Operations order; strictly adheres to Norms + Safeguards; no feature improvisation.
- Quality philosophy: *"Don't worry about making mistakes... plenty of opportunities to course-correct. Minor code smells are fine for now — verify core functionality first."*
- `/spdd-api-test` produces shell script (e.g. `scripts/test-api.sh`) with cURL covering normal + boundary + error cases. Run before deep code review.
- Code review categorizes findings into two paths:
  - **Logic correction** (observable behavior change) → `/spdd-prompt-update` first → `/spdd-generate` to regenerate code.
  - **Refactoring** (no behavior change) → refactor code directly → `/spdd-sync` to push the change back into the Canvas.
- After all optimizations, re-run API tests as regression check.

**Step 6 — Unit tests** (template-driven; SPDD testing workflow not yet fully finalized per article)
- AI generates initial test prompt combining implementation details with template.
- Cross-references existing tests, removes duplicates, keeps only genuinely new scenarios.
- AI generates unit test code from refined test prompt.
- Filename: `GGQPA-001-202603191105-[Test]-multi-plan-billing.md`.

### Two drift paths summarized

| Trigger | Strategy | Command |
|---|---|---|
| Logic / behavior change | **Prompt first**, then regenerate code | `/spdd-prompt-update` → `/spdd-generate` |
| Refactor / code-smell / no-behavior change | Code first, then sync back to Canvas | refactor inline → `/spdd-sync` |

**Golden rule:** *"Always keep the structured prompt synchronized with your latest codebase."*

## 5 · Tooling — `openspdd` CLI

| Command | Type | Purpose |
|---|---|---|
| `/spdd-story` | Optional | Break large requirements into INVEST stories |
| `/spdd-analysis` | Core | Extract domain keywords, scan codebase, strategic analysis |
| `/spdd-reasons-canvas` | Core | Generate full REASONS Canvas blueprint |
| `/spdd-generate` | Core | Read Canvas, generate code task-by-task |
| `/spdd-api-test` | Optional | Generate cURL test scripts (normal/boundary/error) |
| `/spdd-prompt-update` | Core | Incrementally update Canvas when requirements change |
| `/spdd-sync` | Core | Synchronize code-side changes back into Canvas |

Each command encodes a "thinking strategy" pulling output toward consistent structure.

## 6 · Three meta-skills required

1. **Abstraction first** — design before generating; clarify domain objects, collaboration patterns, boundaries before code generation. Prevents AI from "sprinting on implementation details while the structure falls apart."
2. **Alignment** — lock intent (what we will/won't do) with agreed standards + constraints upfront. Avoids "fast output and slow rework."
3. **Iterative review** — turn output into a controlled loop. Prevents drift through repeated patches or repeated restarts losing cost/time control.

## 7 · Relationship to established practices

### vs Spec-Driven Development (SDD)

Same starting point: spec before code generation. SPDD adds:
- Fixed 7-part Canvas (not free-form spec).
- Operations decomposing strategy down to method signatures.
- Maintained, versioned prompt artifacts traveling with code.
- Two-way sync keeping spec and code synchronized.
- Intent flowing both requirements → code AND code → spec.

Birgitta Böckeler categorizes this as **"spec-anchored"** approach.

### vs Test-Driven Development (TDD)

Key difference: **test placement**. SPDD runs API tests **before** deep code review (validating behavior), then unit tests **last** (regression safety). TDD typically uses tests to clarify behavior upfront.

Rationale: intent is already explicit in the REASONS Canvas, so tests serve different purposes at different stages:
- API tests: validate system behavior early.
- Code review: focus on logic, architecture, non-functional concerns.
- Unit tests: regression protection once implementation stabilized.

Quoted: *"Tests are not less important in SPDD. The change is that intent is made explicit earlier."*

## 8 · Where SPDD fits — fitness assessment

| ★ | Context |
|---|---|
| ★★★★★ | Scaled, standardized delivery — high-repeat business logic needing long-term maintainability |
| ★★★★★ | High compliance + hard constraints — financial systems, multi-channel deployments, regulated environments |
| ★★★★ | Team collaboration + auditability — multi-person delivery requiring full traceability |
| ★★★★ | Cross-cutting consistency work — complex refactors across microservices or languages |
| ★★★ | Hotfixes (rated low — speed > governance) |
| ★★ | Exploratory spikes — idea validation; governance overhead unjustified |
| ★★ | One-off scripts — disposable data cleanup; upfront cost too high |
| ★ | Context black holes — domains with unclear business rules and weak boundaries |
| ★ | Pure creative/visual work — UI visual exploration, marketing copy driven by aesthetics |

## 9 · Trade-offs & investment required

### Upfront investment
- **Mindset shift** (high) — design-first culture, not code-first.
- **Senior expertise required** (medium-high) — engineers must translate business rules into clean abstractions.
- **Tooling** (medium) — without infrastructure, SPDD hits a throughput ceiling; `openspdd` provides CLI automation.

### Returns
- **Determinism** (high, immediate) — precise specs reduce hallucination + creative interpretation.
- **Traceability** (high, immediate) — every change traces back to structured prompt.
- **Faster reviews** (high, short-term) — code arrives closer to team standards.
- **Explainability** (medium-high, gradual) — intent visible at natural-language level.
- **Safer evolution** (high, long-term) — well-defined boundaries enable lower-risk targeted changes.

## 10 · Anti-patterns

1. **Hand-editing the Canvas file** — always go through `/spdd-prompt-update` or `/spdd-sync`.
2. **Skipping the analysis phase** — straight to code generation without strategic clarity → misaligned implementation.
3. **Trying to perfect code on first generation** — verify functional behavior first, polish later.
4. **Confusing logic corrections with refactoring** — different paths! Logic → prompt-first; refactor → code-first.
5. **Applying SPDD to ill-defined domains** — "context black hole" success rate drops sharply.
6. **Compressing intent confirmation into one mega-review** — distribute across the 6 steps to manage cognitive load.
7. **Assuming model-agnosticism** — stronger models materially improve output (article notes Claude Opus > GPT Codex > Gemini in their experience). Switching models between iterations carries managed risk of intent drift.

## 11 · Concrete example used throughout the article

**Scenario:** Billing engine enhancement — moving from static pricing to model-aware subscription billing.

**Scope:**
- API enhancement: add required `modelId` parameter to `POST /api/usage`.
- Two plan types: Standard (global quota + model-aware overage) and Premium (no quota, split prompt/completion billing).
- Routing mechanism (Strategy/Factory pattern) for extensible calculation formulas.

**Numeric examples:**
- Standard plan: 100K quota, 90K used, 30K new tokens at "fast-model" $0.01/1K = $0.20 charge (10K from quota, 20K overage).
- Premium plan: 10K prompt + 20K completion for "reasoning-model" at $0.03/$0.06 = $1.50 total.

**Artifacts generated:**
- 2 initial user stories (consolidated into 1).
- Analysis context document.
- REASONS Canvas structured prompt.
- Production Java code (3-tier architecture).
- API test script (cURL-based).
- Unit test code.

**Reference repo:** `gszhangwei/token-billing` (iteration commits show before/after diffs).

**Outcome claim:** ~99% intent alignment, complete engineering transparency, Canvas tightly synchronized with codebase, foundation for future iterations.

## 12 · Caveats & limitations

- **Senior-architect skew today.** Article quote: *"With today's trade-offs, SPDD can look like a method reserved for senior architects."* Roadmap aims to lower the barrier.
- **Local-offline LLMs not strong enough** for analysis/canvas generation; not recommended.
- **Onboarding legacy code** without prior SPDD context requires a synthesis step.
- **ROI compounds across projects** (decision memory accumulates); first project sees less of it.
- **Tooling is needed to scale**; without `openspdd` or equivalent automation, SPDD hits a throughput ceiling.
- **Raw non-determinism still exists** even with governed prompts; SPDD treats it within "controllable bounds," does not eliminate it.

## 13 · Article section list (in order)

1. Opening — local speed vs. system throughput problem
2. SPDD definition + two core components (Canvas + workflow)
3. Prompts as first-class artifacts
4. REASONS Canvas structure (7-part template + diagram)
5. SPDD workflow (6 steps + sync loops)
6. Concrete example: billing engine enhancement (Steps 1–6 walkthrough + summary of deliverables)
7. Three core skills (abstraction-first / alignment / iterative review — linked subsidiary articles)
8. Where SPDD fits (fitness assessment + trade-offs table)
9. Roadmap + closing
10. Acknowledgements
11. Q&A (13 detailed questions on scaling, models, expertise, drift, etc.)

---

**One-line takeaway:** SPDD is *spec-anchored*, codegen-focused, single-prompt-per-feature, two-way synced — built for governance + traceability at organizational scale, biased toward senior engineers and well-defined business domains.
