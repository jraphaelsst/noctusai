# FE↔BE contract-first dispatch — the shared skeleton for connected BE/FE work

**Principle.** When a product-organ task spans BOTH a backend (endpoints) and a frontend (the UI that consumes them), the tech-lead authors the **FE↔BE contract** — the shared skeleton — *first*, then dispatches the BE and FE slices **against that one contract**. Both sides build to the SAME skeleton, so they fit by construction; contract drift is caught at authoring time (by whoever holds both sides), not discovered at runtime. This is the **default** for connected BE/FE product-organ work.

## Why (the drift it prevents)
Born 2026-06-01, social-wiring multi-account integrations. The multi-account framework had a fully-built backend AND a fully-built frontend, each green on its own unit tests, yet the feature was **0% functional** — because the two sides had been built to **different imagined shapes**:
- FE hooks read `res.data` / `res.providers` (an envelope); the BE returned **bare** lists.
- FE keyed providers on `name`; the BE registry emitted `id`.
- FE manual-fields keyed on `key`; the BE emitted `name`.

Mocked-hook FE tests and shape-agnostic BE tests each passed against their own (drifted) assumption. There was no shared skeleton — so nothing forced the two sides to agree. → see [[framework-consume-wire-and-apply-gap]] (the runtime symptom: route/CRUD-exists ≠ wired).

## The contract skeleton (what to pin, ONCE)
Per endpoint, authored as the single source of truth both engineers reference:
- **path + method** (e.g. `GET /api/integrations/accounts?provider=<id>`)
- **request body** field names + types
- **response shape** — *envelope vs bare* + EXACT field names + types (this is the highest-drift surface — `{data:[...]}` vs `[...]`, `id` vs `name`)
- **status codes** (success + the typed error codes — `401` vs `404`, `503` config-gap, `null`-vs-`[]`)
- **auth posture** (which dependency, org-scoping)

Verify the contract against existing code when a side already exists — **do not assume**; extracting it is exactly where you catch the drift. The pinned contract is the **acceptance gate for BOTH** slices.

## A shapes-only contract is necessary but NOT sufficient (2026-06-05 refinement)
The first *clean-from-the-start* run (social-wiring WAHA connect: BE + FE dispatched against one contract) matched with **zero field/envelope drift** — the shapes contract worked exactly as designed. But three smaller drifts slipped through because the contract pinned only *shapes*. For a **stateful / connected** feature (sessions, webhooks, external services), the contract must ALSO pin:
- **Side-effects + state-after** — what the response leaves ALREADY DONE, not just its shape. *(The slip: the contract didn't say "`create()` already `start_session()`s," so the FE independently fired start on detail-open → a redundant double-start. Idempotent here, but it's avoidable drift.)* Rule: every *"after this call, X is already true"* belongs in the contract.
- **Error taxonomy** — enumerate `status → cause → user-facing message`, not just "show error states." *(Here: `502` = upstream WAHA `set_webhook` failed · `503` = `waha_base_url`/`encryption_key`/`resolve_product_url` unconfigured · `404` = unknown webhook token. The FE handled them generically because the map wasn't pinned.)*
- **Strictness** — are extra/removed request fields IGNORED or REJECTED? *(BE dropped `extra="forbid"` to silently ignore the now-removed `session`/`server`/`webhook` fields — a reasonable but contract-level decision the contract should state.)*
- **Deprecations** — when the contract change makes a prior endpoint/action vestigial (here the FE `configureWebhook` action, now that the webhook is auto-minted server-side), NAME it so the consumer drops it instead of leaving an orphan.

The discriminator: a **stateless data-fetch** endpoint is fully captured by shapes; a **stateful/action** endpoint (mutates external state, triggers a side-effect, gates on config) needs the four above or the consumer re-derives behaviour and drifts.

## The flow (tech-lead view)
1. **Author/extract the contract skeleton** first (from the existing side if present; verify field-by-field). This step IS the drift-catch.
2. **Embed it verbatim in BOTH briefs** — the BE brief builds endpoints *to* it; the FE brief consumes *to* it. No rediscovery tax; no divergent assumptions.
3. **Dispatch BE + FE in parallel** (file-disjoint → C1, per [[parallelization-first-orchestration]] + [[branching-and-merging]] §18). Wall-clock = `max`, not `sum`.
4. **Each side's tests assert against the contract** (not against a private mock of a guessed shape).
5. **Close the loop with ONE E2E-shape check** — a real-endpoint curl or a contract test that hits the live route and asserts the FE-consumed shape. Mocked-hook tests never catch BE↔FE drift. ([[framework-consume-wire-and-apply-gap]])

## Default vs carve-out
- **Default:** any task touching API endpoints + a UI that consumes them (i.e. most product-organ features).
- **Carve-out (justify + log):** a trivial single-side change that does not alter the contract (pure BE refactor behind a stable shape; pure CSS/copy FE tweak).

## Composes with
- [[parallelization-first-orchestration]] — the contract is what makes the parallel BE/FE slices *fit*; this names the shared-skeleton precondition.
- [[dispatch-with-project-and-notes]] — the contract lives in the PROJECT.md §4a routing the tech-lead writes before dispatch.
- [[framework-consume-wire-and-apply-gap]] — the runtime gap this prevents (consume-wire + applied + E2E-shape).
- [[products-consume-canonical-organs]] — when the contract IS a canonical organ's seam, both sides consume the organ rather than re-deriving the shape.
