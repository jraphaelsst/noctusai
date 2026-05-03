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
`KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`. Both
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

### ERP metas digest does NOT use `noctusai_lib.domain.digest`
- **Subject:** `KB § 04-SHARED-LIBRARY.md § domain/digest` shared library used by `core` audit-digest, `personal-finance` monthly narrative, `daily-life` weekly review, `mailing` campaign debrief — but NOT ERP metas digest.
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
- **Decision:** all three detector modules retain `import ast` and node-level walks; do NOT migrate to `noctusai_outline_python`.
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
- **Recorded by:** `KB § PATTERNS/testing.md § Schema validation`; per-product conftest comments; reconciliation projects.

### `check_no_self_monkeypatch` severity stays `warning` (not `high`) until count = 0 per product
- **Subject:** keeper detector `check_no_self_monkeypatch` severity calibration.
- **Decision:** severity is `warning` (not `high`) until each product's count reaches zero; ratchets to `high` per-product as cleanups land.
- **Reason:** first run flagged 420 sites across 7 products; tanking the score from 100 → 0 was unhelpful. Per-product ratchet preserves CI signal while letting cleanups happen incrementally.
- **Scope:** `mcp/noctusai/tools/compliance.py::_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS`.
- **Revisit trigger:** a product reaches 0 → flip to `high` for that product (already done for `therapy-platform`). All products at 0 → flip repo-wide; remove the carve-out.
- **Recorded by:** `KB § PATTERNS/testing.md § Severity ratchet`.

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
- **Scope:** `products/core/backend/app/services/stripe_service.py`; `KB § PATTERNS/webhook-signatures.md § Pattern 4`.
- **Revisit trigger:** Stripe SDK changes verification API in a way that breaks our integration → re-evaluate.
- **Recorded by:** `webhook-hmac-consolidation/PROJECT.md`; `KB § PATTERNS/webhook-signatures.md`.

### Webhook helpers accept unsigned payloads with WARNING when secret unset
- **Subject:** development-environment convenience for `verify_hmac_*` / Svix helpers.
- **Decision:** when a webhook secret env var is unset, accept the payload with a structured WARNING log instead of rejecting.
- **Reason:** dev environments often run the bot without the real provider configured; failing closed would block local testing. CI/prod must set the secret; the WARNING surfaces the unsafe state observably.
- **Scope:** consumer-side pattern (e.g. `products/mailing/backend/app/routers/webhooks.py`); documented as the universal rule in `KB § PATTERNS/webhook-signatures.md § Universal rules`.
- **Revisit trigger:** a production deploy ever runs without the secret AND processes traffic — at that point the WARNING wasn't loud enough; tighten to a startup check / fail-fast in production.
- **Recorded by:** `KB § PATTERNS/webhook-signatures.md`.

### MCP toolkit retains `requirements.txt` alongside `pyproject.toml`
- **Subject:** `mcp/noctusai/` packaging — both `requirements.txt` and `pyproject.toml` exist with overlapping dep lists.
- **Decision:** keep both; `pyproject.toml` is canonical, `requirements.txt` is the back-compat path.
- **Reason:** the existing `-e ../../seed/backend/lib` editable install of the platform shared lib is set up via `requirements.txt`. Replicating editable installs from a sibling path inside `pyproject.toml` is clunky (relative-path PEP-660 installs work but require `[tool.uv]` or similar opinionated tooling). The duplication is small (~3 lines); the pain of converting is large.
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

### `send_message` exists in ERP and therapy with different transports (N=2 accept-with-rationale)
- **Subject:** name `send_message` collides across products but the implementations target different transports.
- **Decision:** ERP's `send_message` is WAHA (WhatsApp HTTP API); therapy's `send_message` is in-app messaging. Don't consolidate.
- **Reason:** different domains, different transports, different consent / LGPD rules. The name match is coincidental; the implementations have nothing in common worth absorbing. The N=2 → triage discipline forces this to be an explicit decision rather than silent.
- **Scope:** `products/erp-imobiliario/backend/app/services/whatsapp_service.py`; `products/therapy-platform/backend/app/services/messaging_service.py`.
- **Revisit trigger:** a third product adds a `send_message` of either shape — the recurrence rule (N=3 → MUST formalize) flips this to formalize.
- **Recorded by:** `execution-workflow-codequality-rollout` Phase 0 (closed).

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
- **Scope:** `seed/backend/lib/noctusai_lib/security/webhook_signatures.py`.
- **Revisit trigger:** the user pulls the `whatsapp-google-scheduling` Alphabet/Google webhook findings into this repo, OR a NoctusAI product gains an inbound Google API webhook integration — whichever comes first. Open `webhook-alphabet-scheme-port` then.
- **Recorded by:** `webhook-hmac-consolidation/PROJECT.md` §7 Q1 (2026-05-03).

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
   `# accept-with-rationale: <short-title> in KB § PATTERNS/accept-with-rationale.md`.
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

---

## Cross-references

- **The triage rule:** `KB § 01-PHILOSOPHY.md § Triage at decision time`.
- **The recurrence rule (drives when triage fires):** `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`.
- **CLAUDE.md §1 bullet:** *"Triage at decision time — formalize / refactor / accept-with-rationale"*.
