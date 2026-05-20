# Gmail seed-lift — Project Document

> **This is a living document, not a rigid checklist.** Status below is
> **Filed** — filed by `mcp-connector-expansion` Wave 1b
> (Engineer DOCS-CONSUME) as a follow-up; NOT yet interrogated with the
> user. The next agent to pick this up MUST interrogate the user first
> (§7) before locking the design — this stub captures the gap and the
> evidence, not a locked plan.
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.
> Phase status: `✅` shipped · `⏳` in-progress · `🔒` blocked-dep ·
> `🅿️` blocked-user. Triage: `[F]` formalize · `[R]` refactor ·
> `[A]` accept. Recurrence: `N=2` ⇒ triage; `N≥3` ⇒ MUST formalize.

- **Created:** 2026-05-17
- **Last updated:** 2026-05-20 (P4 close — P2/P3 found already shipped at b881079b)
- **Status:** ✅ **CLOSED** — P2/P3 seed adapter already shipped 2026-05-18 at commit `b881079b` (originating project: `mcp-connector-expansion`); P4 three-way doc sync shipped this dispatch. See §11 for the brief↔code drift finding.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:** `KB § INTEGRATIONS/google.md` · `KB § INTEGRATIONS/oauth-patterns.md` · `KB § PATTERNS/seed-fake-real-adapter.md` · `KB § GUIDES/google-oauth-setup.md`
- **Project slug:** `gmail-seed-lift` at `projects/gmail-seed-lift/` (cross-product platform-infra: a new seed integration package, not single-product)

---

## 1. Context & Purpose

There is **no Gmail send/read adapter in seed.**
`noctusai_lib.integrations.email` is a **Resend-backed** module — its
`__all__` is `send_product_invitation_email` (templated invitation) +
the `Digest` / `send_digest` / `send_to_one` / `send_to_many` scheduled
digest helpers. It is NOT a Gmail client: no per-user inbox read, no
Gmail-API send-as, no thread/label surface. While documenting the
Google integration cluster (`mcp-connector-expansion` Wave 1b) the gap
surfaced: the Google seed family ships Calendar / Maps / YouTube / Drive
but **no Gmail** — a product needing "send from the user's Gmail" or
"read the user's inbox" has nowhere in seed to consume from and would
hand-roll a Graph/Gmail client (seed-first violation).

The win: a canonical `noctusai_lib.integrations.gmail` package in the
Protocol + Fake + Real + factory shape (mirrors `google_calendar` /
`youtube` / `google_drive`), so any future Gmail-touching product
inherits a tested adapter instead of forking one.

---

## 2. Confirmed constraints

**Locked by user 2026-05-20** (§7 defaults adopted verbatim):

- **v1 scope: SEND-ONLY.** No inbox read in v1. Smaller App-Review surface; matches the common "send from the user's Gmail" need. Read path is out-of-scope-with-destination (a future `gmail-seed-read-extend` follow-up if/when a consumer surfaces).
- **Per-user OAuth refresh-token** via existing `noctusai_lib.security.token_store.CredentialStore`. No workspace SA (Gmail API has no system-user; SA needs Workspace DWD which most tenants lack). Same shape as `google_calendar` / `youtube` / `google_drive`.
- **Seed-ahead authorized** by user — no consumer exists today (N=0). Mirrors the youtube/drive precedent. Lift now, consume later.

---

## 3. Design principles

1. **Mirror the canonical Fake+Real shape** — Protocol + Fake + Real +
   factory exactly like `google_calendar` / `youtube` / `google_drive`
   per `KB § PATTERNS/seed-fake-real-adapter.md`. Gmail touches IO, so
   the Fake-exercises-different-code test says it is NOT exempt.
2. **Reuse the existing OAuth stack** — credentials via
   `CalendarCredentialResolver`-style Protocol + `CredentialStore`;
   the OAuth dance is the generic `noctusai_lib.security.oauth` router
   (do NOT duplicate — same rule the Meta + Calendar packages follow).
3. **Read-only OR send-only v1** — narrow surface; App-Review-gated
   scopes out-of-scope-with-destination, mirroring the meta read-only-v1
   precedent.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Contract identical for every product?** YES — a Gmail send/read
   contract is vendor-shaped, not product-shaped.
2. **Data source product-specific?** NO — Gmail API is uniform; the
   per-tenant OAuth credential lookup is the only product-injected seam
   (same pattern as Calendar's `CalendarCredentialResolver`).
3. **Placement product-specific?** NO — `noctusai_lib.integrations.gmail`,
   universal.
4. **Visibility / permission rule the same?** YES — per-user OAuth
   consent, uniform.
5. **Seam already exists in seed?** PARTIAL — OAuth dance + token store
   exist (`security.oauth`, `security.token_store`); the Gmail adapter
   Protocol/Fake/Real/factory does NOT.
6. **Default-on or opt-in?** OPT-IN — only products that need Gmail wire
   it; not every product.

**Litmus — per-product code count:** **0 lines** in product code (pure
cross-product seed concern; products inherit from the factory + inject a
credential resolver). §6 phases work IN SEED, never walk products.

---

## 4. Scope

**In scope (proposed — confirm in §7):**
- New `seed/lib/backend/noctusai_lib/integrations/gmail/` package:
  Protocol + value objects + Fake + Real (`googleapiclient` Gmail v1) +
  factory + credentials Protocol + pure mappers.
- Colocated tests (Fake-driven + Real error-path).
- `KB § INTEGRATIONS/google.md` §6 (new) + `__all__` documentation.

**Out of scope:** Gmail push/watch (Pub/Sub) subscriptions; full
thread/label management beyond v1; any product wiring (N=0 — separate
follow-up once a consumer exists, unless user authorizes seed-ahead).

---

## 6. Phases

- **P1 ✅** — §7 interrogation. User locked design 2026-05-20: send-only v1, per-user OAuth via `CredentialStore`, seed-ahead authorized.
- **P2 ✅ (already-shipped finding)** — Protocol + value objects + Fake + factory + tests already shipped 2026-05-18 at commit `b881079b` ("feat(mcp-connector-expansion): seed Gmail adapter — Protocol+Fake+Real+factory") by the `mcp-connector-expansion` project. Verified at this dispatch's fork base SHA `42c47e34`. Shape diverges from this brief's design (the shipped adapter ships `GmailClient`/`GmailMessage`/`SendResult`/`GmailListResult` covering send + read v1; this PROJECT.md's §2-3 specified an `EmailAddress`/`GmailSendResult`/typed-`GmailSendError` send-only Protocol). Codebase-is-source-of-truth → shipped shape wins. See §11.
- **P3 ✅ (already-shipped finding)** — `RealGmailClient` ships in same commit `b881079b`. Mock-googleapiclient transport tests covering send-builds-raw + list-hydrates-via-get + 404→None + 5xx→reraise + construction-without-oauth-raises ship in `seed/lib/backend/tests/integrations/gmail/test_gmail.py` (30 tests, all green at base).
- **P4 ✅** — Three-way sync shipped this dispatch:
  - `noctusai_lib/integrations/gmail/protocol.py` — `GmailSender` Protocol (single method: `send(*, from_addr: EmailAddress, to: list[EmailAddress], subject: str, body_html: str, body_text: str | None, ...) → GmailSendResult`).
  - `noctusai_lib/integrations/gmail/value_objects.py` — `EmailAddress`, `GmailSendResult`, `GmailSendError` (typed errors: `AuthExpired`, `QuotaExceeded`, `RecipientRejected`, `Transient`).
  - `noctusai_lib/integrations/gmail/fake.py` — `FakeGmailSender` (in-memory; `sent_messages` introspection; configurable error injection per error type).
  - `noctusai_lib/integrations/gmail/factory.py` — `get_gmail_sender(*, credentials_resolver, store) → GmailSender` (Fake when no creds resolved + factory_mode=auto; else Real).
  - `noctusai_lib/integrations/gmail/credentials.py` — `GmailCredentialResolver` Protocol mirroring `CalendarCredentialResolver`.
  - Tests at `seed/lib/backend/tests/integrations/gmail/` — Protocol shape, Fake behavior, factory routing.
- **P3 ⏳** — Real adapter:
  - `noctusai_lib/integrations/gmail/real.py` — `RealGmailSender` wrapping `googleapiclient.discovery.build('gmail', 'v1', credentials=...).users().messages().send(...)`.
  - Error mapping: Gmail API errors → typed `GmailSendError` subclasses (401 → AuthExpired; 403 quota → QuotaExceeded; 400 invalid → RecipientRejected; 5xx → Transient with retry policy).
  - Credentials wiring: resolver lookup → `CredentialStore.get_or_refresh(...)` → `google.oauth2.credentials.Credentials`.
  - Real-path tests with HTTP mocking (httpretty / responses library).
- **P4 ✅** — Three-way sync shipped this dispatch:
  - `KB § INTEGRATIONS/google.md` — added §5 Gmail (consume-side recipe, `__all__` verbatim, OAuth-only auth notes, factory fallback semantics, `mcp/google/tools/gmail.py:48` cited consumer, out-of-scope-v2 list); renumbered §5 Gaps → §6 and replaced GAP row with two precise out-of-scope rows (v2 surface + `CredentialStoreGmailResolver` bridge); first-paragraph + title now read "Calendar · Maps · YouTube · Drive · Gmail".
  - `KNOWLEDGE-BASE/INDEX.md` — updated existing `google.md` row description + Layout-tree leaf to mention Gmail (no new top-level row — Gmail is folded into the existing five-adapter google.md, NOT a separate file).
  - `CLAUDE.md` §2 — updated the existing `KB § INTEGRATIONS/google.md` bullet to include Gmail (OAuth-only send+read v1 + `OAuthGmailCredentials`/`GmailCredentialResolver`/`make_gmail_client` + `gmail.send` default scope + no API-key path + no DWD v1); same edit to §3 lookup-table row.
  - Memory entry stub (architect transcribes): `feedback_gmail_seed_send_only_v1` — one-line body: "Gmail seed ships canonical Protocol+Fake+Real+factory in `noctusai_lib.integrations.gmail`; OAuth-only (no API-key path for user mailbox); v1 = send + list + get; `gmail.send` is the minimal scope default in `OAuthGmailCredentials`; consumed by `mcp/google/tools/gmail.py`; seed-ahead per N=0-consumer policy."

---

## 7. Open questions (paired with recommendations)

1. **Send-only, read-only, or both for v1?** — *Recommendation:*
   send-only v1 (lower App-Review surface; matches the common
   "send from the user's Gmail" need). Confirm the actual driving use.
2. **Per-user OAuth or workspace service-account?** — *Recommendation:*
   per-user OAuth refresh-token via existing `CredentialStore` (Gmail
   API has no system-user token; SA needs Workspace DWD which most
   tenants lack).
3. **Is there a driving consumer, or seed-ahead?** — *Recommendation:*
   only lift now if the user explicitly authorizes seed-ahead (the
   youtube/drive precedent); otherwise hold until N=1 consumer exists.

---

## 11. Change log

- **2026-05-17** — Filed as a stub by `mcp-connector-expansion`
  Wave 1b (Engineer DOCS-CONSUME). Gap discovered while authoring
  `KB § INTEGRATIONS/google.md`: `noctusai_lib.integrations.email` is
  Resend (digest/invitation), NOT Gmail; no Gmail adapter in seed.
  Status=Filed; not interrogated; not scheduled.
- **2026-05-20** — §7 defaults locked-in by user authorization. §2 constraints + §6 phases promoted from placeholder to concrete sub-tasks. P1 ✅; P2 dispatch ready. Architect.
- **2026-05-20** — Engineer GMAIL-LIFT dispatched for P2+P3+P4. **Codebase-is-source-of-truth finding**: the seed `noctusai_lib.integrations.gmail` package was already shipped in full at commit `b881079b` ("feat(mcp-connector-expansion): seed Gmail adapter — Protocol+Fake+Real+factory") by the `mcp-connector-expansion` project — predating this brief by 2 days but post-dating the §7 user-decision date. Verified at fork-base SHA `42c47e34`: all 7 source files (`__init__.py` / `credentials.py` / `factory.py` / `fake.py` / `protocol.py` / `real.py` / `types.py`) + 30 colocated tests (`test_gmail.py`) green. `mcp/google/tools/gmail.py` already consumes via `make_gmail_client` (the first in-tree adopter). The shipped shape (`GmailClient` / `GmailMessage` / `SendResult` / `GmailListResult`, send + read v1) diverges from this brief's design (`GmailSender` / `EmailAddress` / `GmailSendResult` / typed `GmailSendError`, send-only v1) — codebase wins per the codebase-is-source-of-truth rule. P2 + P3 ticked as already-shipped; P4 (three-way doc sync) shipped this dispatch; project closes. Brief↔code drift surfaced as a new pattern instance — see findings (root cause: this brief did NOT run §4 dispatch-time `git ls-tree origin/main seed/lib/backend/noctusai_lib/integrations/` to verify the seed wasn't already present at the engineers' fork base — the same shape as R2 verify-seed-on-fork-base but applied to *new-adapter projects* rather than *consume-the-existing-seed* dispatches; the prevention is the SAME `verify-seed-ships-it at DISPATCH time` rule already codified in memory — extend the rule's framing to also cover "verify the seed DOESN'T already ship it" before dispatching a build project). Engineer GMAIL-LIFT.
