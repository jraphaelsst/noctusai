---
name: noc-contract-first
description: Use BEFORE any connected BE/FE work — triggers "wire the frontend to the backend", "connect this endpoint", "build the API and the UI", "FE consumes the new route", "contract-first", "both sides of the feature". Author the endpoint contract ONCE; both sides build to it. The DEFAULT for product-organ features, not an option.
version: 1.0.0
---

# noc-contract-first — pin the contract, then build both sides to it

🔴 **The drift this kills:** two engineers (or two inline passes) each *guess* the shape — `{data:[...]}` vs `[...]`, `id` vs `name`, envelope vs bare — and the mismatch surfaces as a broken page AFTER both report green. The contract is authored ONCE, verbatim in both briefs, and becomes the acceptance gate for BOTH slices.

## Workflow

0. **UI involved? A mockup is never a prerequisite** (owner 2026-11-11, `KB § PATTERNS/frontend/prototype-on-real-data.md`). If the owner supplied one, its controls and states become the FE contract and its data reads the endpoints; if not, derive them from the brief and build right away.
1. **Author/extract the contract skeleton FIRST** — per endpoint: path+method · request field names+types · response shape (envelope-vs-bare + EXACT field names) · status codes (success + typed errors) · auth posture (dependency, org-scoping). When one side already exists, EXTRACT the contract from it field-by-field — do not assume; extraction is where the drift gets caught. A NEW route added to an EXISTING router counts as "one side exists": the router's sibling routes fix the envelope (`{data: …}` or bare) and the error shape, so extract them before choosing (2026-11-10: a bare-body contract for a router that wraps produced a page reading `undefined`, while both slices were green).
2. **Stateful/action endpoints pin 4 more legs** (shapes alone are NOT sufficient — 2026-06-05 refinement): side-effects + state-after ("after this call, X is already true") · error taxonomy (`status → cause → user-facing message`) · strictness (extra fields ignored vs rejected) · deprecations (name what the change makes vestigial). Discriminator: stateless data-fetch = shapes suffice; stateful/action = all four or the consumer re-derives behavior and drifts.
3. **Embed the contract verbatim in BOTH briefs** — BE builds *to* it, FE consumes *to* it. No rediscovery tax, no divergent assumptions.
4. **Dispatch BE + FE in parallel** (file-disjoint → C1 per the orchestration family). Wall-clock = `max`, not `sum`.
5. **Each side's tests assert against the contract** — never against a private mock of a guessed shape.
6. **Close with ONE E2E-shape check** — a real-endpoint curl or contract test hitting the live route asserting the FE-consumed shape. Mocked-hook tests never catch BE↔FE drift.

## Guardrails
- **The contract has a "Records / Metrics" leg:** what does this feature RECORD (tables as first-class dated rows, the append-only event per lifecycle change, outcome enums) and WHICH METRICS does that enable (each derived in one place)? No metric named ⇒ ask "how will we know it works?" before building. Backstop: keeper `check_measurable_by_design`. → `KB § PATTERNS/architect/measurement-by-design.md`
- ⚠️ Skipping step 1 and "aligning at integration" IS the anti-pattern — integration is where the drift is most expensive.
- Carve-out (justify + log): a trivial single-side change that does not alter the contract (pure BE refactor behind a stable shape; pure CSS/copy tweak).
- Full-stack features extend the same discipline to DB/RLS + persisted client state → `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md § Composes with`.
- **The contract names the access tier of every endpoint** (`platform|org|service|public`) and of every table it adds; Platform IP never ships to a caller below `platform`. → `KB § PATTERNS/security/access-tiers.md`
- **Read the open findings first.** Before touching a product/agent, `noctus.dev.findings_ledger action=open_for_scope scope=<slug>` (briefs carry it too); close what you fix via the tool (`new_status=fixed`, detail=sha), never by hand. → `KB § PATTERNS/common/living-findings-ledgers.md`

## Depth
`KB § PATTERNS/architect/fe-be-contract-first-dispatch.md` (canonical home — skeleton, the 4 stateful legs, worked examples) · `KB § PATTERNS/common/orchestration-family-index.md` (dispatch mechanics) · `KB § PATTERNS/common/dispatch-with-project-and-notes.md` (brief plumbing).

Born from N≥2 recurrence: named the DEFAULT in CLAUDE.md §1 since 2026-06 yet had no skill (2026-07 harness audit, landed 2026-08-03 — repetitive-procedure-→-skill gap).
