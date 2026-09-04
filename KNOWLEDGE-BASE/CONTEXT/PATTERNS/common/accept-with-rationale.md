# Accept-with-Rationale — pattern + active decisions register

> **Why this doc exists.** Projects close and their folders get deleted
> (`apply-inline-then-delete`). Without a durable home, the **why** behind
> every legitimate divergence from platform ideals leaks out of the
> codebase the moment the project ships. Future agents then re-propose
> the same consolidation, re-discover the same constraints, and re-do
> the same triage.
>
> **This doc is the durable home.** Two purposes:
>
> 1. **Define the pattern** — when accept-with-rationale is the right
>    triage outcome (vs. formalize / refactor), and what paperwork
>    keeps it from going silent.
> 2. **Catalog every active decision** — every legitimate
>    divergence on the platform, with the reason, the scope, and the
>    revisit trigger.
>
> When you encounter the third firing of the recurrence rule and start
> writing "it'd be nice to consolidate X" — **first check this catalog**.
> If X is already an active accept-with-rationale, the consolidation
> case has already been triaged. Either the trigger to revisit hasn't
> fired yet (don't re-open) or you've found new evidence that shifts
> the decision (in which case: update the entry).

---

## The pattern

The triage rule lives in `KB § 01-PHILOSOPHY.md § Triage at decision time`
and the recurrence threshold lives in
`KB § PATTERNS/architect/project-execution.md § 2.7 The recurrence rule`. Both
demand that every divergence from ideals lands on **one of three
explicit outcomes**:

- **Formalize** — extend framework / seed / shared library so the
  divergence becomes the new ideal.
- **Refactor** — align with the existing contract; the divergence was
  a slip.
- **Accept-with-rationale** — the divergence is legitimate but
  project- or product-unique; formalizing would bloat the framework,
  refactoring would destroy something the product actually needs.
  Document **why**, name the **revisit trigger**, and move on.

"Accept" without paperwork is silent debt. Paperwork makes the
decision auditable, recoverable, and revisitable. **Recurrence flips
prior accepts** — if a fourth instance of the same divergence shows
up, the accept becomes a formalize.

### When to add a catalog entry

Always, when:

- You consciously decide "this divergence is legitimate; we won't
  formalize or refactor it."
- A closing project §11 contains an accept-with-rationale decision —
  promote it here BEFORE the folder is deleted.
- A product MASTER-PROMPT.md or backend conftest carries a rationale
  comment that's load-bearing platform-wide.

Do NOT add an entry when:

- The divergence is genuinely transient (a follow-up project is
  already filed and runs to closure within weeks). That's a
  **deferred-formalize**, not an accept.
- The divergence is a typo / oversight you're about to fix. That's a
  **refactor**, not an accept.

### Entry format

Each entry under § Active decisions follows this shape:

```
### <short-title>
- **Subject:** what concrete code/contract/decision is being
  documented.
- **Decision:** the diverging shape, in one sentence.
- **Reason:** why formalize and refactor were the wrong outcomes.
- **Scope:** which products / files / surfaces this covers.
- **Revisit trigger:** the concrete signal that flips this from
  accept toward formalize. Often "another product needs the same
  divergence" or "the framework gains the missing seam."
- **Recorded by:** project / commit / agent that surfaced the
  decision.
```

When the revisit trigger fires, **don't delete the entry** — flip it
to "**FORMALIZED** in <project>" or "**REFACTORED** in <commit>" and
keep it as historical context. The catalog is append-only-ish; the
shape just changes when the decision moves.

---

## Active decisions

### permutas compliance findings baselined pre-migration (110 fingerprints)

- **Subject:** `products/permutas/**` — the legacy Permutas platform absorbed
  2026-09-04 (`05ce788e`). `check_all_products()` reports 110 NEW high/critical
  findings for it against `mcp/noctusai/tests/compliance_baseline.json`,
  dropping the platform's informational score from ~90 to 63.
- **Decision:** baseline all 110 rather than fix them or revert the
  absorption. The baseline grows, cited per its own README rule ("a NEW
  pre-existing class is triaged-and-accepted ... a refresh that GROWS the
  baseline must cite the triage decision in the commit msg").
- **Reason:** all 110 are ONE fact wearing four costumes — permutas is a
  create-react-app + Django REST Framework platform that consumes neither
  `@noctusai/seed` nor `@noctusai/lib`, and the detectors assume every product
  does:
    * 2 × `Missing -e seed/framework/backend` / `-e seed/lib/backend` — it has
      no seed dependency to declare.
    * ~85 × "FE calls `X` but no backend route matches" — the wiring detector
      reads FastAPI decorators. DRF registers routes at runtime through
      `DefaultRouter`, so it sees zero backend routes and reports every single
      frontend call as dangling. These are detector false positives, not
      broken wiring.
    * ~20 × "'permutas' backend requires `<django-dep>` but it is MISSING from
      the root requirements.txt" — the root file pins the FastAPI fleet's
      shared deps; Django/Celery belong to permutas alone.
    * 4 × "local declaration of canonical organ" (`AppShell`, `TableSkeleton`,
      `KanbanBoard`, `Header`) — it cannot import organs it has no dependency
      on.
  Fixing them individually would mean either porting permutas onto the seed
  framework (a project, not a fix) or teaching four detectors about Django (a
  fleet change for one product). Reverting was the alternative considered and
  declined by the user — permutas is deployed nowhere (no VPS container, not
  on `prod`), so leaving it on `dev` is operationally free.
- **Scope:** `products/permutas/**` only. No other product's fingerprints
  change; the refresh was verified to grow by exactly these 110 and shrink by
  none.
- **Revisit trigger:** permutas' frontend/backend actually adopts the seed
  (`@noctusai/seed` in its `package.json`, `-e seed/*/backend` in its
  requirements) — at which point these findings become REAL and the baseline
  must shrink back. Also fires if a SECOND Django product is absorbed: N=2
  means the detectors should learn DRF rather than the exception being
  re-baselined.
- **Recorded by:** tech-lead, session_01PVCjij6WdjEbwSdvXWRzGS, 2026-09-04 —
  triaged and accepted by the user after the absorption reddened four fleet
  gates and blocked bless for four unrelated green slices.

### ERP `contratos.parcelas` mixed nested/flat path shape (Pattern G)
- **Subject:** `products/erp-imobiliario/backend/app/routers/contratos.py` exposes the parcela sub-entity through TWO path shapes — **nested** for collection-scoped operations (`GET /api/contratos/{contrato_id}/parcelas` at line 257, `POST /api/contratos/{contrato_id}/parcelas` at line 273) and **flat-by-id** for the single-row update (`PATCH /api/contratos/parcelas/{parcela_id}` at line 310). The frontend (`useContratos.ts:172`) calls the flat shape correctly.
- **Decision:** keep the mixed shape; do NOT normalize to consistently-nested (`PATCH /api/contratos/{contrato_id}/parcelas/{parcela_id}`).
- **Reason:** parcela IDs are globally unique within the contract scope (a parcela belongs to exactly one contract via FK, and the PK is a UUID — not a contract-scoped sequence number). The contrato_id in a hypothetical nested-PATCH URL would be **redundant** with the parcela_id (the server lookup-by-parcela-id-alone hits exactly one row). The flat shape correctly reflects that the parcela is identifiable on its own at update time; the nested shape on collection-listing reflects that "list parcelas FOR contract X" is the natural traversal. Different shapes for different operations, both correctly chosen. Pattern G in the §5.4.2 systemic findings; surfaced low-severity by Phase 0 audit.
- **Scope:** `products/erp-imobiliario/backend/app/routers/contratos.py` — the 3 endpoints (`GET/POST /{contrato_id}/parcelas`, `PATCH /parcelas/{parcela_id}`). FE `products/erp-imobiliario/frontend/src/hooks/useContratos.ts:172` consumes the flat PATCH.
- **Revisit trigger:** (a) a second product surfaces the same sub-entity-id-globally-unique mixed shape (N=2 fires → triage at platform level whether to add a `KB § PATTERNS/backend/backend.md § Mixed nested/flat sub-entity paths` documented convention), OR (b) parcela IDs become contract-scoped sequences (e.g. parcela #1 of contract A and parcela #1 of contract B share the integer 1) — then the nested PATCH becomes structurally required and the flat shape must be deprecated.
- **Recorded by:** ERP wiring Phase 4 (Engineer ERP-P4, 2026-05-20) — design-batch Pattern G `contratos/parcelas` triage resolved per §5.4.2 default recommendation.

### ERP `Configuracoes.tsx` reaches into core `/api/settings/org` (cross-product)
- **Subject:** `products/erp-imobiliario/frontend/src/pages/Configuracoes.tsx` reaches `${VITE_CORE_API_URL}/api/settings/org{,/{key}}` from ERP into core (5 callsites: GET list, PUT upsert, DELETE per-key, DELETE in row, and a single DELETE clearer). ERP is supabase-auth; core is custom-JWT — the call bridges by passing the supabase session's `access_token` as the Bearer.
- **Decision:** keep the cross-product reach; refactor only the HTTP shape — from raw `fetch()` to `createApiClient({ getBaseUrl, getAuthToken })` (the same seed factory ERP's own `api` uses). No new cross-product helper in `noctusai_lib`.
- **Reason:** **N=1** cross-product reach across the entire codebase (verified `grep -rE "VITE_CORE_API_URL|CORE_API_URL" products/`). Extracting a shared cross-product API helper (`createCoreClient(supabase)`) at N=1 is premature formalization — the recurrence-rule threshold is N=2. Refactoring to `createApiClient` already aligns the shape with the seed pattern; the only divergence left is *which base URL it points at*. Going to a fresh helper would add indirection without amortization (the contrasting bridge — supabase-session-token → core's JWT-expecting endpoint — is a 4-line `getAuthToken` callback). The cross-product reach itself is legitimate: ERP edits *org-level credentials* (OpenAI / InfoSimples keys) that live in `core.org_settings` (the single source of truth across the platform) — ERP is the editor surface; core is the authoritative store.
- **Scope:** `products/erp-imobiliario/frontend/src/pages/Configuracoes.tsx` lines ~10-50 (`coreClient` factory + `coreApi(method, path, body?)` wrapper). 5 callsites within the page.
- **Revisit trigger:** (a) a second product page makes a cross-product fetch using the supabase-session-token → core-backend bridge shape (N=2 fires → extract `seed/lib/frontend/src/createCrossProductClient.ts(supabase, baseUrl)` helper consumed by both sites), OR (b) the `coreApi` wrapper grows beyond URL routing + the existing network-down UX (e.g. retry logic, response caching) — at that point the wrapper IS the helper and the formalize-vs-accept rebalances.
- **Recorded by:** ERP wiring Phase 4 (Engineer ERP-P4, 2026-05-20) — design-batch Pattern D `pages/Configuracoes.tsx` row resolved.

### `mcp/{meta,google}` per-connector seed-pin copies — `[A]`→`[F]` RESOLVED (dedup landed, copies removed)
- **Status:** `[F]` — formalized ∧ consumed. Dedup landed on branch `seed-pin-dedup`; the per-connector hand-rolled copies are **removed**, all three sites now compose `from _kit.seed_pin import pin_in_tree_seed`.
- **Subject (historical):** the stale cross-worktree editable-finder eviction logic was formalized in `mcp/_kit/seed_pin.py` (`pin_in_tree_seed`, also called by `_kit.bootstrap.prepare_sys_path`; N=2 — META-2 + GOOG-2 hand-rolled it). The pre-formalization per-connector copies — `mcp/google/conftest.py::_pin_in_tree_noctusai_lib`, `mcp/google/server.py` inline meta_path loop, `mcp/meta/tests/test_smoke.py` inline `_is_noctus_editable_finder` — were initially **retained** under the prior `[A]` because removal was proposed at a project wrap-up under a known-unstable harness window (risk/reward then negative).
- **Resolution (triage rule: recurrence flips `[A]`→`[F]`):** the named-destination condition in the prior entry — "a `conftest`-delegates-to-`from _kit.seed_pin import pin_in_tree_seed` swap is safe ONLY with a green-suite re-verify per connector, in a healthy-harness session, as a pure dedup" — was met. Swap applied to all 3 sites (`mcp/google/conftest.py`, `mcp/google/server.py`, `mcp/meta/tests/test_smoke.py`); zero behaviour change (the helper is intent-equivalent + idempotent); `mcp/google/README.md` prose updated. Re-verify: `_kit` ∧ `meta` suites green (47 passed). `google/tests/` collection is pre-existingly red on the clean base (`ModuleNotFoundError: google.api_core` — `mcp/google/` shadows the site-packages `google.*` namespace package; unrelated to seed-pin, out-of-scope, surfaced to `gmail-seed-lift`); byte-identical before ∧ after this change ⇒ no regression.

### Cloudflare connector keeps its bespoke `request_envelope` transport (not `_kit.transport`)
- **Subject:** `mcp/cloudflare/api.py` (`request_envelope` / `request_json`) hand-rolls the same stdlib-`urllib` transport (params / headers / browser-UA / `urlopen` / `URLError` / `TimeoutError` / non-JSON) that the other four connectors now delegate to the shared `_kit.transport.request_json` seam (kit-connector-boilerplate-consolidation — n8n + waha + hostinger + supabase consume the seam).
- **Decision:** cloudflare does **not** consume `_kit.transport`; it retains its own transport. The other four connectors consume the seam (the N=4 generic-boilerplate recurrence is killed there; cloudflare is the documented single exception, N=1).
- **Reason:** cloudflare's error contract is *richer* than the seam's `error_cls(message, *, status=...)` interface. On an HTTP-error response cloudflare extracts the Cloudflare `errors[0].code` and attaches it as a typed `CloudflareApiError.cf_code` attribute (consumed by the host LLM + `connection_status`); the shared seam owns the try/except and raises `error_cls(message, status=code)` — it has **no channel to carry `cf_code`**. Folding cloudflare in would either (a) regress `cf_code`-on-HTTPError (violates the project's "keep behavior identical" mandate) or (b) add a vendor-error-body hook on the seam used by exactly ONE connector (premature formalization — N=1). Cloudflare's `success:false`-envelope handling (200-transport, business error) is also CF-specific. Folding the *success-path* alone would split cloudflare's transport across two layers for no net duplication win.
- **Scope:** `mcp/cloudflare/api.py` (`request_envelope`, `request_json`, `_first_cf_error`). `mcp/cloudflare/tests/test_smoke.py` accordingly keeps patching `cloudflare.api.urllib.request.urlopen` (NOT `_kit.transport.urlopen` like hostinger/supabase do).
- **Revisit trigger:** a SECOND connector needs to attach a vendor-specific structured error code from the HTTP-error body (N=2) → formalize a `_kit.transport` error-body hook (e.g. an `error_body_parser` callback + an `error_cls` that accepts the parsed code) and fold cloudflare in. Until then the duplicated generic transport in cloudflare is the accepted cost of its richer error contract.
- **Recorded by:** `kit-connector-boilerplate-consolidation` Wave 2 extend-wave (2026-05-25, branch `feat/kit-connector-extend-wave`).

### PF `Equipe.tsx` direct-fetch retained (no `useTeam` hook extraction)
- **Subject:** `products/personal-finance/frontend/src/pages/Equipe.tsx` makes 5 direct `api.get/post/delete` calls to the seed `team` standard router instead of going through a `useTeam` hook layer (Pattern D in the PF wiring §5.2.2 systemic-findings classification).
- **Decision:** Equipe.tsx keeps the 5 direct-fetch callsites; no `hooks/useTeam.ts` is created.
- **Reason:** One-off admin page; the 5 callsites are tight to this single component (member list + invitations list + invite + remove + cancel). A hook layer would add indirection without amortization. Other PF data surfaces have multiple consumers (Dashboard + Transacoes + Carteira all reading transacoes, for example) which is when the hook layer pays off. Equipe has exactly one consumer of each of its 5 endpoints.
- **Scope:** `products/personal-finance/frontend/src/pages/Equipe.tsx` — the 5 callsites against `/api/team`, `/api/team/invitations`, `/api/team/invite`, `/api/team/{id}`, `/api/team/invitations/{id}`.
- **Revisit trigger:** (a) a second product page consumes any of these endpoints (N=2 fires → extract `useTeam` hook in `seed/lib/frontend/src/hooks/useTeam.ts` for cross-product reuse, since `team` is a seed standard router), OR (b) Equipe grows beyond 5 callsites (e.g. role-edit-in-place, bulk-invite, member-detail expansion).
- **Recorded by:** PF wiring Phase 6 engineer (worktree-agent-a0ae8b7bce8e0cd0f, 2026-05-11) — design-batch question Q-equipe resolved.

### ERP metas digest does NOT use `noctusai_lib.domain.digest`
- **Subject:** `KB § 04-SHARED-LIBRARY.md § domain/digest` shared library used by `core` audit-digest, `personal-finance` monthly narrative, `daily-life` weekly review, `social-wiring` email-marketing campaign debrief (absorbed from the retired `mailing` product 2026-05-16) — but NOT ERP metas digest.
- **Decision:** ERP metas digest keeps its own `metas_digest_service.py` shape; does not consume the seed-lib `domain/digest` contract.
- **Reason:** ERP metas digest has no LLM narrative path and preserves a bespoke return shape (3-tier VGV cascade + per-team breakdown). Forcing it through the seed-lib contract would either bloat the contract or destroy the bespoke shape the gamification UI consumes.
- **Scope:** `products/erp-imobiliario/backend/app/services/metas_digest_service.py` + `routers/metas_digest.py`.
- **Revisit trigger:** if a second product needs a non-LLM digest with a similar bespoke shape (N=2 → triage → likely formalize a no-LLM variant of `domain/digest`).
- **Recorded by:** closed project (`projects/erp-metas/`) — context promoted here on 2026-05-02.

### Core bypasses framework auth dependency factories
- **Subject:** `noctusai_seed.create_product_app(...)` ProductDependencies contract assumes Supabase Auth; core's `app/dependencies.py` + `app/database.py` use custom JWT + refresh-token auth instead.
- **Decision:** core defines its own dependencies module, bypassing the framework's standard auth wiring.
- **Reason:** core is the **identity-source** product (not Supabase-consumer). The framework's ProductDependencies contract is built for products that delegate auth to Supabase; core IS the identity authority. Formalizing would require a `customDependencies` seam in seed (worth doing only when a second identity-source product appears).
- **Scope:** `products/core/backend/app/dependencies.py` + `products/core/backend/app/database.py`.
- **Revisit trigger:** a second identity-source product surfaces the same divergence → strong signal to formalize `customDependencies` slot.
- **Recorded by:** `seed-inheritance-hardening` Phase 2 (closed); `KB § 01-PHILOSOPHY.md:200`.

### `outline_typescript` uses regex, not the TypeScript Compiler API
- **Subject:** `mcp/noctusai/tools/outline_typescript.py` parser backend.
- **Decision:** regex-based outline (~5ms/call, ~95% precision on prettier/eslint-formatted TS) instead of the official `typescript` npm package via Compiler API + child-process bridge.
- **Reason:** Phase-4 audit (2026-05-02) found Compiler API costs ~50MB on disk + ~200ms spawn per call for ~15% precision on edge cases (overloaded types, conditional types, nested template strings) the narrow-read use case doesn't need. Regex hits ~95% at zero install cost. The `OutlineResult` shape is identical across both backends so caller code stays parser-agnostic.
- **Scope:** `mcp/noctusai/tools/outline_typescript.py` + `tests/test_outline_typescript_corpus.py`.
- **Revisit trigger:** a downstream use case (e.g. AI-training feature extraction in `projects/project-history-ledger/`) needs higher precision than ~95% → swap the parser implementation behind the same `OutlineResult` contract; caller code doesn't change.
- **Recorded by:** `methodology-extraction` Phase 4 (closed); also documented at `06-AGENTS.md:108`.

### `outline_python` first-level only — no nested functions / closures
- **Subject:** `mcp/noctusai/tools/outline_python.py` symbol enumeration depth.
- **Decision:** module-level + first-level methods only; nested `def` / nested `class` deliberately not surfaced.
- **Reason:** rare in production code; including them adds noise that defeats the narrow-read planning purpose. Anti-pattern guard documented in the module docstring.
- **Scope:** `mcp/noctusai/tools/outline_python.py:35-36`.
- **Revisit trigger:** a real use case where the agent needs nested-function discovery (nested-class is rarer) — surface it as a project, evaluate "add a `depth=2` flag" vs. accept-and-document.
- **Recorded by:** `methodology-extraction` Phase 3 (closed); inline docstring.

### `outline_python` constants restricted to `UPPER_SNAKE_CASE`
- **Subject:** `outline_python.py` constant capture criterion.
- **Decision:** module-level `Assign` nodes whose target is a single Name in `UPPER_SNAKE_CASE` are kind=`constant`; everything else (type aliases like `X = SomeType`, mixed-case module data) is ignored.
- **Reason:** Python convention is UPPER_SNAKE_CASE for constants; type aliases are rare at module level and outside narrow-read scope; mixed-case data is ambiguous.
- **Scope:** `mcp/noctusai/tools/outline_python.py:143-152`.
- **Revisit trigger:** a use case requires type-alias enumeration (e.g. cross-product type-export auditing) → consider a `kind=type_alias` extension.
- **Recorded by:** `methodology-extraction` Phase 3 (closed); inline implementation.

### `outline_typescript` corpus test excludes Playwright e2e specs
- **Subject:** `mcp/noctusai/tests/test_outline_typescript_corpus.py` corpus filter.
- **Decision:** corpus walks `products/*/frontend/src/` only; `e2e/` is in `SKIP_DIRS`.
- **Reason:** Playwright specs use `test(...)` / `describe(...)` callback shapes that the regex backend deliberately doesn't surface. They're not the narrow-read calibration target; including them would force the corpus test to fail on a legitimate non-target.
- **Scope:** `mcp/noctusai/tests/test_outline_typescript_corpus.py:50` (`SKIP_DIRS`).
- **Revisit trigger:** a separate spec-outline use case → build a sibling tool (`outline_playwright`?) rather than overload `outline_typescript`.
- **Recorded by:** `mcp-ast-tools-hardening` Phase 2 (closed) — calibration finding.

### MCP detectors keep raw `import ast` (NOT migrated to `outline_python`)
- **Subject:** `mcp/noctusai/tools/{catalog,compliance,recurrence}.py` parser usage.
- **Decision:** all three detector modules retain `import ast` and node-level walks; do NOT migrate to `noctus.dev.outline_python`.
- **Reason:** detectors examine AST below the symbol-tree level outline_python exposes — they need `Call.keywords`, `Try.handlers`, `AnnAssign.annotation`, `ast.unparse(...)`, and similar node-level surfaces that `outline_python` deliberately omits ("the whole point is to leave them out" — `outline_python.py:32`). The recurrence rule fires at the `import ast` line (N=3 modules), but the actual usage shapes diverge — outline_python is for narrow-read planning, detectors are for node-level introspection. Different concerns; consolidating just the imports doesn't pay off.
- **Scope:** `mcp/noctusai/tools/catalog.py:35`, `compliance.py:6`, `recurrence.py:771`. Each carries an inline comment pointing here.
- **Revisit trigger:** if `outline_python`'s contract grows to expose node-level surfaces (e.g. via a new `OutlineResult.calls` or `.tries` field) — at that point evaluate per-detector migration. As of 2026-05-02 the contract is intentionally narrow.
- **Recorded by:** `ast-callers-consolidation` (Phase 0 audit, 2026-05-02; project closed without a refactor — accept-with-rationale was the outcome).

### `MockSupabaseClient(validate_schema=False)` per-product opt-outs
- **Subject:** test mock schema validation gate, default-on since 2026-04-24.
- **Decision:** ERP (8 drifts) and therapy-platform (~20 drifts) keep `validate_schema=False` in their `tests/conftest.py`.
- **Reason:** legitimate schema drift documented in active reconciliation projects; flipping prematurely would cascade test failures while drift remains. Each opt-out has a rationale comment per the keeper detector `check_mock_schema_validation`.
- **Scope:** `products/erp-imobiliario/backend/tests/conftest.py:96,108`; `products/therapy-platform/backend/tests/conftest.py:70`.
- **Revisit trigger:** the per-product reconciliation projects close (`erp-imobiliario/projects/erp-schema-drift-reconciliation/`, `therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`). Flip to `True` is the close gate.
- **Recorded by:** `KB § PATTERNS/compliance/testing.md § Schema validation`; per-product conftest comments; reconciliation projects.

### `check_no_self_monkeypatch` severity stays `warning` (not `high`) until count = 0 per product
- **Subject:** keeper detector `check_no_self_monkeypatch` severity calibration.
- **Decision:** severity is `warning` (not `high`) until each product's count reaches zero; ratchets to `high` per-product as cleanups land.
- **Reason:** first run flagged 420 sites across 7 products; tanking the score from 100 → 0 was unhelpful. Per-product ratchet preserves CI signal while letting cleanups happen incrementally.
- **Scope:** `mcp/noctusai/tools/compliance.py::_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS`.
- **Revisit trigger:** a product reaches 0 → flip to `high` for that product (already done for `therapy-platform`). All products at 0 → flip repo-wide; remove the carve-out.
- **Recorded by:** `KB § PATTERNS/compliance/testing.md § Severity ratchet`.

### `# self-patch-ok: <reason>` inline comments allowlist
- **Subject:** `check_no_self_monkeypatch` detector accepts inline rationale comments.
- **Decision:** specific call sites can opt out with a `# self-patch-ok: <reason>` comment that names why patching the named target is legitimate (typically: pydantic config knob, not behavior; external lib re-exported through our module).
- **Reason:** the detector can't distinguish "patching a behavior helper" from "patching a config flag with no behavior surface." Human-authored rationale closes the gap.
- **Scope:** detector logic in `compliance.py::_extract_patch_target`; instances in product test code.
- **Revisit trigger:** if a class of `self-patch-ok` instances clusters at a recognizable shape (e.g. all settings-knob patches) → formalize the carve-out as a structural detector exception rather than per-site comments.
- **Recorded by:** `mcp-tooling-expansion` (closed); detector documentation in `06-AGENTS.md`.

### Stripe SDK is the canonical webhook verifier (not the seed-lib helper)
- **Subject:** `noctusai_lib.security.webhook_signatures` covers patterns 1-3 (Hub-Signature / hex HMAC / Svix); pattern 4 (Stripe) is explicitly carved out.
- **Decision:** core's `app/services/stripe_service.py::construct_webhook_event` keeps using `stripe.Webhook.construct_event(...)` instead of the seed-lib helper.
- **Reason:** Stripe's SDK does HMAC + 5-min timestamp tolerance internally; wrapping it would either re-implement the timestamp logic (drift risk) or just shadow the SDK call. Don't wrap, don't reinvent.
- **Scope:** `products/core/backend/app/services/stripe_service.py`; `KB § PATTERNS/security/webhook-signatures.md § Pattern 4`.
- **Revisit trigger:** Stripe SDK changes verification API in a way that breaks our integration → re-evaluate.
- **Recorded by:** `webhook-hmac-consolidation/PROJECT.md`; `KB § PATTERNS/security/webhook-signatures.md`.

### Webhook helpers accept unsigned payloads with WARNING when secret unset
- **Subject:** development-environment convenience for `verify_hmac_*` / Svix helpers.
- **Decision:** when a webhook secret env var is unset, accept the payload with a structured WARNING log instead of rejecting.
- **Reason:** dev environments often run the bot without the real provider configured; failing closed would block local testing. CI/prod must set the secret; the WARNING surfaces the unsafe state observably.
- **Scope:** consumer-side pattern (e.g. `products/social-wiring/app/modules/email_marketing/.../routers/webhooks.py` — absorbed from the retired `mailing` product 2026-05-16); documented as the universal rule in `KB § PATTERNS/security/webhook-signatures.md § Universal rules`.
- **Revisit trigger:** a production deploy ever runs without the secret AND processes traffic — at that point the WARNING wasn't loud enough; tighten to a startup check / fail-fast in production.
- **Recorded by:** `KB § PATTERNS/security/webhook-signatures.md`.

### MCP toolkit retains `requirements.txt` alongside `pyproject.toml`
- **Subject:** `mcp/noctusai/` packaging — both `requirements.txt` and `pyproject.toml` exist with overlapping dep lists.
- **Decision:** keep both; `pyproject.toml` is canonical, `requirements.txt` is the back-compat path.
- **Reason:** the existing `-e ../../seed/lib/backend` editable install of the platform shared lib is set up via `requirements.txt`. Replicating editable installs from a sibling path inside `pyproject.toml` is clunky (relative-path PEP-660 installs work but require `[tool.uv]` or similar opinionated tooling). The duplication is small (~3 lines); the pain of converting is large.
- **Scope:** `mcp/noctusai/pyproject.toml` + `mcp/noctusai/requirements.txt`.
- **Revisit trigger:** the platform settles on a single Python packaging tool (uv / poetry / pdm) → consolidate.
- **Recorded by:** `mcp-ast-tools-hardening` Phase 2 (closed); inline comments in both files.

### MCP toolkit `requires-python = ">=3.10"` (not `>=3.11`)
- **Subject:** `mcp/noctusai/pyproject.toml` Python version floor.
- **Decision:** `>=3.10` even though the venv runs 3.11.
- **Reason:** the test suite uses `X | Y` typing syntax (PEP 604 — 3.10+); 3.11+ features aren't actively used. Setting the floor at 3.10 keeps the toolkit installable in any modern environment.
- **Scope:** `mcp/noctusai/pyproject.toml [project] requires-python`.
- **Revisit trigger:** the toolkit adopts 3.11-only features (e.g. `tomllib`, `ExceptionGroup`) → ratchet to `>=3.11`.
- **Recorded by:** `mcp-ast-tools-hardening` Phase 2 (closed) — Phase 0 finding (system Python 3.9 fails to collect drove the explicit declaration).

### `send_via_waha` exists in ERP and therapy (N=2 → FORMALIZED 2026-05-10)
- **Subject:** N=2 byte-level recurrence: WAHA `/api/sendText` HTTP transport duplicated at `products/erp-imobiliario/backend/app/services/whatsapp_service.py:319 (send_via_waha)` + `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:44 (send_via_waha)`. Each owned its own `httpx.AsyncClient` block, chat_id construction, error handling.
- **Decision:** **FORMALIZED 2026-05-10.** Both `send_via_waha` callsites now delegate to seed `noctusai_lib.integrations.whatsapp.WahaClient.send_text` (consumed via `get_whatsapp_client(...)` factory). Each product retains a thin wrapper that owns product-specific concerns: ERP keeps Brazilian phone normalization + DB config lookup + legacy `{message_id,status,phone,[error|dry_run]}` envelope; therapy keeps the explicit-arg signature + `ValueError`-on-error contract for `send_reminder`. Zero `httpx` calls remain in either product's `send_via_waha`. Auth-header behavior change captured in findings.md (ERP now uses `X-Api-Key` instead of `Authorization: Bearer`, aligning with WAHA standard and seed default).
- **Original framing (preserved for slip-pattern history):** the catalog row was filed at N=2 on the false premise that `send_message` was the recurrence; Engineer H's Phase 0 verification surfaced the real recurrence is `send_via_waha`. Re-scoped 2026-05-10 to Path A. `send_message` is N=1 (ERP Meta Cloud API; therapy stub) and stays as a separate follow-up project (`whatsapp-meta-cloud-api-seed-absorption`).
- **Scope:** WAHA transport: `products/erp-imobiliario/backend/app/services/whatsapp_service.py:319 (send_via_waha)` + `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:44 (send_via_waha)` — both now thin delegates. Out-of-scope (preserved by Path A): ERP `send_message` (Meta Cloud API, N=1) + therapy `send_message` stub (N=1) + therapy `messaging_service.send_message` (in-app, different concern).
- **Recorded by:** `projects/send-message-consolidation/` Phase 3 (closed 2026-05-10, Path A — re-scoped after Engineer H Phase 0 STOP+escalate).

### Vista audit path uses ERP's `validate_schema=False` mock (deferred to schema-drift project)
- **Subject:** Vista showcase router writes audit rows to `user_actions_log` (Phase 2 deliverable of the now-closed `vista-crm-wiring` project).
- **Decision:** the test mock for those writes runs through ERP's already-opted-out `MockSupabaseClient(validate_schema=False, schema="erp")` fixture, so insert-shape drift against the real `user_actions_log` schema is NOT caught by tests.
- **Reason:** ERP's broader `erp-schema-drift-reconciliation` project owns the flip to `validate_schema=True` across all ERP tests; doing it ad-hoc for one router would either break unrelated tests or duplicate the reconciliation logic. The audit row metadata is small + the migration already applied + the consent / LGPD posture is enforced at the router level (admin-only + audit logged), so the validation gap is narrow and time-bounded.
- **Scope:** `products/erp-imobiliario/backend/app/routers/vista_showcase.py` audit-log writes; covered by ERP's schema-validation opt-out at `tests/conftest.py:96,108`.
- **Revisit trigger:** when `products/erp-imobiliario/projects/erp-schema-drift-reconciliation/` closes and ERP flips to `validate_schema=True`, the Vista audit path will need explicit validation against the real `user_actions_log` columns. Re-evaluate at that close gate.
- **Recorded by:** `vista-crm-wiring` (closed + folder deleted 2026-05-02; this entry promoted at the close).

### Outbound webhook signer stays in `core/services/webhook_delivery.py`
- **Subject:** `products/core/backend/app/services/webhook_delivery.py` HMAC-SHA256 signing of outbound deliveries to org-registered endpoints (Stripe-style `{timestamp}.{body}` envelope; `X-Webhook-Signature` / `X-Webhook-Event` / `X-Webhook-Timestamp` headers).
- **Decision:** outbound signer stays in core. Only the cryptographic primitive (`hmac.new(...).hexdigest()` → `compute_hmac_sha256_hex(...)`) routes through the seed-lib helper.
- **Reason:** the signer is tightly coupled to delivery lifecycle — DB insert into `webhook_deliveries`, retention sweep, retry loop with exponential backoff, payload classification (LGPD minimization), failure logging. Pulling it into `noctusai_lib.security` would either drag the lifecycle into the seed-lib (wrong layer — it's a domain-bounded concern of core's webhook subscription product) or split the signer from its lifecycle (creating a brittle two-piece API). Inbound verifiers ARE seed-lib material because they're pure crypto; outbound delivery is a product feature.
- **Scope:** `products/core/backend/app/services/webhook_delivery.py`.
- **Revisit trigger:** a second product builds an outbound webhook subscription product (delivery + retention + retry). At that point, formalize the lifecycle pattern into seed-lib OR keep both implementations and re-record. Until then, single-adopter at core.
- **Recorded by:** `webhook-hmac-consolidation/PROJECT.md` Phase 2 close (2026-05-03).

### Alphabet/Google webhook signature scheme deferred (sibling-repo intake)
- **Subject:** the 2026-05-02 originating directive for `webhook-hmac-consolidation` mentioned both Meta-style `X-Hub-Signature-256` and Alphabet/Google-style schemes from the user's `whatsapp-google-scheduling` sibling repo.
- **Decision:** ship the seed-lib helper covering Meta / GitHub / WAHA / Svix / Stripe (the four shapes already adopted in this monorepo). Defer the Alphabet/Google scheme port to a small follow-up project when the sibling-repo findings land.
- **Reason:** none of the 4 current adopters speaks an Alphabet/Google webhook protocol. The seed-lib helper API is already format-agnostic-ready (`scheme` literal + `signature_header` + `timestamp_header` knobs); adding Alphabet's scheme will be additive when the spec arrives. Blocking this project's close on a spec we don't have would freeze the platform-wide hardening behind a single absent input.
- **Scope:** `seed/lib/backend/noctusai_lib/security/webhook_signatures.py`.
- **Revisit trigger:** the user pulls the `whatsapp-google-scheduling` Alphabet/Google webhook findings into this repo, OR a NoctusAI product gains an inbound Google API webhook integration — whichever comes first. Open `webhook-alphabet-scheme-port` then.
- **Recorded by:** `webhook-hmac-consolidation/PROJECT.md` §7 Q1 (2026-05-03).

### `noctus.dev.count_tokens` MCP tool ~~does not yet exist~~ — **FORMALIZED 2026-05-03**
- **Subject:** `KB § PATTERNS/architect/project-execution.md § 2.8 Multi-phase rule shipments — forward-stub + bullet-weight discipline § Measurement discipline` references `noctus.dev.count_tokens` as the offline MCP tool for measuring CLAUDE.md / KB / project-doc sizes.
- **Decision (retired 2026-05-03):** **FORMALIZED.** The tool ships at `mcp/noctusai/tools/cost_evaluation.py::count_tokens` (with `count_tokens_in_text` underlying primitive); registered in `mcp/noctusai/server.py:265` (descriptor) and `:414` (dispatch). Tokenizer is `tiktoken` (per `requirements.txt`), with `chars/4` fallback. Accepts `path` (file/dir/glob), `text` (inline), or both.
- **Reason for the original accept:** building the MCP tool inside `context-budget-overhaul` would have been scope creep; deferred to `mcp-server-expansion` where MCP tooling was the explicit deliverable. `wc -w` covered the project's directional 50%+ signal.
- **Scope:** retired. Tool ships at `mcp/noctusai/tools/cost_evaluation.py`; KB § 2.8 stub note removed from `KB § PATTERNS/architect/project-execution.md` in same flip.
- **Revisit trigger:** N/A — historical context; kept per the catalog's append-only-ish convention.
- **Recorded by:** `context-budget-overhaul/PROJECT.md` Phase 2 + Phase 8 (originating accept, 2026-05-03); `mcp-server-expansion` (formalization ship, ahead of catalog flip); flip recorded in `projects/vista-api-mcp/PROJECT.md` §11 2026-05-03 (catalog audit during Vista formalize).

### Per-product `app/scheduler.py` at N=3 — **FORMALIZED** in `noctusai_lib.api.scheduler`

- **Subject:** `products/social-wiring/app/modules/email_marketing/.../scheduler.py` (absorbed from the retired `mailing` product 2026-05-16), `products/personal-finance/backend/app/scheduler.py`, and `products/therapy-platform/backend/app/scheduler.py` previously each carried their own APScheduler instance + lifecycle.
- **Decision (retired 2026-05-03):** **FORMALIZED.** The seed-side primitive at `seed/lib/backend/noctusai_lib/api/scheduler.py` now owns `register(name, fn, hours/minutes/seconds/cron=...)` + `start_scheduler` + `stop_scheduler`. All 3 product `app/scheduler.py` files collapsed to thin wrappers (job functions + a `configure()` registration call + re-export of the seed-side `start_scheduler`/`stop_scheduler` so `main.py`'s lifespan wiring is unchanged).
- **Reason for the original accept:** the formalization needed a focused initiative (design the seed-lib API; migrate 3 products one-by-one; exercise cron + interval triggers; preserve the test baseline). Filed as `projects/seed-side-scheduler-primitive/` and now executed.
- **Scope:** retired. Outcome shipped at `seed/lib/backend/noctusai_lib/api/scheduler.py` + `seed/lib/backend/tests/test_scheduler.py` (14 tests) + product wrapper migrations.
- **Revisit trigger:** N/A — this entry is now historical context, kept per the catalog's append-only-ish convention.
- **Recorded by:** `projects/side-projects-batch/` Phase 1.c (originating accept) + `projects/seed-side-scheduler-primitive/` (formalization ship, 2026-05-03).

### `check_function_search_path_pinned` flags survive CREATE-OR-REPLACE supersession across migration files
- **Subject:** the keeper `check_function_search_path_pinned` detector (see `mcp/noctusai/tools/noctus/dev/compliance.py:2551`). It scans every `*.sql` file in `products/<p>/backend/migrations/` and flags every `CREATE FUNCTION` / `CREATE OR REPLACE FUNCTION` block whose text doesn't contain a `SET search_path` clause. It does not understand that a later migration's `CREATE OR REPLACE` supersedes an earlier unpinned definition.
- **Decision:** when a search_path gap is closed by shipping a new `CREATE OR REPLACE FUNCTION ... SET search_path = ...` in a fresh migration (per the "MCP migrations mirror the file" rule that forbids in-place rewriting of historical migration files), accept the residual detector findings against the original unpinned `CREATE` blocks. The runtime DB carries the pinned version; the static analyzer sees only the file-local text.
- **Reason:** the alternative — editing the source migration in-place to add `SET search_path` — violates the "Existing migration files (the replay log) are NOT rewritten" rule from `KB § PATTERNS/backend/database-rls.md`. Migration files are the authoritative replay log; rewriting them retroactively breaks the contract that older deployments replaying from zero produce the same DB state as the current head. The runtime risk addressed by Supabase advisor 0011 IS closed by the superseding migration (CREATE OR REPLACE drops + recreates the function with the pinned clause). What remains is detector noise, not a production gap.
- **Scope:** therapy-platform `011_scheduling_pilot.sql:126` (`gcal_authorization_is_fresh` — closed by `012_search_path_hardening.sql`). ERP-imobiliario `003_schema_separation.sql:91/96/101/308/696/750/756`, `004_mvp_expansion.sql:28`, `005_fix_sidebar_pages.sql:11` (9 functions — closed by `028_search_path_hardening.sql`). Same shape will apply for any future `00N_search_path_hardening.sql` migration on any product.
- **Revisit trigger:** detector v2 lands with multi-file supersession awareness (CREATE OR REPLACE in file `M > N` clears the finding in file `N` for the same `fn_qualified`). Recurrence threshold = 3+ products with the same shape — therapy + ERP = N=2 today; the third occurrence flips this entry toward **FORMALIZED** and files `keeper-detector-supersession-tuning`.
- **Recorded by:** `projects/keeper-trio-erp/PROJECT.md` Phase 2 close, engineer ZZ on `worktree-agent-a906ec599e71917d5`. Established precedent: therapy GG's `012_search_path_hardening.sql` left 1 finding standing in `011:126` — same shape, recorded retroactively here.

### Per-product TS strict mode is opt-in over time
- **Subject:** TypeScript `"strict": true` in each product frontend's `products/<product>/frontend/tsconfig.json`. Today every product frontend ships `strict: false` (or inherits a non-strict base).
- **Decision:** per-product TS strict mode is **opt-in over time, NOT a coordinated campaign**. Strict-quality types are enforced at the seed boundary only (`seed/lib/frontend/` + `seed/framework/frontend/`, both `strict: true`, gated by `.github/workflows/seed-typecheck.yml` — see `KB § 03-SEED-ARCHITECTURE.md § Seed Contract § 5. Contract enforcement § 1`).
- **Reason:** 8 product frontends × ~2-3h each ≈ 16-24h of mostly mechanical `!`-non-null-assertion fixes that *mask* the same null risk rather than removing it. The high-leverage subset — cross-product type contracts in `@noctusai/lib` + `@noctusai/seed` — already lands at the seed boundary and propagates to every consumer via raw-source `.ts` import (no build step, no `.d.ts` emission, so the strict-quality of seed types directly affects what each product sees). Per-product strict adds quality-of-life inside each product but does not tighten any cross-product contract. The per-product flip is the kind of work an individual maintainer can opt into when they're touching a frontend deeply — not a platform-wide deliverable that pays off the coordination cost.
- **Scope:** `products/{core,erp-imobiliario,personal-finance,therapy-platform,daily-life,social-wiring,seed,dev-team}/frontend/tsconfig.json` (`mailing` consolidated into `social-wiring` 2026-05-16).
- **Revisit trigger:** a product team **independently** flips `strict: true` in their `tsconfig.json` and closes the resulting errors at their own pace — that's the per-product happy path and doesn't change this catalog. Recurrence fires (flip toward **FORMALIZED**) when **3+ product frontends** end up at `strict: true` on their own (signals a coordinated push is warranted) OR a **real null-safety incident** in production is traced to a non-strict product file (signals the seed-boundary gate isn't catching enough).
- **Recorded by:** `projects/strict-mode-migration/PROJECT.md` Phase 5 close (2026-05-10). Original 8-frontend campaign drafted 2026-04-27 was retired here after the 2026-05-03 cost/leverage audit; seed-boundary gate shipped Phases 1-4 of the same project.

---

## How to add a new entry

1. **Confirm the divergence is genuinely accept-with-rationale.** If
   formalize or refactor would work and the cost is bounded, do that
   instead.
2. **Add a `### <short-title>` section** at the bottom of § Active
   decisions following the entry format above.
3. **Name the revisit trigger concretely.** "Eventually" or "if it
   gets bad" is not a trigger. "A second product needs the same
   divergence" or "the framework gains the X seam" is.
4. **Add an inline pointer near the divergence in code** —
   `# accept-with-rationale: <short-title> in KB § PATTERNS/common/accept-with-rationale.md`.
   The KB doc is the prose; the inline comment is the wayfinder.
5. **Update `KB § INDEX.md`** if this is the first entry on a new
   subject; this doc is already indexed so existing-subject additions
   don't change INDEX.md.

## How to retire an entry

When the revisit trigger fires:

- **If formalize wins:** flip the entry's first line to `**FORMALIZED
  in <project / commit>**` and append a one-line note on what
  changed. Keep the entry; it's now historical context.
- **If accept stands but the trigger is wrong:** update the
  revisit trigger to whatever the new evidence suggests.
- **If the divergence disappears organically** (the diverging code is
  deleted): flip to `**RETIRED — code removed in <commit>**`.

Don't delete entries. The catalog is append-only-ish; retirement is a
state change, not a removal.

### Seed-workspace chmod is symbolic, not enforcing
- **Subject:** `scripts/bootstrap/bootstrap-seed-workspace.sh` applies `chmod -h a-w` to every symlinked surface in the seed workspace.
- **Decision:** chmod runs at bootstrap time and is documented as a Layer 3 SYMBOLIC defense — not an actual write barrier.
- **Reason:** The user's stated mechanism *"chmod the symlinked surfaces"* cannot work as imagined cross-platform: macOS symlinks ignore mode bits at the kernel level (no-op), Linux mostly-ignores them too, and chmoding the symlink TARGETS would lock noc itself out of editing its own files (same OS user owns both directories). The realistic enforcement boundary is at commit-time via the template-side pre-commit hook (Layer 1 — PRIMARY); chmod stays as a marker that the surface is read-only by intent.
- **Scope:** `scripts/bootstrap/bootstrap-seed-workspace.sh` + `templates/seed-workspace-README.md` + `KB § PATTERNS/architect/seed-workspace.md`.
- **Revisit trigger:** macOS gains symlink mode-bit enforcement (unlikely), OR a new POSIX-portable per-symlink immutability mechanism appears (chflags+immutable that doesn't affect the target), OR a wrapper layer (FUSE / OverlayFS) becomes available on macOS that lets template see noc as read-only without affecting noc's own writes.
- **Recorded by:** `projects/seed-workspace/` Phase 0 audit (2026-05-03).

### Per-product `_render_bodies` + `_generate_narrative` digest wrappers retained at N=4 (AMENDED 2026-05-10)

- **Subject:** four products (`core/audit_digest_service.py`, `daily-life/weekly_review_service.py`, `social-wiring/email_marketing/campaign_debrief_service.py` — absorbed from the retired `mailing` 2026-05-16, `personal-finance/monthly_narrative_service.py`) carry per-product `_render_bodies(...)` and `_generate_narrative(...)` overrides. Originally module-level wrappers (2026-05-03); **as of 2026-05-10, refactored to be methods of `XDigestService(BaseDigestService)` subclasses** — see `KB § PATTERNS/backend/digest-seed.md`. The methods themselves still bind product-specific context-dict keys + LLM prompt strings to the seed primitive's `narrative(...)` / `render_digest_pair(...)` calls.
- **Decision:** keep both methods per-subclass. `_render_bodies` binds product-specific context-dict keys to the seed primitive's `context=` arg; `_generate_narrative` binds product-specific LLM `system` + `user_prompt` strings.
- **Reason:** the wrappers are the *domain-binding boundary*. The LLM prompts (security-audit narrative vs. weekly habit review vs. campaign metrics vs. monthly cashflow) are fundamentally per-product; abstracting them through a `prompt_factory` indirection would either bloat the seed-lib API with per-domain prompt knowledge or split the prompt from its data-shape (creating a brittle two-piece API). The recurrence-rule's MUST-formalize threshold (N≥3) fired here, but Phase 0 audit found the formalize-target was the *primitives* (2026-05-03) and the *orchestrator template* (2026-05-10) — which is what shipped. The remaining per-method overrides are correctly per-product code.
- **Scope:** `products/{core,daily-life,social-wiring,personal-finance}/backend/app/services/*_digest_service.py` (or equivalent name; `mailing` consolidated into `social-wiring/email_marketing` 2026-05-16). ERP excluded per the existing "ERP metas digest does NOT use `noctusai_lib.domain.digest`" entry above.
- **Revisit trigger:** the existing 4 method-overrides start sharing identical prompt-shape boilerplate (e.g. all begin with the same system-prompt prefix), at which point pull the prefix into a `digest_system_preamble` helper. The N=5 narrative-using digest trigger is satisfied at the orchestration layer (`BaseDigestService`); per-method overrides remain accept-with-rationale.
- **Recorded by:** `projects/digest-helpers-absorption/` PROJECT CLOSE (2026-05-03; commit `07afb18`). **Amended 2026-05-10** with `seed-digest-base-class` branch merge — wrapper sites moved from module-level functions to subclass methods of `BaseDigestService`. The boundary rationale stands; only the surface shape changed.

### MCP settings shim ships its own local `get_settings()` factory (not in `noctusai_lib`)
- **Subject:** `mcp/noctusai/settings.py` re-exports `BaseAppSettings` from `noctusai_lib.config.settings` as `Settings` AND ships a local `lru_cache(maxsize=1)`-backed `get_settings()` singleton. The lib does NOT ship a global `get_settings()` of its own.
- **Decision:** keep the factory MCP-local, not in the lib.
- **Reason:** `noctusai_lib/config/settings.py:13-22` documents that products extend `BaseAppSettings` per-product (each backend resolves the root `.env` from a different `__file__`). A lib-level singleton would force every consumer process to share one Settings instance — wrong shape for per-product backends. The MCP server is one of N future consumers of the shim pattern; an MCP-scoped factory is the right granularity. When this MCP eventually extracts to its own repo (per `mcp/noctusai/settings.py:1-7` docstring), the shim becomes the source — every consumer reads its own `.env` against the same `BaseAppSettings` shape.
- **Scope:** `mcp/noctusai/settings.py` (today). Future extracted MCP repo's own `settings.py`.
- **Revisit trigger:** a second non-product process needs the same `Settings()` singleton (e.g. a CLI orchestrator, a webhook gateway, a separate MCP server in a sibling repo). At N=2 the factory pattern moves into the lib (e.g. `noctusai_lib.config.factories.lru_singleton(BaseAppSettings)`). Trigger also fires if `BaseAppSettings` itself starts requiring multi-process coordination (very unlikely; would force a redesign).
- **Recorded by:** `projects/mcp-server-expansion/` Phase 1 (2026-05-03; commit `bfe4f83`).

### `noctusai_lib.domain.ai.tool_audit._safe_jsonable` accepts string + repr fallbacks instead of raising
- **Subject:** the `_safe_jsonable(value)` helper in `seed/lib/backend/noctusai_lib/domain/ai/tool_audit.py`. Its job is to coerce an arbitrary `arguments` / `result` value into something a Postgres JSONB column will accept.
- **Decision:** when `json.dumps(default=str)` round-trip succeeds it returns whatever JSON-load produces — including bare strings (e.g. a Pydantic model whose `__repr__` rendered via `default=str`). When even that fails, it returns `{"_repr": repr(value)}` and emits `logger.debug(...)`. Never raises.
- **Reason:** the audit writer is **best-effort** by contract — failing to persist a row must NEVER break the user-facing tool dispatch (the audit table is for visibility, not correctness). A strict serializer that raised on unknown types would either: (a) propagate up into the dispatch and break the user flow, or (b) need a try/except wrapper at every call site that swallowed the failure differently — multiplying the silent-error surface. Keeping the fallback inside `_safe_jsonable` centralizes the policy + keeps `make_audit_writer` callers simple. The string / `_repr` fallback is acceptable for an observability table; a strict consumer wanting structured data builds its own wrapper.
- **Scope:** `seed/lib/backend/noctusai_lib/domain/ai/tool_audit.py::_safe_jsonable` and every consumer wired via `make_audit_writer(db, table_class)`.
- **Revisit trigger:** a downstream BI consumer reports it can't query a meaningful percentage of rows because `arguments` / `result` arrived as bare strings or `_repr` envelopes. At that point either (a) flip `_safe_jsonable` to opt-in strict mode (`make_audit_writer(..., on_unserializable="raise")`) so producers learn to redact upstream, or (b) ship a typed companion table for the strict-shape rows. Not before — premature strictness would break products mid-rollout.
- **Recorded by:** `projects/llm-tool-call-audit/` Phase 1 (2026-05-03; commit `bf0bfe3`).

### Vista CRM client + normalizers + showcase DTOs duplicated at N=2 — **FORMALIZED 2026-05-03**
- **Subject:** `VistaClient` + 7-class error hierarchy (`VistaError` / `VistaConfigError` / `VistaUpstreamError` / `VistaPermissionDenied` / `VistaNotFound` / `VistaFieldNotAvailable` / `VistaTimeout`) + `VistaCallResult` + `extract_items` + 4 normalizers (`vista_imovel_to_showcase`, `vista_imovel_detalhes_to_showcase`, `vista_usuario_to_showcase`, `vista_agencia_to_showcase`) + 4 showcase DTOs (`ShowcaseImovel`, `ShowcaseImovelDetalhes`, `ShowcaseUsuario`, `ShowcaseAgencia`).
- **Decision (retired 2026-05-03):** **FORMALIZED** in `seed/lib/backend/noctusai_lib/integrations/vista/{__init__,client,normalizers,types}.py`. Both consumers — the in-repo Vista MCP server (`mcp/vista/`) and the ERP showcase router/service (`products/erp-imobiliario/backend/app/{routers,services}/vista_showcase*.py`) — import from the seed-lib home. The duplicated `products/erp-imobiliario/backend/app/integrations/vista/` package was deleted; the duplicated `mcp/vista/{client,normalizers}.py` were deleted (mcp/vista/types.py kept, trimmed to MCP-tool-IO schemas only). ERP-product-specific response wrappers (`ShowcasePagination`, `ShowcaseEnvelope`, `ShowcaseTabStatus`, `ShowcaseDiagnostic`) moved to `app/services/vista_showcase_types.py` — they're showcase-router shapes, not Vista-protocol shapes, so they correctly stay in the ERP product.
- **Reason for the original "accept" framing (and why it was wrong):** during Phase 1 of the Vista MCP build (2026-05-03 morning) the duplication was framed as "recurrence note in PROJECT.md §11 → absorb later when `mcp-server-expansion` substrate ships." This was silent debt: no catalog entry, no follow-up project filed, no concrete revisit trigger — exactly what `KB § PATTERNS/common/accept-with-rationale.md § The pattern` warns against. The user flagged the miss the same day and the formalize landed inline, in the same session.
- **Bug evidence that proved the cost:** the `_detect_unavailable_field` substring-search bug (Vista wire body uses JSON unicode escapes; naive `"não está disponível" in body_text` never matched) had to be fixed in TWO places the same morning. If one had been missed, Phase 4.5's 422 hardening would have stayed secretly broken in that copy. Single-source eliminates that risk.
- **Scope:** retired. Canonical home: `seed/lib/backend/noctusai_lib/integrations/vista/`. Two consumers: `mcp/vista/` (in-repo MCP) + ERP showcase router/service. ERP-side `vista_showcase_types.py` retains the 4 router-response wrappers.
- **Revisit trigger:** N/A — historical context. Convention going forward: any third Vista consumer (e.g. an `agents/` LLM tool, a sibling-repo MCP, a future bot) imports from `noctusai_lib.integrations.vista` directly. Sub-field calibration discovery (currently `mcp/vista/calibration.py`) is the natural next promotion candidate when a second probe-style consumer appears.
- **Recorded by:** `projects/vista-api-mcp/PROJECT.md` §11 (2026-05-03 — Phase 1 originating accept + same-session formalize). FORMALIZED in same session per the user's "reconsider your accept-with-rationale" prompt + the catalog rule "promote permanent accepts to the catalog before the project folder is deleted."

### Migration `008_org_scoping_transition.sql` retains non-idempotent `RENAME COLUMN user_id` blocks
- **Subject:** `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` — the transition migration that flipped PF from user-scoped to org-scoped. After Phase 6 of `pf-org-scoping-migration` rewrote `001_personal_finance.sql` to declare deployed truth (org-scoped from the start), 008 became near-redundant: most clauses already use `IF EXISTS` / `IF NOT EXISTS` and short-circuit, but the 12 per-table `ALTER TABLE ... RENAME COLUMN user_id TO created_by` and the corresponding `UPDATE ... WHERE t.user_id = u.id` statements are not idempotent. On a fresh clone (where 001 already produced truth), they would error because `user_id` no longer exists.
- **Decision:** keep 008 on disk with a documenting header that explains the transition history and the non-idempotent caveat. Do NOT add `DO $$ IF EXISTS (column) THEN ... END IF; $$` wrappers to each per-table block at this time.
- **Reason:** the live DB has 008 in its migration log already (will never re-run). Fresh-clone replay is currently a desk-checked scenario — Supabase branching is Pro-tier-only and not enabled on this org, so we cannot actually verify a wrapped 008 would behave correctly without paying the Pro upgrade. Wrapping all 24 non-idempotent statements (12 tables × {UPDATE, RENAME}) is ~120 LOC of mechanical change with no observable benefit until someone actually runs migrations against an empty DB. Premature wrapping risks introducing its own bugs (DO block semicolon edge cases, search_path issues) that branching can't catch.
- **Scope:** `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` only. Other PF migrations (001-007) are idempotent or describe schemas that don't conflict with rewritten 001.
- **Revisit trigger:** any of (a) someone needs to spin up a fresh PF database for staging / testing / a second tenant, (b) Supabase branching becomes available on this org (Pro tier or above), at which point we have a verification environment to harden the wrappers in safely, (c) a second product hits the same pattern (user-scoped → org-scoped flip with rewritten-baseline migration) — that's N=2, formalize the wrapping pattern into a shared helper. None of those have fired today.
- **Recorded by:** `products/personal-finance/projects/pf-org-scoping-migration/` Phase 6 + Phase 8 (2026-05-03).

### MCP workspace-aware tool integration — **SUPERSEDED by parallel-agent collision protocol 2026-05-03**
- One-shot collision between the `seed-workspace` project and the parallel `mcp-server-expansion` agent (parallel agent reverted my edits twice during the session). Originally landed here as a deferral; resolved same-day when the user signalled the parallel agent was done. **Now subsumed by the parallel-agent collision protocol** at `KB § PATTERNS/architect/project-execution.md § 2.9` — future collisions get a `projects/parallel-collision-<topic>-<YYYY-MM-DD>/` project per the protocol, not a catalog entry. This entry is the worked example referenced from § 2.9; preserved as the originating incident, not as an active divergence.
- **Recorded by:** `projects/seed-workspace/` PROJECT CLOSE (2026-05-03).

### Real Google Calendar adapters (service-account + OAuth) — **RESOLVED 2026-05-03**
- **Originally deferred** from `whatsapp-seed-absorption` Phase 7 (Fake adapter + types + factory shipped; service-account + OAuth adapters left for a follow-up). The deferral premise was: real adapters require (a) `googleapiclient` + `google-auth` runtime deps in seed-lib; (b) a credential-repo abstraction story; (c) mock-based tests for the Google SDK. The Fake unblocked chatbot framework integration immediately while the real adapters waited for a first-consumer trigger.
- **Resolved same day** alongside the chatbot-framework rename: `googleapiclient` + `google-auth` added to `seed/lib/backend/pyproject.toml`; `GoogleCalendarServiceAccountAdapter` + `GoogleCalendarOAuthAdapter` shipped at `noctusai_lib/integrations/google_calendar/{service_account_adapter,oauth_adapter}.py`; `CalendarCredentialResolver` Protocol + `ServiceAccountCalendarCredentials` + `OAuthCalendarCredentials` dataclasses ship the credential-repo abstraction at `credentials.py`; `get_calendar_adapter(resolver, tenant_id)` factory picks adapter kind from the credentials returned by the resolver, falling back to Fake when no resolver / no credentials. 18 mock-based tests in `tests/integrations/google_calendar/test_real_adapters.py` cover create / get (404 → None) / list (ISO bounds) / wrong-credentials-kind raise / OAuth refresh-on-invalid / factory selection.
- **Preserved as worked example** of the "Verify the seed ships it" methodology surfaced 2026-05-03 (`KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test`) — the deferral was caught at decision-time during `therapy-scheduling-pilot` Phase 0 *before* it silently expanded pilot scope. Future deferrals follow the same shape: catalog here, name the consumer trigger, resolve when the consumer arrives.

### Calendar credential seam — `CalendarCredentialResolver` Protocol over spec'd `Callable` — **FORMALIZED 2026-05-03 → `KB § PATTERNS/architect/seed-lib-layout.md § Consumer-injection seams`**
- **Subject:** `projects/google-calendar-real-adapters/` PROJECT.md §2 constraint #3 specified the credential-repo abstraction as a `Callable[[user_id_or_clinic_id], OAuthCredentials]`. The agent who shipped the real adapters chose `CalendarCredentialResolver` Protocol returning a `ServiceAccountCalendarCredentials | OAuthCalendarCredentials | None` union instead.
- **Originally landed here as ACCEPTED** (2026-05-03 close-gate). User correctly challenged that triage call: a Protocol-vs-Callable choice with a clear better answer is a **formalize** outcome, not an **accept** — accept is the weakest of the three and reserved for genuinely-defensible-but-not-improvable divergences. Same-day reclassified to FORMALIZED.
- **Formalization landed in `KB § PATTERNS/architect/seed-lib-layout.md § Consumer-injection seams — Protocol over Callable`** — codifies the seed-wide rule: when a consumer-injected dependency has a discriminated-union return, a multi-method surface, or a typed signature that's part of the seed's public contract, it ships as a `typing.Protocol`. Bare `Callable` only when the seam is genuinely a one-arg one-return-type pure function with no dispatch.
- **Why formalize, not accept:** the Protocol shape was strictly better in this case (factory-side dispatch over typed-union, matches existing seed convention `TravelLookup` / `Conflict` / `Scorer` / `MapsAdapter`). Accepting it as a one-off divergence would have left every future seed-side credential-resolver author free to pick Callable again. Formalizing makes Protocol the default, with bare-Callable now needing its own justification.
- **This entry is preserved as the originating triage record** — the formalization KB section back-references this catalog row. Future similar Protocol-vs-Callable triage decisions follow the formalized rule, not this entry.
- **Recorded by:** `projects/google-calendar-real-adapters/` close-gate (2026-05-03), reclassified same day after user feedback on the original ACCEPTED entry.

### `KB § 04-SHARED-LIBRARY.md` catalog row deferred for new `whatsapp-seed-absorption` namespaces
- **Subject:** `noctusai_lib.integrations.{whatsapp,redis,google_calendar,google_maps}` + `noctusai_lib.domain.chatbot` namespaces shipped 2026-05-03 by `whatsapp-seed-absorption` Phase 9, but `KB § 04-SHARED-LIBRARY.md` was NOT updated to add catalog rows for them.
- **Decision:** ship the new KB pattern doc (`KB § PATTERNS/backend/whatsapp-chatbot-seed.md`) + INDEX entries + CLAUDE.md §2 Map pointer; defer the catalog-row paperwork to a follow-up.
- **Reason:** the namespaces are discoverable via the KB pattern doc + INDEX By-topic entries (the agent reading discipline says go to KB first). The shared-library catalog is a secondary index; updating it for every absorption batch is paperwork churn that lags reality. Lower-priority than landing the actual capability.
- **Scope:** `KB § 04-SHARED-LIBRARY.md` only — INDEX + pattern doc + CLAUDE.md are current.
- **Revisit trigger:** any of (a) a future agent gets confused looking up a `noctusai_lib.integrations.whatsapp` symbol via the catalog and surfaces it, (b) a paperwork follow-up commit sweeps the catalog (cheap inline update once multiple deferred catalog rows accumulate), (c) the shared-library doc is rewritten end-to-end. None today.
- **Recorded by:** `projects/whatsapp-seed-absorption/` Phase 9 (closed 2026-05-03).

### Hard-coded `tools/<x>.py` paths in test code — scanner deferred at N=1
- **Subject:** Test files occasionally hard-code module file paths in
  `mock.patch("<dotted.module.path>.func")` strings or
  `Path(...) / "tools" / "<x>.py"` literals. mcp-server-fastmcp-switch
  Phase 3 found 4 such sites in 3 test files
  (`test_outline_python.py:214`, `test_compliance.py:992-1022` ×3,
  `test_three_way_sync.py:31`) — they had to be fixed by hand because
  the libcst-based import rewriter only walks `import` / `from-import`
  statements, not string literals.
- **Decision:** do NOT formalize a complementary scanner today; just
  log the pattern + the known features that could detect it.
- **Reason:** **N=1 today** (one focused-session relocation event
  surfaced the pattern). The libcst rewriter handled the 99% case
  (statements); a string-aware scanner is meaningfully more code (must
  parse the dotted-string into a real module reference + cross-check
  against the moved set). At N=1 the cost-benefit doesn't pencil out.
- **Scope:** `mcp/noctusai/tests/**/*.py` — and any future test file
  that hard-codes module paths in `mock.patch(<str>)` or
  `Path(...) / "<dirname>" / "<filename>.py"` constructions.
- **Known features that could help when this fires again:**
  - `noctus.dev.scan_recurrence` — detects recurring code shapes
    across files; could be extended to recognize the
    `mock.patch("<str>")` literal-path pattern.
  - `noctus.dev.scan_within_product_helpers` — already inspects
    string literals for product-specific paths; extending its
    detection set to module-path strings is incremental.
  - libcst's `cst.SimpleString` visitor — a future
    `relocate_string_paths.py` rewriter would visit
    `cst.SimpleString` nodes whose value parses as a dotted path
    starting with `tools.` or matches the moved-files set.
- **Revisit trigger:** **N=2** — any future code-relocation project
  that has to manually fix similar hard-coded paths in tests, OR a
  string-aware scan tool gets built independently for another reason
  and could absorb this case for free. Recurrence flips this from
  accept → formalize.
- **Recorded by:** `projects/mcp-server-fastmcp-switch/` Phase 3
  (closed 2026-05-03).

---

## Entries from `media-scheduling-port-resume` (closed 2026-05-04)

> **DELETED 2026-05-11.** The `media-scheduling` product was deleted in favor of `imobi-scheduling` (same product, divergent shapes; imobi was the canonical cleaner adopter — single 001 migration, Supabase-native audit adapter, factory-shaped WhatsApp router, 393 tests passing, DEPLOYMENT.md). All file-paths cited in the entries below point to deleted code. Entries kept for **methodology archaeology** — the rationales (LID-auth at N=1 stays product-side; dispatcher mutation vs per-call `tool_handler=`; hybrid SQLAlchemy+Pydantic at the seed-audit-contract boundary; etc.) remain relevant when the next product hits the same shape. Their **revisit triggers** still fire — imobi-scheduling re-instantiates the WhatsApp/Calendar/Maps surface and inherits the open questions. If/when N=2 fires, the move-to-seed conversation re-opens; cite this catalog block for context.
>
> **UPDATE 2026-05-16 (`social-wiring-absorption` Wave 4):** `imobi-scheduling` itself was subsequently consolidated into **`products/social-wiring/`** and retired. Any `products/imobi-scheduling/...` or `products/media-scheduling/...` path cited below resolves, for live code, to the absorbed module under `products/social-wiring/app/modules/scheduling/`. The rationales and revisit triggers remain durable as written; treat the cited paths as historical provenance, not live pointers. Durable record: `project-history/ledger.ndjson` slug `social-wiring-absorption-wave4-teardown`.

### LID-aware first-inbound auth stays product-side

- **What:** `products/media-scheduling/backend/app/services/lid_auth.py::LidAuthService` (3-path WhatsApp `chat_id` → `authorized_user` resolution: direct LID match, PendingChatIdentity capture, anonymous-but-known-phone fallback).
- **Why product-side and not seed:** the LID/JID semantics are WhatsApp-specific (chat_id format includes the device-identifier suffix) AND the resolution policy is real-estate domain logic (which authorized_user gets attached to a fresh inbound from an unknown phone). At N=1 product, the abstraction would be premature.
- **Revisit trigger:** **N=2** — when a second WhatsApp-driven product needs the same shape, recurrence-rule fires and the resolver's pure parts move into `noctusai_lib.security.lid_auth` (or `noctusai_lib.integrations.whatsapp.identity`). The product-specific bits (which user-table to query) stay product-side via a Protocol seam.
- **Recorded by:** `projects/media-scheduling-port/` Phase 3 + Phase 7 close (2026-05-04).

### Dispatcher tool-registry mutation via `register_scheduling_tools(dispatcher)`

- **What:** `products/media-scheduling/backend/app/services/scheduling_tools.py::register_scheduling_tools(dispatcher, context_provider, tools)` mutates the seed `LLMDispatcher` instance — sets `dispatcher.tool_payload` (OpenAI tools list), `dispatcher.tool_handler` (Callable), `dispatcher.tool_registry`. The seed's canonical pattern is per-call `tool_handler=` parameter.
- **Why mutation, not the seed pattern:** at the worker's lifecycle, tools are registered ONCE at startup and reused for every dispatch — passing `tool_handler=` per-call would mean re-resolving the registry every time. Mutation matches the worker's lifecycle better; seed pattern fits short-lived call sites better.
- **Revisit trigger:** **N=2** — when a second product needs persistent tool registration on a dispatcher, recurrence-rule fires and `noctusai_lib.domain.chatbot.tool_registry` ships (likely as `LLMDispatcher.with_tools(registry)` returning a wrapped dispatcher that owns the registry).
- **Recorded by:** `projects/media-scheduling-port/` Phase 4 + Phase 7 close (2026-05-04).

### Test self-patches for unconfigured-env paths annotated `# self-patch-ok`

- **What:** `products/media-scheduling/backend/tests/routers/test_oauth_credentials.py:92-94` patches `app.config.settings.google_oauth_client_id` (and the two sibling secrets) to empty strings to simulate the unconfigured-env path the router returns 503 on.
- **Why exempt from the no-self-patching rule:** the router's behavior under "no OAuth secrets configured" IS what we're testing. Pydantic settings' validators don't permit constructing an empty `Settings()` instance because the fields are required at boot — the only way to drive the unconfigured path is via post-boot patch. The annotation `# self-patch-ok: simulates the unconfigured-env path the router itself returns 503 on` makes the rationale visible at the call site.
- **Revisit trigger:** when noc adopts a `make_test_settings(**overrides)` helper (would unblock test-time settings construction without monkeypatch), this entry retires.
- **Recorded by:** `projects/media-scheduling-port/` Phase 7 close (2026-05-04).

### `route_groups` table name (vs `routes` in PROJECT.md spec)

- **What:** PROJECT.md §5 mapping listed `Route → routes`; the actual landed Supabase table is `media_scheduling.route_groups` (matching the source's SQLAlchemy `__tablename__`). Engineer A surfaced the drift; chose to keep source's name rather than rename mid-port.
- **Why kept:** the source repo's data model uses `route_groups` (a logical grouping of cached origin/destination travel-time tuples). Renaming during port adds risk for marginal gain.
- **Revisit trigger:** if a future routing-cache refactor (`noctusai_lib.domain.routing.PersistentTravelCache` or similar) ships and the table becomes a generic origin/destination cache, rename then.
- **Recorded by:** `projects/media-scheduling-port/` Phase 2 (Engineer A) + Phase 7 close (2026-05-04).

### Hybrid SQLAlchemy ORM + Pydantic models in `app/models/`

- **What:** `products/media-scheduling/backend/app/models/` ships BOTH SQLAlchemy ORM (`ToolCallAudit`, `ConversationSummary`, `PendingChatIdentity`) AND Pydantic value objects (everything else: `Appointment`, `AuthorizedUser`, `Condominium`, `CrewSkill`, `OAuthCredential`, `Property`, `RouteGroup`, `ServiceType`).
- **Why hybrid:** the seed `make_audit_writer(db, table_class)` contract requires a SQLAlchemy class (so `ToolCallAudit` stays ORM). The product's actual data layer is Supabase-client-native (Pydantic value-objects type-narrow row dicts). Engineer C and Engineer D each independently chose the right shape for their consumers; the merge resolution kept both.
- **Why not pick one:** picking pure Pydantic breaks the seed audit contract (would require per-product audit-writer reimpl). Picking pure ORM forces every Supabase-client touchpoint through a sql-binding layer that adds no value.
- **Revisit trigger:** if seed `make_audit_writer` changes signature to accept a Pydantic-style spec (e.g. `make_audit_writer(table_name, schema_class)`), ToolCallAudit can convert to Pydantic and the hybrid retires.
- **Recorded by:** `projects/media-scheduling-port/` Phase 3+4 merge resolution + Phase 7 close (2026-05-04).

---

## Entries from `seed-hardening-from-youtube-crawler` (in progress 2026-05-04)

> **RETIRED 2026-05-16 (`social-wiring-absorption` Wave 4).** The `youtube-crawler` product was consolidated into **`products/social-wiring/`** and retired. The hardening *rationales* below are durable methodology (Trivy non-runtime CVE accepts, test-class dedup, etc.) and their revisit triggers still fire; any `products/youtube-crawler/...` path is historical provenance, not a live pointer — the equivalent live surface is the seed `products/seed/backend/Dockerfile` slim image + `products/social-wiring/`. Durable record: `project-history/ledger.ndjson` slug `social-wiring-absorption-wave4-teardown`.

### `TestSqlTemplatesIntegration` test class duplicated in `test_scaffold.py` and `test_scaffold_migration.py`

- **What:** Both `mcp/noctusai/tests/test_scaffold.py` and `mcp/noctusai/tests/test_scaffold_migration.py` ship a `TestSqlTemplatesIntegration` class asserting that `set_search_path()` / `updated_at_function()` / `updated_at_trigger()` / `rls_subquery_policy()` outputs from `noctusai_lib.domain.sql_templates` appear verbatim (whitespace-normalized) in the scaffolded SQL.
- **Why accept-with-rationale at N=2:** the third consumer's home is uncertain — Phase 2 (oauth router, jobs primitive) and Phase 3 (storage, quota) MAY add more SQL-emitting tools, in which case extracting now lands a helper at a destination that better fits N≥3. Extracting prematurely (e.g. into `mcp/noctusai/tests/_sql_templates_assertions.py`) before knowing whether the helper should live in `mcp/noctusai/tests/` or `seed/lib/backend/tests/` is an arbitrary choice. The 30-LOC duplication is cheap to carry; the wrong-home extraction is expensive to undo.
- **Revisit trigger:** **N=3** — when Phase 2 or 3 adds a third SQL-emitting tool, the recurrence rule's "MUST formalize" arm fires; all three consumers' locations are known then.
- **Recorded by:** `projects/seed-hardening-from-youtube-crawler/` Phase 1 close (2026-05-04, Engineer C surfaced; architect triaged).

### `tests/test_youtube_integration.py` flat path (siblings live under `tests/integrations/<name>/`)

- **What:** YouTube integration tests live at `seed/lib/backend/tests/test_youtube_integration.py` (top-level). Sibling integrations (`google_calendar`, `google_maps`, `whatsapp`) follow `tests/integrations/<name>/{test_fake_adapter.py, test_real_adapters.py}` (nested folder, split fake/real).
- **Why accept-with-rationale:** the engineer brief specified the flat path explicitly; following the brief preserved zero-context dispatch correctness. The flat path is functionally equivalent (same module imports, same pytest collection). Relocating mid-flight adds merge friction with no behavioral benefit.
- **Revisit trigger:** when a second integration is added under the seed-hardening umbrella (Phase 3 storage / quota), align all three at once via a single `git mv`. Cosmetic.
- **Recorded by:** `projects/seed-hardening-from-youtube-crawler/` Phase 1 close (2026-05-04, Engineer B surfaced; architect triaged).

### NF-e issuance lives in `products/adconnect/.../nfe_service.py` at N=1 (seed-lib lift triggered by N=2)

- **Subject:** `products/adconnect/backend/app/services/nfe_service.py` (444 LOC) ships a Brazilian NF-e issuance surface in the canonical Protocol + Fake + Real + factory shape per `KB § PATTERNS/backend/seed-fake-real-adapter.md`: `NFeProvider` Protocol + 5 DTOs (`NFeItem`, `NFeIssueRequest`, `NFeIssueResult`, `NFeCancelRequest`, `NFeCancelResult`) + `FakeNFeProvider` + `FocusNFeProvider` (httpx-based REST adapter against `homologacao.focusnfe.com.br` / `api.focusnfe.com.br`, `ambiente=homologacao|producao` toggle, `FocusNFeMisconfiguredError` raise-on-missing-API-key, no silent degraded mode) + `make_nfe_provider(provider_name, **config)` factory with `fake` / `focusnfe` switch and `nfeio` / `enotas` `NotImplementedError` stubs.
- **Decision:** module stays single-product at AdConnect for now. Do **not** lift to `noctusai_lib.integrations.nfe` today.
- **Reason:** N=1 consumer. The seed-fake-real-adapter rule explicitly fires at N≥2 (`"Gap + N=2+ consumers → DRY-recurrence, file the seed real-adapter project"`); N=1 ships against the Fake the product already has. Premature absorption bloats the lib with single-consumer code that's still being calibrated by its first product (e.g. the `_build_payload` Focus-NFe-specific JSON shape, the `_map_status` provider-status vocabulary, the `cancel`-by-ref-vs-chave compromise documented in the source). Phase 0 audit on 2026-05-10 confirmed N=1 via word-boundary grep (`\bnfe\b|\bNFe\b|\bNF-e\b|nota_fiscal|nota fiscal`) + adjacent-domain grep (NFS-e / CT-e / MDF-e / Focus NFe / NFE.io / eNotas) + `noctus.dev.scan_cross_product_helpers` + `noctus.dev.scan_within_product_helpers`. The only XML-fiscal recurrence in the codebase is ERP's `dimob_service.py` + `xml_feeds.py`, which share `xml.etree.ElementTree` (stdlib) but target totally different domains (DIMOB income-tax informational return + property-listing feeds) — no NF-e helper to absorb.
- **Scope:** `products/adconnect/backend/app/services/nfe_service.py` + `products/adconnect/backend/tests/services/{test_nfe_service.py,test_focusnfe_provider.py,test_nfe_xml_parser.py}` (9 NF-e tests live product-side).
- **Revisit trigger:** **a second product surfaces a need for NF-e issuance** (e.g. `personal-finance` invoicing for self-employed users, or a future B2B product, or any consumer that asks for `nfeio` / `enotas` to replace the factory's `NotImplementedError` stubs). At N=2 the lift project follows the recipe captured in `projects/noctusai-lib-nfe-domain-absorption/findings.md § K1`: split single file into `noctusai_lib/integrations/nfe/{__init__.py,types.py,fake_adapter.py,focus_adapter.py}` mirroring `google_calendar`'s 5-file layout; refactor AdConnect's `nfe_service.py` to a thin re-export shim; new consumer imports from the lib directly; move Fake-side + Protocol-contract tests to `seed/lib/backend/tests/test_integrations_nfe.py`. Optional `credentials.py` Protocol if N=2 needs a per-tenant credential resolver (today AdConnect uses env vars; sufficient at N=1). The factory's `nfeio` / `enotas` `NotImplementedError` slots already anticipate the multi-vendor reality, so the lift project starts by replacing those stubs with the second consumer's real adapter.
- **Recorded by:** `projects/noctusai-lib-nfe-domain-absorption/PROJECT.md` (2026-05-10) — design-only project filed at AdConnect MVP close to encode the N=2 trigger structurally + pre-specify the lift target (`noctusai_lib.integrations.nfe`) so a future agent doesn't re-design at trigger time. Originating module shipped in `archive/projects/2026-05-10/01-adconnect-mvp-implementation/` Phase 5 (commit `f520165`).
- **Inline wayfinder pending:** `nfe_service.py` lives on the `adconnect-mvp-implementation` branch (not yet merged into `main` as of this entry's filing — the `archive/projects/.../adconnect-mvp-implementation/` artifact records the close, but the source files merge in a separate operation). The inline `# accept-with-rationale: NF-e issuance lives in products/adconnect/.../nfe_service.py at N=1 (seed-lib lift triggered by N=2)` comment lands as a drive-by edit when adconnect-mvp merges to main, or when the next NF-e-touching session opens the file.

---

## Entries from `keeper-test-status-assertion` (closed 2026-05-06)

> ~~3 erp-imobiliario tests catalogued for cross-product cleanup OOS.~~
> **RESOLVED 2026-05-06** — drive-by fix applied during YouTube Crawler
> Phase 3 close: each of the 3 tests received a 1-line
> `assert resp.status_code == 200` insert at the call site. Detector
> now runs clean across the entire repo (`noctus.dev.review` returns
> zero `test_status_assertion` findings). Entries removed.

---

## Entries from `trivy-prescan-2026-05-11` (filed 2026-05-11)

### `wheel` CVE-2026-24049 carried in runtime venv (multi-stage Docker leak; attack surface not exercised)

- **Subject:** `wheel==0.45.1` ships in `/opt/venv` in every slim image (`noctus-seed-backend:slim`, `noctus-youtube-crawler-backend:smoke`, and by extension every product whose Dockerfile is the canonical seed copy at `products/seed/backend/Dockerfile`). Trivy reports it as HIGH (CVE-2026-24049, CVSS 7.1, GHSA `wheel: Privilege Escalation or Arbitrary Code Execution via malicious wheel file unpacking`). Fix is `wheel>=0.46.2`.
- **Decision:** keep `wheel==0.45.1` in the runtime venv; do **not** force-bump or scrub it from the runtime image at this time. Suppress the finding via Trivy's `.trivyignore` (T9 owns ignore-file wiring) referencing this entry's short title.
- **Reason:** the exploit requires invoking `wheel unpack <attacker-controlled.whl>` against attacker-controlled input. Our runtime never invokes wheel — confirmed via `grep -rn "import wheel\|from wheel" --include="*.py" ./products ./seed` returning zero hits. `wheel` is a build-time package that rides along into the runtime venv because the canonical multi-stage Dockerfile copies `/opt/venv` verbatim from builder → runtime stage (lines 110-111 of `products/seed/backend/Dockerfile`). The attack surface is not exercised; patching the `wheel` version would require running `pip install -U wheel` in the builder, which is harmless but adds CI work for zero runtime gain. Force-scrubbing `wheel` via `pip uninstall -y wheel` in the builder stage right before the runtime copy is the right structural fix but lands at N=2 (when a second non-exercised build-time package surfaces the same shape; currently only `wheel` + `jaraco.context` qualify, and they share the same fix).
- **Scope:** all slim images built from `products/seed/backend/Dockerfile` or its slug+port copies — at time of filing: `seed`, `youtube-crawler`, and every other product since they share the canonical pattern. Trivy's `.trivyignore` should target `CVE-2026-24049` package-narrowed to `wheel`.
- **Revisit trigger:** **a second non-exercised build-time CVE surfaces** (third-party builder-stage package, not invoked at runtime) — at N=2 the structural fix is "scrub non-runtime packages from the builder→runtime copy" in the seed Dockerfile, with both entries flipping to FORMALIZED. OR **`wheel` becomes a runtime dep** (a future feature invokes `wheel unpack` for installer flows) — at that point the accept flips to refactor (force-bump and remove the catalog entry).
- **Recorded by:** `projects/trivy-prescan-2026-05-11/PROJECT.md` (2026-05-11) — Trivy pre-scan against the two currently-built slim images using `aquasec/trivy:0.49.1` + `--severity HIGH,CRITICAL` + `--ignore-unfixed` (T9 CI gate config bit-for-bit). 4 unique CVEs surfaced; 2 patched (`PyJWT 2.9.0 → 2.12.0`, `fastapi 0.115.0 → 0.115.5+` brings starlette ≥0.40.0), 2 accepted (this entry + `jaraco.context` sibling).

### `jaraco.context` CVE-2026-23949 carried in runtime venv (setuptools transitive; attack surface not exercised)

- **Subject:** `jaraco.context==5.3.0` ships in `/opt/venv` in every slim image (transitive of `setuptools`, which pip's bootstrap installs into the venv). Trivy reports it as HIGH (CVE-2026-23949, CVSS 8.6, GHSA "jaraco.context: Path traversal via malicious tar archives"). Fix is `jaraco.context>=6.1.0`.
- **Decision:** keep `jaraco.context==5.3.0` in the runtime venv; do **not** force-bump or scrub it. Suppress via Trivy's `.trivyignore` referencing this entry's short title.
- **Reason:** the exploit requires invoking `jaraco.context.tarball()` against attacker-controlled tar archives (the `tarball()` function is a context manager for extracting tarballs with `tarfile.extractall()`). Our runtime never invokes `jaraco.context` — confirmed via `grep -rn "import jaraco\|from jaraco" --include="*.py" ./products ./seed` returning zero hits. `jaraco.context` is pulled in transitively by `setuptools`, which we don't directly depend on at runtime either but which lives in the venv as part of pip's bootstrap. Same shape as the `wheel` entry above. Force-bumping `jaraco.context` requires either pinning it directly (adding a runtime requirement we don't actually use) or upgrading `setuptools` (which may break wheel-build compatibility for products with native deps like cryptography/psycopg2). The structural fix (scrub non-runtime packages from the builder→runtime copy) lands at N=2 alongside `wheel`.
- **Scope:** all slim images built from `products/seed/backend/Dockerfile` or its slug+port copies. Trivy's `.trivyignore` should target `CVE-2026-23949` package-narrowed to `jaraco.context`.
- **Revisit trigger:** **shared with `wheel` entry above** — at N=2 (which is now, with `wheel` + `jaraco.context`), the recurrence rule says formalize. But the formalization here is a Dockerfile change (add `pip uninstall -y wheel setuptools` or equivalent scrub step in the builder stage right before the venv copy), which is best landed as a single follow-up project, not inline. Both entries flip to FORMALIZED at that project's close. OR **`jaraco.context` becomes a runtime dep** (a future feature invokes `tarball()` for archive extraction flows) — at that point the accept flips to refactor.
- **Recorded by:** `projects/trivy-prescan-2026-05-11/PROJECT.md` (2026-05-11) — same scan that surfaced the `wheel` entry above.

---

## Entries from `mailing-wiring` Phase 2 (filed 2026-05-11)

> **RETIRED 2026-05-16 (`social-wiring-absorption` Wave 4).** The `mailing` product was consolidated into **`products/social-wiring/app/modules/email_marketing/`** and retired; the `mailing-wiring` project (Phases 0-2 ✅, Phases 3-5 superseded by the absorption) was never separately ledgered — a verbatim snapshot of its `PROJECT.md` + the closed proposal-eval set is preserved at `projects/social-wiring-absorption/.integration-holding/W4.0-preservation/`, and disposition is recorded in `project-history/ledger.ndjson` slug `social-wiring-absorption-wave4-teardown`. **These 4 entries are the durable substance of that incomplete project and MUST survive.** For live code, every `products/mailing/...` path below resolves to the absorbed `products/social-wiring/app/modules/email_marketing/...` module (`useSettings.ts`/`Equipe.tsx`/`Unsubscribe.tsx`/`routers/{lists,automations,analytics,ai}.py` and the GET-verify endpoint moved with the absorption); the decisions + revisit triggers remain valid as written. Treat the cited `products/mailing/...` and `products/mailing/projects/mailing-wiring/PROJECT.md` paths as historical provenance.

### Settings/verify `GET /api/settings/domains/{id}/verify` is mutation-shaped (idempotent re-verify)

- **Subject:** `useSettings.useVerifyDomain` hook performs `api.get(`/api/settings/domains/${id}/verify`)`, backend `routers/settings.py:48` GET endpoint triggers a domain DNS verification side effect.
- **Decision:** keep the GET verb; do not refactor to POST.
- **Reason:** domain verification is idempotent — re-running it any number of times produces the same outcome (DNS lookup against an external provider, mutation only happens if the verified state changes). The verb-quirk is a minor REST-purity divergence (mutations should be POST/PATCH), but the operation matches HTTP GET's safe/idempotent semantics in practice. Tag has `@limiter.limit` applied, so abuse is bounded. Refactoring would require frontend + backend + tests + downstream call sites (none currently); cost > benefit at N=1.
- **Scope:** `products/mailing/frontend/src/hooks/useSettings.ts::useVerifyDomain` + `products/mailing/backend/app/routers/settings.py:48` (GET `/api/settings/domains/{id}/verify`).
- **Revisit trigger:** **a second similar verb-quirk surfaces** (e.g. another `/verify` / `/refresh` / `/sync` endpoint in mailing or any other product using GET for a side-effect operation) — at N=2 the formalize is a seed-wide convention call (POST for any operation with side effects, regardless of idempotence) recorded in `KB § PATTERNS/backend/backend.md § HTTP verb conventions`. OR the verification gains non-idempotent behavior (e.g. logs a verification attempt audit row each call) — at that point the GET is wrong and refactor wins.
- **Recorded by:** `products/mailing/projects/mailing-wiring/PROJECT.md` Phase 0 §5.2.3 Q4 (2026-05-11), executed in Phase 2 (this entry).

### `Equipe.tsx` direct-fetch on seed `team` standard router (Pattern D — N=1 mailing page)

- **Subject:** `products/mailing/frontend/src/pages/Equipe.tsx` calls `api.get`/`api.post`/`api.delete` directly against `/api/team*` endpoints (5 callsites). Does not consume a `useTeam` hook.
- **Decision:** keep direct-fetch shape; do not extract a `useTeam` hook for mailing.
- **Reason:** the `team` endpoints come from the seed `team` standard router (mounted via `create_product_app(..., standard_routers=["team"])`); they are not mailing-product-owned. No other mailing page calls them, so a per-product hook wrapper would be code-for-the-sake-of-code. PF and ERP made the same call at their wiring phase (Pattern D accept). When the `team` surface needs typed hook ergonomics, the right destination is `seed/frontend/src/hooks/useTeam.ts` (cross-product seed hook), not per-product hooks.
- **Scope:** `products/mailing/frontend/src/pages/Equipe.tsx` only. Other mailing pages use product-owned hooks.
- **Revisit trigger:** **seed ships `useTeam` cross-product hooks** (e.g. as part of `seed/frontend/src/hooks/`) — at that point Equipe.tsx adopts the seed hook in a mechanical refactor and this entry retires. OR **a second mailing page needs team data** — at N=2 (within mailing) a product-local `useTeam.ts` hook becomes worth the wrap.
- **Recorded by:** `products/mailing/projects/mailing-wiring/PROJECT.md` Phase 0 §5.2.3 Q-equipe (2026-05-11), executed in Phase 2 (this entry).

### `Unsubscribe.tsx` direct-fetch on public `/api/unsubscribe/{token}` (Pattern D — public route, no auth)

- **Subject:** `products/mailing/frontend/src/pages/Unsubscribe.tsx` calls `api.get`/`api.post` directly against `/api/unsubscribe/{token}` (1 GET + 1 POST callsite). Does not consume a hook.
- **Decision:** keep direct-fetch shape; do not extract a `useUnsubscribe` hook.
- **Reason:** the unsubscribe surface is a public route (no auth, no org scoping) — it bypasses every standard frontend auth interceptor that hooks rely on. The page is also single-use: a recipient lands on it once, confirms, and never returns. A hook wrapping a one-off public POST adds React-Query plumbing (cache key, invalidation, retry) for a request that doesn't benefit from any of it. Same shape as Equipe.tsx Pattern D (seed-owned endpoints OR public routes → direct-fetch ok).
- **Scope:** `products/mailing/frontend/src/pages/Unsubscribe.tsx` only.
- **Revisit trigger:** **a second public unsubscribe-shaped page appears** (e.g. preference center, re-subscribe confirmation, double-opt-in landing) — at N=2 within mailing the public-route pattern justifies a `useUnsubscribeAPI` hook OR a thin `publicAPI` wrapper at seed. OR the unsubscribe operation gains cache-relevant state (e.g. the recipient sees their previous preferences) — at that point the hook ergonomics pay off.
- **Recorded by:** `products/mailing/projects/mailing-wiring/PROJECT.md` Phase 0 §5.2.3 Q-unsubscribe (2026-05-11), executed in Phase 2 (this entry).

### Mailing orphan routes (5) kept for planned UI work (scaffolded-ahead-of-UI)

- **Subject:** five mailing backend routes ship without a frontend caller — `PATCH /api/lists/{id}`, `PATCH /api/automations/{id}`, `PATCH /api/automations/{automation_id}/steps/{step_id}`, `POST /api/automations/{automation_id}/steps/reorder`, `DELETE /api/lists/{list_id}/members`, `GET /api/analytics/campaigns/{campaign_id}`, `POST /api/ai/campaigns/{id}/debrief/send`. All have backend tests; all have service-layer org-scoping (M-1 hardened in Phase 1).
- **Decision:** keep all orphan routes; do not delete.
- **Reason:** each route maps to a planned UI feature (lists rename, automations rename, step-edit drawer, step-reorder drag-and-drop, list member removal, per-campaign analytics drilldown, manual debrief send). Deleting them now means re-adding identical code when the UI lands — pure churn. The routes are correctly org-scoped (Phase 1 M-1 hardening) and tested; the only "cost" of keeping them is a few unused public-API entries on the OpenAPI schema, which is information rather than risk. Symmetric with the orphan-hook accept rationale: backend route + future-UI > delete-and-readd-cycle.
- **Scope:** `products/mailing/backend/app/routers/{lists,automations,analytics,ai}.py` (the 6 routes named above).
- **Revisit trigger:** **a route stays orphan for 6 months past mailing's first GA cut** (no UI feature lands consuming it) → cleanup pass deletes it OR documents the deferred feature explicitly. OR **the UI feature design lands and the route shape doesn't match** → adjust route + re-add corresponding hook (Phase 2 already deleted 5 test-only AI hooks; the 6 above are the symmetric backend keep). OR **the recurrence rule fires** (a 6th product accumulates >5 orphan routes from the same "scaffolded UI lagging" cause) → file a methodology project on the scaffold-ahead-of-UI pattern.
- **Recorded by:** `products/mailing/projects/mailing-wiring/PROJECT.md` Phase 0 §5.2.3 Q2 (2026-05-11), executed in Phase 2 (this entry).

---

## Entries from `social-wiring-absorption` Wave 2 (filed 2026-05-16)

### social-wiring keeps 4 validated adapter subpackages product-local (seed-convergence deferred) — N=1

`products/social-wiring/backend/app/services/{calendar,meta,routing,drive_api}/` + `credential_store.py` are kept **product-local**, NOT converged onto the Wave-1 reconciled seed `noctusai_lib.integrations.{google_calendar,google_maps,google_drive,meta}` + `security.token_store`, even though the absorption's goal is "consume the seed".

**Rationale.** Two independent engineers (W2.5, W2.5b) proved (zero-edit, surfaced) the workspace↔seed contract gap is **4 coupling axes**: credential-read (bridgeable) · OAuth credential-WRITE path (router `store.upsert(provider=…)`; seed has no provider-constant/write seam — OAuth delegated to `security.oauth`) · `isinstance` adapter-type labeling (seed classes ≠ workspace classes) · **Meta method-set capability gap** (Wave-1.E4 seed Meta dropped `me()`/`get_page()` — a dropped capability, not a rename). The 69-test oracle asserts `app.services.meta` *internals*, so deleting the subpackages destroys the regression oracle. Forcing convergence now would lose validated behavior + the oracle, for a product that is **already real-world-functional** with these validated local implementations (the user's explicit "deliver functional in real world" + "theirs validated" requirements). N=1 (only social-wiring) — below the seed-absorb threshold; the subpackages' own design docs already say "absorb at N=2".

**Named destination (NOT a silent fork).** Follow-up project `projects/seed-adapter-convergence/` — gated on the seed FIRST shipping: Meta `me()`/`get_page()` capability + a `credential_store=`-convenience factory path + an OAuth-credential-WRITE seam (provider-constant + callback-write contract). Recurrence flips this `accept`→`formalize` the moment a 2nd product needs the same convergence. Verify-the-seed-ships-it 4th-shape (consumer-method-set + write-path compat) is the codification that would have caught the Wave-1.E4 under-ship at reconcile time.

> **UPDATE 2026-05-17 (`seed-adapter-convergence` executed — partial-convergence landing; project closed).** The 3 gating seed prerequisites are now **SHIPPED** (durable record: `project-history/ledger.ndjson` slug `seed-adapter-convergence`):
> - **Prereq-1 (Meta capability gap) — CLOSED.** `me()` + `get_page(page_id)` added to the seed `MetaAdapter` Protocol + `MetaOAuthAdapter` + `FakeMetaAdapter` (`noctusai_lib/integrations/meta/{types,oauth_adapter,fake_adapter}.py`); `auth_mode` was already shipped pre-this-session. Colocated tests in `seed/lib/backend/tests/integrations/meta/test_meta_integration.py`.
> - **Prereq-2 (`credential_store=` convenience) — CLOSED.** `get_calendar_adapter(credential_store=, oauth_client_id=, oauth_client_secret=)` + `get_meta_adapter(credential_store=)` now accept the seed `token_store.CredentialStore` directly and build the resolver internally.
> - **Prereq-3 (OAuth credential-WRITE seam) — CLOSED.** New seed module `noctusai_lib/integrations/credential_resolvers.py`: canonical provider constants (`CALENDAR_PROVIDER`/`META_PROVIDER`/`DRIVE_PROVIDER`), `CredentialStore`-backed resolver bridges (`CredentialStoreCalendarResolver`/`CredentialStoreMetaResolver`), and `make_token_persisting_callback(store, …)` for `oauth_router(on_callback=)`. `channel_id`/`channel_title`/`scopes` ride the `token_store` `metadata` dict (no schema change). Colocated tests `seed/lib/backend/tests/integrations/test_credential_resolvers.py`.
>
> **Convergence outcome per axis (triage at decision time):**
> - **Routing — `[F]` FORMALIZED.** `products/social-wiring/backend/app/services/routing/` is now a thin re-export shim over `noctusai_lib.integrations.google_maps` (value objects + both adapters were byte-identical to the seed; `isinstance` checks stay transparent because consumers get the *same* seed classes). 4 product-local files deleted (`mappers.py`/`google_maps_adapter.py`/`static_adapter.py`/`types.py`, ~209 LoC); oracle repointed to the seed seam; 73/73 green.
> - **Calendar + Meta — seed-enabled, consumer-migration RESIDUAL.** The seed now *supports* the convergence (prereqs landed; seed `CalendarAdapter` is a superset of the product Protocol, value objects identical; Meta gap closed). The remaining work is the consumer-side rewrite of `calendar_router.py`/`meta_router.py` (migrate their bespoke OAuth dance to seed `oauth_router` + `make_token_persisting_callback`; swap product `CredentialStore`→seed `token_store`). Not forced this session because it is entangled with the drive non-fit (next bullet) and would, if rushed, hit exactly the "destroy validated behavior + 69-test oracle" failure the W2.5/W2.5b engineers proved. **Destination:** when a 2nd product needs OAuth-token-at-rest the recurrence rule fires `accept`→`formalize`; until then this is a consumer-side residual, seed side complete.
> - **Drive — `[A]` PERMANENT non-fit (ACCEPTED, not deferred).** The product `DriveAdapter` Protocol is **sync** (`def search`/`def read_content`/`def get_file`/`def list_recent`, consumed via `asyncio.to_thread(...)`); the seed `google_drive.DriveReader` is **async** with different method names (`read_file` vs `read_content`) + return types (`DriveSearchHit` vs `DriveFile`). Forcing convergence flips sync↔async across every consumer call site — destroys validated behavior. `products/social-wiring/backend/app/services/drive_api/` stays product-local. `drive_api/oauth_adapter.py` also imports `CALENDAR_PROVIDER`/`_strip_tz` from `calendar/oauth_adapter.py` — this internal coupling is *why* calendar's internals can't be deleted while drive is product-local. **Revisit trigger:** a seed `google_drive` sync façade (or a 2nd product needing the sync drive shape) — not on the current roadmap.
> - **`credential_store.py` — retained.** Cannot be retired while drive (non-fit) + youtube (`google_auth_oauthlib` pre-existing-broken, out of scope) still consume it. Retire when calendar/meta consumers migrate AND drive is resolved.
>
> **Net:** seed prerequisites fully formalized + routing converged (zero-risk, complete); calendar/meta consumer-migration is a bounded consumer-side residual with a concrete destination; drive is a documented permanent non-fit. This entry stays `accept` (not yet fully `formalized`) because the product-local calendar/meta/drive + `credential_store.py` persist — but the *seed under-ship that blocked it is closed*.

### 9 `scripts/` carve-outs retain shell (MCP runtime structurally unavailable)

- **Subject:** `KB § PATTERNS/architect/mcp-first-scripts.md` mandates new automation default to a `noctus.dev.*` MCP tool. 16 absorbable scripts were ported + deleted 2026-05-18 (`scripts-mcp-absorption`). 9 remain shell.
- **Decision `[A]`:** these 10 stay shell, NOT absorbed: `pre-commit` + `merge-kb-counts.sh` (`[carve:hook]` ×2 — `pre-commit` is a thin dispatcher, logic IS in `noctus.dev.*`; `merge-kb-counts.sh` is a git MERGE DRIVER invoked by git itself via `.gitattributes merge=kb-counts` to regenerate auto-derived kb-counts blocks on rebase/merge — git plumbing with no agent-facing surface, cf. `KB § PATTERNS/common/auto-generated-merge-drivers.md`) · `install-hooks.sh` · `setup.sh` · `first-time-setup.sh` · `bootstrap-worktree.sh` · `bootstrap-seed-workspace.sh` · `build-init-local-db.sh` (`[carve:bootstrap]` ×6 — run *before* the venv the MCP lives in exists; they *create* it) · `build-base-images.sh` + `build-and-push.sh` (`[carve:docker]` ×2 — whole body is `docker build`/push plumbing of the seed base + product images; a Python wrapper would only shell out. `build-and-push.sh` relocated from `projects/production-deploy-migration/` → `scripts/infra/` 2026-05-24: a permanent CI surface MUST live outside `projects/` — it broke CI with exit 127 when that project was archived; durable-refs gate now prevents the class).
- **Reason:** formalize/refactor are structurally impossible, not merely costly. Git invokes `.git/hooks/*` as a shell process with no Python runtime guarantee; bootstrap scripts are the chicken-and-egg that builds the interpreter the toolkit imports from; the docker-orchestration body has zero extractable logic (absorbing yields negative value — a shell-out wrapper). `pre-commit`'s *logic* WAS formalized (every step → `cli.py --<flag>`); only the unavoidable shell entry is accepted.
- **Scope:** the 9 files above, each carrying its `[carve:*]` row in `KB § PATTERNS/architect/mcp-first-scripts.md` §3 (the manifest is the keeper-parsed single source of truth; this entry is its 1:1 rationale pairing).
- **Revisit trigger:** (a) a hook runner that can invoke MCP directly (flips `[carve:hook]`→formalize); (b) `build-base-images.sh` grows real logic beyond `docker build` plumbing (flips `[carve:docker]`→absorb); (c) the bootstrap sequence gains a pre-existing Python runtime it can rely on (flips `[carve:bootstrap]`). Any *new* `scripts/*.{sh,py}` without a manifest row trips `check_new_script_lacks_mcp_analog` (warning) — the keeper enforces the rule going forward.
- **Recorded by:** `scripts-mcp-absorption` Phase 5 (2026-05-18, architect + 5 parallel engineers MOLE/ANALYSIS/LEDGER/KBSYNC/CODEGEN).

### 9a `claude-guard-primary-write.py` retains shell (`[carve:hook]`, 2026-08-19)

- **Subject:** the self-branching WRITE gate needs a `PreToolUse` hook entry point (`KB § PATTERNS/common/self-branching-mode.md` §11). Under the MCP-first rule a new `scripts/**/*.py` defaults to a `noctus.dev.*` tool.
- **Decision `[A]`:** `scripts/hooks/claude-guard-primary-write.py` stays a script — same `[carve:hook]` bucket as `pre-commit`, and for the same structural reason one step further out.
- **Reason:** the harness invokes the hook as a subprocess before EVERY `Bash`/`Edit`/`Write` call. The MCP server is not reachable from that path, and even if it were, the round-trip is unaffordable: the whole gate has to fit in tens of milliseconds or it becomes the thing someone removes. Importing `compliance.py` alone costs ~0.27 s — a quarter-second tax on every command in every session. So the script is a **protocol adapter only**: it reads the hook's JSON, calls one function, prints one decision. Every bit of judgement lives in `mcp/noctusai/tools/noctus/dev/primary_write_guard.py` — inside the toolkit, stdlib-only, imported BY PATH rather than as a package precisely to keep that cost near zero — and `compliance.py` imports `SHARED_BRANCHES` + the ledger allowlist FROM it, so the two gates cannot drift apart. This is `pre-commit`'s shape exactly: the logic is formalized, only the unavoidable entry point is accepted.
- **Scope:** the one file, carrying its `[carve:hook]` row in `KB § PATTERNS/architect/mcp-first-scripts.md` §3.
- **Revisit trigger:** a hook runner that can invoke MCP directly and cheaply (the same trigger as entry 9's `[carve:hook]` — it would flip both at once).
- **Recorded by:** `guard-primary-checkout-writes` (2026-08-19), after the primary-checkout slip recurred twice in one session with only the commit-time keeper installed.

## Entries from `schedule-recurrence-window-gap` Phase 0 (filed 2026-05-18)

### 9b `claude-guard-test-seams.py` retains shell (`[carve:hook]`, 2026-09-02)

- **Divergence:** a second `scripts/hooks/*.py` PreToolUse adapter, for the
  write-time half of the no-self-monkeypatch rule.
- **Decision `[A]`:** stays a script, same `[carve:hook]` bucket and the same
  structural reason as 9a — the harness invokes it as a process in the
  pre-tool path on every `Edit`/`Write`; the MCP server is not reachable
  there and a round-trip would not fit the budget. The DECISION logic lives
  in the toolkit (`tools/noctus/dev/test_seam_guard.py`, sharing
  `self_patch_predicate.py` with the `check_no_self_monkeypatch` keeper), so
  only the protocol adapter is shell-shaped.
- **Why a SECOND adapter rather than a branch inside 9a:** branch isolation
  and test-seam enforcement must fail independently. A crash in one must not
  disable the other, and both fail OPEN by design — a guard that raises must
  never become a guard that blocks all work.
- **Scope:** the one file, carrying its `[carve:hook]` row in
  `KB § PATTERNS/architect/mcp-first-scripts.md` §3.
- **Revisit trigger:** identical to 9a's (a) — a hook runner able to invoke
  MCP directly flips this to formalize.

### Recurrence-expansion stays product-local across daily-life/erp/PF — domain-divergent, no `N≥3` unifiable contract

- **Subject:** §3a seed-first audit of the daily-life recurring-events gap asked whether windowed recurrence-expansion is `N≥3`-duplicated → a seed primitive (`noctusai_lib.domain.scheduling`).
- **Decision `[A]`:** keep recurrence-expansion product-local. daily-life `schedule_service.expandir_recorrencias` (calendar events → in-memory occurrences clipped to a read-window) vs erp `recorrencia_service` (generates+persists financial rent rows) vs PF `recorrentes_service` (financial-transaction recurrence). Same word, **three different domains**: in-memory-read-clip vs persist-financial-rows; period vocabularies even differ (daily-life `diario/semanal/mensal/anual` vs PF `semanal/quinzenal/mensal/bimestral/…`).
- **Reason:** no `N≥3` *unifiable* contract — a shared "recurrence engine" abstraction would be a wrong abstraction (forced unification of divergent domains). Recurrence rule (`N≥3 ⇒ MUST formalize`) does not fire; `[R]` N/A (each is correct for its domain). `[A]` is the correct landing, not a deferral. (User-preference is to avoid `[A]` when `[F]/[R]` is genuinely possible — here it is not without harm.)
- **Scope:** the three services above. The narrow shared sliver (period→`relativedelta`) is too small + vocabulary-divergent to extract.
- **Revisit trigger:** a 3rd+ product needs *calendar-style window-expansion* (same contract as daily-life's, not financial-posting) → re-triage toward `[F]` a `noctusai_lib.domain.scheduling.recurrence` window-expand primitive. (Out-of-scope note: a broad cross-product scan during this audit re-surfaced general platform helper-duplication — `audit_hook` `_get_engine_and_factory`/`_noop_writer` ×5 — pre-existing, belongs to the standing absorption queue, not this entry.)
- **Recorded by:** `schedule-recurrence-window-gap` Phase 0 (2026-05-18, architect; user-delegated decision).

## Entries from `erp-imobiliario-test-baseline-recovery` (filed 2026-05-20)

### `noctus.dev.scan_mock_predicate_skew` Stage-4 keeper — Stage-3 observation only, intra-product N=9 ¬ cross-product

- **Subject:** Engineer G's baseline-recovery surfaced N=9 mock-skew clusters in ERP (test fixtures missing fields that production queries `.eq()`/`.gte()`/`.is_()` filter on, so chained predicates returned empty → 9 tests failed). G surfaced a candidate `noctus.dev.scan_mock_predicate_skew` detector that would libcst-walk routers/services to extract predicate-columns, then diff against `set_table_data("<table>", [...])` fixture row keys to flag skew before tests run.
- **Decision `[A]`:** Stage-3 observation captured in `KB § PATTERNS/compliance/testing.md` (∧ this catalog entry); **Stage-4 keeper deferred** — N=9 inside ONE product is intra-product debt accumulation, not the cross-product recurrence that justifies a deterministic platform-wide detector. The recurrence rule (`KB § PATTERNS/architect/project-execution.md § 2.7`) reads cross-consumer counts; one product's quirks are not yet cross-cutting evidence.
- **Reason:** building a libcst predicate-extractor scoped to test fixtures is ~200-300 LoC + cross-file static analysis, justified only when the same pattern surfaces in a second product. G's fixes drained the existing 9 instances → the recurrence pressure is now gone in ERP. Premature Stage-4 = code that runs forever for one historical accumulation. `[F]` premature; `[R]` N/A (the fix-set already shipped); `[A]` is the correct landing per "Accept when formalize+refactor are wrong outcomes today."
- **Scope:** `noctus.dev.scan_*` MCP toolkit (mcp/noctusai/tools/noctus/dev/). No code change today; observation lives in `KB § PATTERNS/compliance/testing.md`.
- **Revisit trigger:** a second product's recovery / baseline-drain surfaces ≥3 mock-skew failures with the same root-cause shape (fixture rows missing predicate columns vs production `.eq()`/`.gte()`/`.is_()` filters). At that point cross-product recurrence is confirmed → flip `[A]→[F]` and build `noctus.dev.scan_mock_predicate_skew`. The libcst infrastructure to do this already exists (`noctus.dev.scan_outlined` + `scan_pydantic_model_shapes` patterns). Pre-emptive scan now during next platform-wide test pass: `pytest --collect-only` across all products; if mock-skew failures appear elsewhere, that's the trigger.
- **Recorded by:** `erp-imobiliario-test-baseline-recovery` close-out (2026-05-20, architect + Engineer G).

### core's `docker-compose.yml` control-plane `docker.sock` — FORMALIZED into the propagate generator [A]→[F] (2026-05-24)

- **Divergence:** `products/core/docker-compose.yml` carries a control-plane mount — `/var/run/docker.sock:/var/run/docker.sock:ro` — that the canonical `products/seed/docker-compose.yml` deliberately lacks (core alone operates the fleet via `noctusai_lib.domain.fleet_control`; commit `336e7657`).
- **Why it could NOT stay an accept:** the pre-commit propagate gate (`cli --propagate both --check`) fires on **any staged seed-docker change**. The first-pass workaround — re-propagate then `git checkout -- products/core/docker-compose.yml` — **cannot survive a seed Dockerfile commit** (e.g. the npm-10 tarball fix): the gate sees core's compose `stale` and aborts. The safety net firing forced the formalize (per *"safety nets capture failures → methodology evolves"*).
- **Formalized fix:** `propagate.py` now has a slug-keyed compose-extras hook — `_C_VOLUME_EXTRA = {"core": _C_CORE_DOCKER_SOCK}` injected after the seed-lib FE `node_modules` anchor in `_render_compose` (mirrors the Dockerfile `_D_EXTRA` map). Core's compose now **regenerates WITH the socket** (byte-identical to the committed file → `in-sync`), so `propagate composes` is safe to run blindly and the drift gate passes. Guarded by `test_compose_core_gets_docker_sock_others_dont` (core gets it once; every other product gets none).
- **To add another product's control-plane mount:** add a slug entry to `_C_VOLUME_EXTRA` (+ extend the test). No hand-restore, no accept entry.
- **Recorded by:** `container-first-codify-and-absorb-ke` P4 (2026-05-23 surfaced → 2026-05-24 formalized) — the npm-10 seed-Dockerfile commit tripped the gate and converted this from accept to formalize.

## Entries from `harness-agents-skills` (filed 2026-05-25)

### Specialist personas live in TWO homes — agno charters + `.claude/agents` (two runtimes) — [A]

- **Divergence:** the senior-specialist personas (architect / security / code-reviewer / backend / frontend / …) exist as BOTH `dev_team/src/dev_team/charters/*.md` (the agno multi-agent runtime) AND `.claude/agents/*.md` (the Claude Code harness runtime). N=2 duplication of persona text.
- **Why accept (not formalize):** the two are DIFFERENT execution substrates — agno (a paid product, `noctus.team.*`, collaborate-mode cross-talk) vs the Claude Code harness (the day-to-day branch-isolated dispatch: read-only advisors + worktree executors). Neither can `import` the other's format. The shared core (the universal §1 rules) already lives once in `CLAUDE.md` / `dev_team/.../charters/shared.md`; only the thin role-specific layer is dual-authored. Each `.claude/agents/*.md` carries an `Adapted from dev_team/.../X.md` provenance line so the pair is greppable.
- **Bound:** a THIRD consumer of the same persona, OR role-text drift between the two homes, flips this to [F] — extract a shared persona-core both runtimes consume (plan option A2).
- **Decision:** A3 of the `harness-agents-skills` plan, user-approved 2026-05-25.

### Three CLAUDE.md backup poles tracked in-repo at `backup/` — [A]

- **Divergence:** `backup/CLAUDE.md.bak` (verbose original) + `CLAUDE-Aggressive.md.bak` + `CLAUDE-Moderate.md.bak` live at repo root — unusual for a docs tree.
- **Why accept:** they are the rollback + comparison poles for the v4.0 router synthesis. `KB § PATTERNS/common/claude-md-router-discipline.md` references them as the rollback mechanism (`cp backup/<pole> CLAUDE.md`). User-requested for safe reversibility (2026-05-25). Revisit at integration — keep as durable rollback OR gitignore to local-only.

### `harness-agents-skills` shipped commit-per-phase, not the single-commit first floated — [A]

- The user initially asked for one squashed commit (easy revert), then revised mid-build to **commit-per-phase** (more auditable). Per-phase won; the parked `feat/harness-agents-skills` checkpoint + a `git revert` of the phase range preserves reversibility without losing the audit trail. Recorded so the deviation from the single-commit ask is non-silent.

## Entries from `p-studio-absorption-rollout` (filed 2026-08-13)

### p-studio's `src/components/ui.tsx` re-implements 22 canonical organs — [A], bounded to the absorption

- **Divergence:** `products/p-studio/frontend/src/components/ui.tsx` hand-rolls 22 UI primitives (Button, Input, Textarea, Select, Label, Field, Checkbox, Card, StatCard, Badge, StatusBadge, Modal, Spinner, EmptyState, ErroBox, PageHeader, Table, Th, Td, THead, TBody, BotaoExcluir). Every one shadows a canonical `@noctusai/lib` organ, so `check_canonical_organ_consumption` fires the moment p-studio is scanned. The single-file shape was itself a deliberate reaction in the originating workspace to a Lovable prototype that installed 47 shadcn components and used five.
- **Why accept (not formalize) TODAY:** the product arrived from outside noc and the absorption's job is to port + containerize it. Folding the organ swap into the same change would (a) balloon a reviewable diff into an unreviewable one, and (b) put a large FE refactor *in front of* the container gate, which is what unblocks the public URL the whole project exists for. `KB § GUIDES/absorb-seed-workspace.md` Gate 9 is explicit that containerization is the gate, not a final polish.
- **Not a permanent carve-out.** This is the epoch-delta the absorption guide predicts — the measurable distance the platform moved while this product grew elsewhere — and epoch delta is *paid*, not amnestied.
- **Bound / revisit trigger:** roadmap `project-history/roadmaps/p-studio-2026-08.md` **T4** — the swap starts once M4 (prod promote) is ✅ and the product has one week of prod uptime with no rollback. If p-studio ships a *new* screen before T4 fires, that screen consumes canonical organs directly; this entry never licenses growing the local set.
- **Explicitly NOT covered by this entry:** weakening, silencing, or scoping-out `check_canonical_organ_consumption` itself. The keeper stays as-is and is expected to fire; this entry is the rationale a reader finds when it does.
- **Recorded by:** tech-lead, `p-studio-absorption-rollout` slice B close-out (2026-08-13). Surfaced by the dispatched frontend engineer, decided by the tech-lead — the engineer correctly declined to fix it in-flight.

## Cross-references

- **The triage rule:** `KB § 01-PHILOSOPHY.md § Triage at decision time`.
- **The recurrence rule (drives when triage fires):** `KB § PATTERNS/architect/project-execution.md § 2.7 The recurrence rule`.
- **CLAUDE.md §1 bullet:** *"Triage at decision time — formalize / refactor / accept-with-rationale"*.
