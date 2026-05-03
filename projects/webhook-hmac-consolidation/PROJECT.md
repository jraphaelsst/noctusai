# Webhook HMAC Consolidation — Verify-Before-Expensive + Seed-Lib Absorption

> **This is a living document, not a rigid checklist.**
> Filed 2026-05-02 mid-session after a different-repo agent flagged
> HMAC + DoS concerns on the user's `whatsapp-google-scheduling`
> project (scoped there to Meta + Alphabet APIs). The user asked
> for that learning to land here too as platform-wide protection.
> The current grep audit found N=2 products with their own
> per-product HMAC verification — recurrence-rule fire (`KB §
> PATTERNS/project-execution.md § 2.7` → N=2 means triage time).
>
> **Status: Concept — interrogation pending.** §6 phases are
> drafted from the in-session audit but NOT yet user-confirmed;
> the open questions in §7 must resolve before Phase 0 starts.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-02
- **Status:** Phase 1.a ✅ shipped 2026-05-02 by commit `e1ba4e3` (parallel agent — cross-pollination from `whatsapp-google-scheduling` repo). Phase 1.b + Phase 2 still open. See §11 for the review of what shipped and what's still missing.
- **Owner / stakeholders:** Raphael · Claude Opus 4.7 (drafting agent) · future zero-context execution agent · cross-pollination from the user's `whatsapp-google-scheduling` repo (Meta + Alphabet API hardening lessons inbound)
- **Related docs:** `CLAUDE.md § Engineering Philosophy § The recurrence rule` (drives why this is its own project at N=2); `KB § PATTERNS/backend.md` (where the FastAPI dependency seam guidance lives); `KB § 04-SHARED-LIBRARY.md` (catalog target — `noctusai_lib.security.webhooks`); `KB § PATTERNS/seed-lib-layout.md § 6-layer model` (decides which layer the helper lives in — `integrations/` vs new `security/`); `KB § PATTERNS/lgpd.md` (signed payloads with PII trigger LGPD-first review); `products/erp-imobiliario/backend/app/webhook_utils.py` (existing helper — migration source); `products/erp-imobiliario/backend/app/routers/{assinaturas,meta_api,whatsapp_webhook}.py` (3 inbound consumers); `products/core/backend/app/services/stripe_service.py` (Stripe SDK — carve-out adopter); `products/core/backend/app/services/webhook_delivery.py` (outbound signer — different shape, may also absorb).
- **Project slug:** `webhook-hmac-consolidation` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

A different-repo agent working on the user's
`whatsapp-google-scheduling` project (Meta + Alphabet API
integrations, scoped there) flagged HMAC verification as a
load-bearing security control, with two distinct concerns:

1. **Forgery / tampering / replay** — without HMAC, anyone can
   fabricate webhook events. With naive HMAC (no timestamp guard,
   no constant-time compare), replay and timing attacks remain
   open.
2. **DoS / amplification** — webhook endpoints often run
   expensive downstream work (DB writes, notifications, audit
   logs, AI calls, webhook re-dispatch). An attacker who can
   bypass or precede the HMAC check forces that work for
   nothing. The mitigation is a layered cheap-first gate:
   max-body-size → rate-limit → HMAC verify → expensive work.

The user asked for that learning to land in this monorepo as
well, since: (a) we will eventually merge meta+alphabet
integration work from the sibling repo, and (b) the existing
NoctusAI codebase already has webhook surface that's
inconsistently hardened.

**Audit findings from the in-session grep (2026-05-02):**

| Location | Direction | Pattern | Gap? |
|---|---|---|---|
| `products/erp-imobiliario/backend/app/webhook_utils.py` | inbound | `verify_hmac_sha256(body, signature, secret)` using `hmac.compare_digest`. Used by 3 routers: `assinaturas.py`, `meta_api.py`, `whatsapp_webhook.py` (Meta `X-Hub-Signature-256`). | No timestamp / replay guard; not in seed-lib (per-product helper). |
| `products/core/backend/app/routers/billing.py` + `services/stripe_service.py` | inbound | Stripe SDK's `construct_webhook_event(payload, sig_header)` — handles HMAC + timestamp internally (5-min tolerance). | None — Stripe SDK is the canonical verifier; carve-out. |
| `products/core/backend/app/services/webhook_delivery.py` | outbound | `hmac.new(...)` to SIGN outbound deliveries to org-registered endpoints. | Different shape (signer not verifier); per-product; not in seed-lib. |
| Therapy / daily-life / mailing / personal-finance / adconnect | none | No webhook endpoints today. | Future: any new webhook reinvents the helper unless seed absorbs first. |

**Recurrence-rule fire:** N=2 products with their own HMAC
implementations, plus 1 carve-out (Stripe). The recurrence rule
says **N=2 → triage time**; the obvious triage outcome is
**formalize** (absorb into seed-lib).

**DoS-shaped gaps the audit found:**

- **Body-size cap missing.** FastAPI doesn't cap `request.body()`
  by default. An attacker streaming a 1 GB body forces full
  buffering before HMAC even fires. No middleware visible in
  the seed factory for this.
- **Rate-limit missing.** Even cheap HMAC-fail responses cost
  socket + CPU. Under a botnet flood the endpoint can starve
  other traffic. No rate-limit middleware in seed.
- **HMAC-failure path expensive in some routers.** If audit
  logging / notification dispatch fires on bad signatures, the
  failure path becomes attackable. Needs per-router review.
- **Replay window unbounded** in ERP's `verify_hmac_sha256` —
  no timestamp parameter; the helper validates structure only.
  Stripe SDK does this right (built-in tolerance); ERP's
  callers should match.

The win when this ships: every existing webhook endpoint in this
monorepo verifies HMAC before doing any expensive work, with a
constant-time compare AND a replay-safe timestamp guard, behind
a max-body-size cap and an optional rate limiter. Future
products inherit the helper at zero per-endpoint cost.

---

## 2. Confirmed constraints (what the user *has* said)

> **Source:** the user's 2026-05-02 directives, paraphrased.
> Future agents: confirm before assuming.

- **The original concern came from a different repo (`whatsapp-google-scheduling`).**
  That project is scoped to Meta + Alphabet API integration; the
  user is bringing the lessons here for portability. *(Drives:
  the design must accommodate both Meta-style `X-Hub-Signature-256`
  and Alphabet/Google-style signature schemes. Keep the helper
  signature-format-agnostic — pass in the algorithm + header
  shape — so future integrations don't fork the helper.)*
- **Concerns are BOTH security AND DoS — equal priority.**
  *(Drives: the seed-lib helper covers signature + replay +
  constant-time compare; the seed middleware covers max-body
  + rate-limit. Both ship in this project; not deferring
  either.)*
- **Scope covers BOTH hardening existing webhooks AND
  preventing future ones from reinventing.** *(Drives: Phase 1
  builds the seam, Phase 2 migrates ERP's 3 callers AND adds
  the middleware so the next product webhook inherits both the
  helper and the body-size cap from day one.)*
- **File as a separate project from `mcp-ast-tools-hardening`.**
  *(Drives: lives at root `projects/webhook-hmac-consolidation/`,
  has its own phases, its own audit, its own close. Not bundled
  into the AST hardening rollout.)*

---

## 3. Design principles

1. **Cheap-first gate, then expensive work.** Order: max-body
   cap → rate-limit (optional) → HMAC verify → replay-window
   check → handler. Any reordering opens a DoS lane.
2. **Constant-time signature compare always.** Never use `==`
   on signature bytes. The seed-lib helper enforces
   `hmac.compare_digest`; the linter / keeper detector flags
   `==` against a signature variable name (future enhancement,
   not in this project's first ship).
3. **Replay-safe by default.** The seed-lib helper takes a
   timestamp header + max-age (default 5 min, matching
   Stripe's default tolerance). Endpoints whose providers don't
   send a timestamp must opt in to "no replay protection" with
   a documented rationale.
4. **Stripe SDK is the carve-out.** `stripe.Webhook.construct_event`
   already does HMAC + timestamp; don't double-wrap. The
   seed-lib helper covers everything else.
5. **Signature-format agnostic.** Take algorithm + header
   shape as parameters; one helper supports HMAC-SHA256 (Meta,
   WhatsApp, GitHub), HMAC-SHA1 (legacy GitHub), and whatever
   shape Alphabet uses (TBD — confirm in §7 Q1).
6. **Failure path is silent + cheap.** No audit-log row, no
   notification, no DB write on bad signature — return 401 +
   structured logger.warning (NOT logger.error). Logging at
   warning is fine because it's cheap; deeper observability is
   not.
7. **Outbound signing absorbs separately.** Core's
   `webhook_delivery.py` is a different shape (we sign, customer
   verifies). Phase 2 considers it; if the absorption isn't
   clean, accept-with-rationale and split into a follow-up.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Run the six-question checklist:

1. **Is the contract identical for every product?** YES — HMAC
   signature verification is platform-universal. Algorithm +
   header shape vary per-integration, but the verification
   contract is one function.
2. **Is the data source product-specific?** NO — bytes-in
   (body) + signature header + secret. Universal.
3. **Is the placement product-specific?** NO — lives in seed-lib
   (`noctusai_lib.security.webhooks` — exact module name TBD §7
   Q2). Products import.
4. **Is the visibility / permission rule the same?** YES —
   correct signature → 200 to handler; bad signature → 401;
   missing header → 400. Uniform across products.
5. **Does the seam already exist in seed?** NO — needs new seam.
   Closest existing surface: `seed/backend/lib/noctusai_lib/`
   (the canonical seed-lib root). Likely
   `noctusai_lib.security.webhooks` or
   `noctusai_lib.integrations.webhook_security` per the 6-layer
   layout (TBD §7 Q2 — the layout suggests `integrations/` for
   external-API-shaped concerns).
6. **Default-on or opt-in?** OPT-IN per webhook endpoint
   (since not every endpoint is a webhook), but the seed-lib
   helper + middleware are universally available the moment
   the product imports `noctusai_seed`.

**Litmus — per-product code count this design requires:**

- [ ] **0 lines** — pure cross-product concern; lives entirely in seed
- [x] **1 line** — opt-in dependency on a seed-lib helper per
      webhook endpoint (e.g.
      `signature: bytes = Depends(verify_meta_signature)`).
      Acceptable because not every endpoint is a webhook.
- [ ] A small section
- [ ] Multiple files / pages / mounts per product — STOP

**Phase plan implications:** §6 Phase 1 works in seed-lib +
seed framework (the middleware). §6 Phase 2 migrates 3 ERP
routers from `app/webhook_utils.py` to the seed-lib import
(replaces the per-product helper with a 1-line import
swap). No replication framing — products inherit, don't
re-implement.

---

## 4. Scope

**In scope:**

- **Inbound HMAC verification** consolidated into seed-lib
  (`noctusai_lib.security.webhooks` or per §7 Q2).
- **Replay-window guard** built into the seed-lib helper
  (timestamp header + max-age).
- **Max-body-size middleware** in `noctusai_seed` framework
  (default cap, per-product override).
- **Rate-limit middleware** in `noctusai_seed` framework
  (best-effort — likely `slowapi` or `starlette-limiter`;
  may be opt-in via flag).
- **Migration of ERP's 3 inbound webhook callers** from
  `app/webhook_utils.py` to the seed-lib helper. Delete the
  per-product helper at the end.
- **Audit + decision** on whether
  `products/core/backend/app/services/webhook_delivery.py`
  (outbound signer) absorbs into seed-lib too.
- **Tests** colocated at `seed/backend/lib/tests/` for the
  seed-lib helper + at each migrated router for end-to-end
  verification (per the 5-layer test taxonomy).
- **KB sync** — `KB § 04-SHARED-LIBRARY.md` catalog entry +
  `KB § PATTERNS/backend.md` section on the verify-before-
  expensive pattern.

**Out of scope (deferred):**

- **Cross-pollination of `whatsapp-google-scheduling` findings**
  — until the user pulls those over. The project starts with
  what's already in this repo; sibling-repo learnings update §7
  / §11 when they arrive.
- **A keeper detector that flags `==` on signature variables**
  — separate enhancement; not load-bearing for the first ship.
- **Stripe SDK migration** — Stripe is the documented carve-
  out; the seed-lib helper does not try to replace it.
- **Rate-limit beyond a single-process limiter** — Redis-backed
  cluster-aware rate-limiting requires infra coordination;
  out of scope for v1.
- **WAF / Cloudflare-level protections** — handled outside the
  app; this project addresses what we own.

---

## 5. Architecture / file paths

Sketch — confirm in Phase 0:

```
seed/backend/lib/noctusai_lib/
  security/                          # NEW (or integrations/webhooks/ — §7 Q2)
    __init__.py
    webhooks.py                      # the helper + the dependency
    tests/test_webhooks.py           # seed-lib unit tests

seed/backend/framework/noctusai_seed/
  middleware/                        # NEW (if not present)
    __init__.py
    body_size.py                     # max-body-size cap
    rate_limit.py                    # opt-in rate limiter

products/erp-imobiliario/backend/app/
  webhook_utils.py                   # DELETED at end of Phase 2
  routers/assinaturas.py             # import swap to seed-lib helper
  routers/meta_api.py                # import swap
  routers/whatsapp_webhook.py        # import swap

KNOWLEDGE-BASE/CONTEXT/
  04-SHARED-LIBRARY.md               # add catalog entry
  PATTERNS/backend.md                # add verify-before-expensive section
```

**Helper API sketch (likely shape — confirm in §7):**

```python
# noctusai_lib.security.webhooks

def verify_hmac_signature(
    body: bytes,
    signature_header: str,
    secret: str,
    *,
    algorithm: str = "sha256",          # "sha256" | "sha1"
    prefix: str | None = "sha256=",      # Meta-style; None for raw hex
    timestamp_header: str | None = None,  # opt-in replay guard
    timestamp_value: int | None = None,
    max_age_seconds: int = 300,
) -> None:
    """Raises WebhookSignatureError on any failure (bad signature,
    missing header, expired timestamp). Constant-time compare always."""

def webhook_endpoint(
    *,
    secret_env: str,                     # name of env var holding the secret
    signature_header: str = "X-Hub-Signature-256",
    timestamp_header: str | None = None,
    algorithm: str = "sha256",
    prefix: str | None = "sha256=",
    max_age_seconds: int = 300,
):
    """FastAPI dependency factory. Returns a Depends(...) callable
    that verifies the signature before the handler runs. Returns
    the raw body bytes for the handler to use."""
```

**Middleware sketch:**

```python
# noctusai_seed.middleware.body_size
class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests where Content-Length > max_bytes with 413.
    Falls back to streaming-counter for chunked requests."""
    def __init__(self, app, *, max_bytes: int = 1 * 1024 * 1024):
        ...
```

---

## 6. Implementation phases

Cadence: phase-by-phase by default. 3 phases — kept tight per
the user's "few phases, batch related items" directive.

### Phase 0 — Audit baseline + cross-repo intake ⏳ (2026-05-02; partially folded into Phase 1.a's commit; §7 Q1 still open)
- [x] In-session HMAC audit completed 2026-05-02 (logged in §11 of `projects/mcp-ast-tools-hardening/PROJECT.md`).
- [x] Cross-repo findings ported via commit `e1ba4e3` (parallel agent — see §11 below).
- [x] `webhook_utils.py` API surface inventoried + 3 ERP callers identified.
- [x] §7 Q2 resolved: helpers landed in `seed/backend/lib/noctusai_lib/security/` (security as a top-level seed-lib layer).
- [x] §7 Q3 deferred to Phase 2 (outbound `webhook_delivery.py` still a separate concern).
- [ ] **§7 Q1 still open:** Alphabet/Google signature scheme — needs user input from sibling repo. Phase 0 stays ⏳ until this lands.

**Improvements:** none identified — this is an audit phase, not an implementation phase; the audit findings ARE in §11 and the Phase 1.a / 1.b / Phase 2 plan structure.

### Phase 1.a — Inbound verification primitives ✅ (commit `e1ba4e3`, parallel agent)

Shipped via the parallel agent's commit. Owned by that agent's PR; recorded here for traceability:

- [x] `seed/backend/lib/noctusai_lib/security/webhook_signatures.py` (111 LoC, 3 helpers — `verify_hmac_sha256` for Hub-Signature shape, `compute_hmac_sha256_hex` for bare hex, `verify_svix_signature` for Svix protocol). `hmac.compare_digest` everywhere.
- [x] `seed/backend/lib/noctusai_lib/security/__init__.py` (18 LoC, exports the 3 helpers).
- [x] `seed/backend/lib/tests/test_webhook_signatures.py` (174 LoC, 12 tests — success / tamper / wrong-secret / missing-input / multi-version-rotation / non-v1-rejection / garbage-base64; all passing).
- [x] `KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhook-signatures.md` (141 LoC, four-shape catalog: Hub-Signature / hex HMAC / Svix / Stripe SDK; universal rules; adopter list).
- [x] `KNOWLEDGE-BASE/INDEX.md` updated (Layout tree + topic table) — registers the new KB doc.
- [x] `products/erp-imobiliario/backend/app/webhook_utils.py` converted from real implementation to 16-line re-export shim (3 ERP callers continue to work via the same import path; new code should import from `noctusai_lib.security` directly).
- [x] `products/mailing/backend/app/routers/webhooks.py` migrated from `TODO: verify webhook signature` stub to fully-wired Svix verification with bypass-on-unset-secret WARNING (closes a real un-verified-prod gap).

**Improvements:** the post-commit review of `e1ba4e3` surfaced 9 findings — fully enumerated as Phase 1.b open items below + cited in §11. Headline issues: broken doc pointer at `mailing/webhooks.py:32` (FIXED in this session's commit alongside catalog work), missing replay-window guard, missing `verify_hmac_sha256_hex` symmetric wrapper, missing FastAPI dep factory (recurrence rule N=4 still firing across 4 routers), three-way sync incomplete (memory + CLAUDE.md not updated), `KB § 04-SHARED-LIBRARY.md` not yet updated, LGPD cross-reference missing from the KB doc, no test for the new mailing Svix verification path.

### Phase 1.b — Hardening gaps from review (open)

Found by reviewing `e1ba4e3` (full review in §11 below). **Not blocking the agent's commit; load-bearing for completeness.**

- [x] **🐛 Fix broken doc pointer in `mailing/webhooks.py:32`** — references `KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhooks.md` (doesn't exist); should be `webhook-signatures.md`. **Fixed 2026-05-02 in this session's commit** (one-line edit).
- [ ] **Add `verify_hmac_sha256_hex(body, sig_hex, secret) → bool`** to the seed-lib module. Symmetric with the prefixed verifier; prevents callers from forgetting `hmac.compare_digest`. ~6 LoC + 2-3 tests.
- [ ] **Replay-window guard.** Extend `verify_hmac_sha256(...)` and `verify_svix_signature(...)` with optional `(timestamp_value: int | None, max_age_seconds: int = 300)` params. Default-off so existing callers don't break; opt-in by passing the timestamp from header / body. Stripe SDK already does this internally; the rest of our surface is wide open to capture-and-replay.
- [ ] **Mailing router test.** Add `tests/routers/test_webhooks_router.py` (or extend the existing one) pinning: (a) valid Svix signature → 200, (b) tampered body with same signature → 401, (c) `RESEND_WEBHOOK_SECRET` unset → WARNING + 200 (legacy bypass). Without these, a future refactor can silently re-break verification.
- [ ] **Three-way sync the rule.** New behavioral rule lives in the KB doc but is missing from CLAUDE.md and `~/.claude/projects/.../memory/`. Per CLAUDE.md three-way-sync rule: file CLAUDE.md §1 bullet ("Inbound webhooks verify-before-side-effect; helpers in `noctusai_lib.security.webhook_signatures`") + memory entry `feedback_webhook_verify_before_side_effect.md`.
- [ ] **`KB § 04-SHARED-LIBRARY.md`** — add the new module to the canonical reusable-components catalog. Without it, "check `04-SHARED-LIBRARY.md` first" misses this module.
- [ ] **LGPD cross-reference in `webhook-signatures.md`.** Add one line in the universal-rules section pointing to `KB § PATTERNS/lgpd.md` — verified-but-unparsed Meta/Resend payloads carry PII (names/contacts/email addresses) and need consent/retention treatment after verification.

### Phase 2 — DoS + dep factory + remaining migrations

**Recurrence-rule N=4 fires post-1.a:** the 3 ERP routers + the new mailing router each hand-roll the same `if not header or not verify_*(...): raise HTTPException(401, ...)` pattern. The seed-lib helper absorbed the verification primitive but NOT the dependency-factory pattern. This phase formalizes that.

- [ ] **`webhook_endpoint(...)` FastAPI dependency factory** in `noctusai_lib.security.webhook_signatures` (or sibling module). Reads `secret_env`, signature header(s), optional timestamp header; verifies before the handler runs; returns the raw body bytes for the handler to parse. Replaces the verify-then-raise dance.
- [ ] **`noctusai_seed.middleware.body_size.MaxBodySizeMiddleware`** — default 1 MB cap, per-product override via `settings.webhook_max_body_kb`. Register in `create_product_app(...)` so every product inherits at zero cost.
- [ ] **Opt-in rate-limit middleware** (`slowapi` recommended per §7 Q4). Default off; wire via product config.
- [ ] **Migrate the 4 callers to the dep-factory pattern:**
  - `products/erp-imobiliario/backend/app/routers/assinaturas.py:202`
  - `products/erp-imobiliario/backend/app/routers/meta_api.py:325`
  - `products/erp-imobiliario/backend/app/routers/whatsapp_webhook.py:73`
  - `products/mailing/backend/app/routers/webhooks.py:resend_webhook`
- [ ] **Decide outbound `webhook_delivery.py` absorption.** Either merge into `noctusai_lib.security.webhook_signatures.sign_outbound(...)` (clean) or accept-with-rationale (different shape — we sign vs. customers verify).
- [ ] **Stripe carve-out documentation** — add a `KB § PATTERNS/backend.md § Webhook signature carve-outs` section explicitly naming Stripe's SDK as the canonical verifier (don't wrap, don't reinvent).
- [ ] **End-of-project verification:** every product backend `pytest` green; `cli.py --review` clean; `verify-kb-sync.sh` green; three-way sync verified; folder deletion per `apply-inline-then-delete`.

### Phase 2 — Migrate existing callers + close
- [ ] Migrate `products/erp-imobiliario/backend/app/routers/assinaturas.py`
      from `app.webhook_utils.verify_hmac_sha256` to
      `noctusai_lib.security.webhooks.webhook_endpoint(...)`.
      Run that router's tests in isolation — green required
      before next.
- [ ] Migrate `meta_api.py` — same pattern.
- [ ] Migrate `whatsapp_webhook.py` — same pattern.
- [ ] Delete `products/erp-imobiliario/backend/app/webhook_utils.py`
      + its colocated test if any.
- [ ] Decide per §7 Q3: does
      `products/core/backend/app/services/webhook_delivery.py`
      (outbound signer) migrate into
      `noctusai_lib.security.webhooks.sign_outbound(...)`? If
      yes, migrate + delete the per-product version. If no,
      document the carve-out in §11.
- [ ] Confirm Stripe carve-out: `products/core/backend/app/services/stripe_service.py`
      keeps its `construct_webhook_event` call. Document in
      `KB § PATTERNS/backend.md` why.
- [ ] Add the body-size cap to every product's
      `create_product_app(...)` (zero per-product code if the
      middleware is registered in the factory).
- [ ] Run the full ERP backend test suite end-to-end — green
      required.
- [ ] Run `mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --review`
      — confirm no new compliance issues.
- [ ] Run `bash scripts/verify-kb-sync.sh` — green.
- [ ] **End-of-project verification:**
      - Every product backend `pytest` green
      - Frontend builds for any touched products green
      - KB sync verifier green
      - Three-way sync (KB ↔ CLAUDE.md ↔ memory) — file a
        memory entry IF this project codifies a new behavioral
        rule (e.g. *"webhook endpoints must use the seed-lib
        helper"*); otherwise skip
      - `python mcp/noctusai/cli.py --improvements projects/webhook-hmac-consolidation/PROJECT.md`
- [ ] Flip header to ✅, log §11, delete the project folder per
      `apply-inline-then-delete`.

---

## 7. Open questions

Each paired with a recommendation. Update as work progresses.

1. **Alphabet/Google signature scheme(s) — what's the actual
   shape?** *Recommendation: confirm with user — likely a mix
   of HMAC-SHA256 for some Google APIs and OIDC-style JWT
   verification for Pub/Sub.* Decided in Phase 0; drives helper
   API parameters.
2. **Seed-lib layer — `security/` or `integrations/webhooks/`?**
   *Recommendation: `security/webhooks` per `KB § PATTERNS/seed-lib-layout.md`
   — security primitives belong in their own domain, not under
   integrations.* But integrations also has a fit (webhook IS an
   integration concern). User to confirm in Phase 0.
3. **Outbound webhook signer — same module or separate?**
   *Recommendation: same module
   (`noctusai_lib.security.webhooks.sign_outbound`).* Both
   inbound + outbound are "HMAC over a message" with the same
   cryptographic primitives. Audit existing
   `webhook_delivery.py` shape in Phase 0; if it's tightly
   coupled to org-endpoint dispatch logic, split.
4. **Rate-limit library — `slowapi` vs `starlette-limiter` vs
   custom?** *Recommendation: `slowapi`* — battle-tested,
   FastAPI-native, supports per-endpoint limits. Custom only
   if Phase 0 surfaces a constraint slowapi doesn't meet.
5. **Body-size default — 1 MB? 4 MB?** *Recommendation: 1 MB
   default with per-product override.* Most webhook payloads
   are <100 KB; 1 MB is generous for legitimate use, harsh
   enough to deny abuse. Override per product when integrations
   like file-upload-via-webhook need more.
6. **Should the keeper get a new detector that flags `==` on
   signature variables?** *Recommendation: yes, but in a
   follow-up project (`webhook-detector-rollout`).* Out of
   scope for v1.

---

## 8. Dependencies & blockers

- **Cross-repo intake from `whatsapp-google-scheduling`.**
  Phase 0's Q1 (Alphabet signature scheme) needs the user to
  port findings. Until then, design defaults to HMAC-SHA256.
- **Recurrence-rule honor.** Per CLAUDE.md, the recurrence rule
  fires at N=2; the obvious triage outcome is **formalize**.
  This project is the formalization. If a fourth product needs
  a webhook before this ships, the migration plan grows.
- **No external runtime blockers.** Everything lives in this
  repo; no infra change required (the optional rate-limiter
  is single-process, no Redis dep).

---

## 9. Success criteria

- `noctusai_lib.security.webhooks` (or per §7 Q2 resolution)
  ships with `verify_hmac_signature(...)` +
  `webhook_endpoint(...)` + `sign_outbound(...)` (per §7 Q3).
- `noctusai_seed.middleware.body_size.MaxBodySizeMiddleware` is
  registered in every product's `create_product_app(...)` by
  default.
- ERP's three webhook routers consume the seed-lib helper via
  a `Depends(...)` instead of a hand-rolled per-router call.
- `products/erp-imobiliario/backend/app/webhook_utils.py` is
  deleted.
- Every webhook endpoint in this monorepo (current + future)
  inherits: max-body cap, constant-time compare, replay
  protection, structured 401 on failure.
- Stripe SDK carve-out documented in
  `KB § PATTERNS/backend.md`.
- All affected product test suites green.

---

## 10. How to use this project

```bash
# Read this project + cross-references first
sed -n '1,260p' projects/webhook-hmac-consolidation/PROJECT.md

# Phase 0 audit commands
grep -rn "hmac\|HMAC" products/ seed/ mcp/ 2>/dev/null | grep -v ".venv\|node_modules"
grep -rn -E "webhook|@router\.(post|get).*['\"][^'\"]*webhook" products/*/backend/app/routers/
grep -rn -E "no_auth|allow_anonymous|skip_auth|public_route|signature.*verif" products/*/backend/app/

# Phase 1 verification (after seed-lib helper ships)
cd seed/backend/lib && pytest tests/test_webhooks.py -v
cd seed/backend/framework && pytest tests/

# Phase 2 verification (per migration)
cd products/erp-imobiliario/backend && pytest tests/routers/test_assinaturas_router.py -v
cd products/erp-imobiliario/backend && pytest tests/routers/test_meta_api_router.py -v
cd products/erp-imobiliario/backend && pytest tests/routers/test_whatsapp_webhook_router.py -v

# End-of-project
cd products/erp-imobiliario/backend && pytest
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --review
bash scripts/verify-kb-sync.sh
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --improvements projects/webhook-hmac-consolidation/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after the user surfaced an HMAC + DoS concern from a different-repo agent (the user's `whatsapp-google-scheduling` project, scoped to Meta + Alphabet APIs). In-session audit found N=2 products with their own per-product HMAC verification (ERP `webhook_utils.py` + core's outbound `webhook_delivery.py`) plus 1 carve-out (Stripe SDK). Recurrence rule fires; the obvious triage outcome is **formalize** — absorb into seed-lib + add max-body + opt-in rate-limit middleware. §1, §2 (4 user constraints), §3 (7 design principles), §3a (seed-first analysis — 1-line per-endpoint cost is acceptable), §4 (scope in/out), §5 (file paths + helper API sketch + middleware sketch), §6 (3 phases — Phase 0 audit + cross-repo intake + Phase 1 seed-lib + middleware + Phase 2 migrate + close), §7 (6 open questions paired with recommendations), §10 commands populated. Status: Concept — interrogation pending. Phase 0 cannot start until the user confirms §7 Q1 (Alphabet signature scheme — pulled from sibling repo) + §7 Q2 (seed-lib layer choice). | Claude Opus 4.7 |
| 2026-05-02 | **Phase 1.a ✅ shipped via parallel agent — commit `e1ba4e3`** *(`feat(security): central webhook signature verifier in noctusai_lib + adopt across products`)*. The user authorized cross-pollination from the `whatsapp-google-scheduling` sibling repo; the parallel agent committed 7 files / 494 lines: 3 helpers + 12 tests in `seed/backend/lib/noctusai_lib/security/`, KB doc at `webhook-signatures.md`, INDEX.md updates, ERP webhook_utils.py converted to 16-line re-export shim (3 ERP callers continue to work), mailing webhooks router migrated from `TODO: verify webhook signature` stub to fully-wired Svix verification (closes a real un-verified-prod gap). §6 split: Phase 1 → Phase 1.a (this commit, ✅) + Phase 1.b (gaps below, open) + Phase 2 (DoS + dep factory + remaining migrations, open). | Claude Opus 4.7 |
| 2026-05-02 | **Review of `e1ba4e3` (parallel agent's work) — 9 findings.** Quality verdict: **shippable as-is** — clean code (`hmac.compare_digest` everywhere, type hints, returns False not raise), 12/12 tests green, sensible re-export migration, well-structured KB doc, correct seed-lib layer choice (`security/`). Gaps logged into Phase 1.b above: (1) 🐛 broken doc pointer at `mailing/webhooks.py:32` (`webhooks.md` doesn't exist; should be `webhook-signatures.md`); (2) missing `verify_hmac_sha256_hex` wrapper (asymmetric API surface); (3) no replay-window guard on any helper (capture-and-replay attacks open; Stripe SDK does this, ours doesn't); (4) no test for the new mailing Svix verification path; (5) three-way sync incomplete (KB doc shipped; CLAUDE.md ❌; memory ❌); (6) `KB § 04-SHARED-LIBRARY.md` not updated; (7) LGPD cross-reference missing from KB doc; (8) recurrence-rule N=4 STILL fires post-migration (3 ERP + 1 mailing routers each hand-roll verify-then-raise — not absorbed by the seed-lib primitive); (9) no middleware (`MaxBodySizeMiddleware` + opt-in rate-limit deferred to Phase 2). Methodology compliance scorecard: ✅ recurrence-rule formalize-primitive, ✅ seed-lib layout, ✅ no silent errors, ✅ constant-time compare, ✅ tests colocated; ❌ recurrence-rule formalize-dep-factory, ❌ three-way sync, ❌ LGPD-first cross-reference. **Not blocking the parallel agent's commit; load-bearing for Phase 1.b.** | Claude Opus 4.7 |
