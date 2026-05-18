# Gmail seed-lift — Project Document

> **This is a living document, not a rigid checklist.** Status below is
> **Filed** — filed by `mcp-connector-expansion` Wave 1b
> (Engineer DOCS-CONSUME) as a follow-up; NOT yet interrogated with the
> user. The next agent to pick this up MUST interrogate the user first
> (§7) before locking the design — this stub captures the gap and the
> evidence, not a locked plan.
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.
> Phase status: shipped / in-progress / blocked-dep / blocked-user.
> Triage: [F] formalize / [R] refactor / [A] accept. Recurrence:
> N=2 => triage; N>=3 => MUST formalize.

- **Created:** 2026-05-17
- **Last updated:** 2026-05-17
- **Status:** Filed (follow-up; not interrogated; not scheduled)
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:** `KB § INTEGRATIONS/google.md` · `KB § INTEGRATIONS/oauth-patterns.md` · `KB § PATTERNS/seed-fake-real-adapter.md` · `KB § GUIDES/google-oauth-setup.md`
- **Project slug:** `gmail-seed-lift` at `projects/gmail-seed-lift/` (cross-product platform-infra: a new seed integration package, not single-product)

---

## 1. Context & Purpose

There is **no Gmail send/read adapter in seed.**
`noctusai_lib.integrations.email` is a **Resend-backed** module — its
`__all__` is `send_product_invitation_email` (templated invitation) +
the `Digest` / `DigestSendResult` / `send_digest` / `send_to_one` /
`send_to_many` scheduled digest helpers. It is NOT a Gmail client: no
per-user inbox read, no Gmail-API send-as, no thread/label surface.
While documenting the Google integration cluster
(`mcp-connector-expansion` Wave 1b) the gap surfaced: the Google seed
family ships Calendar / Maps / YouTube / Drive but **no Gmail** — a
product needing "send from the user's Gmail" or "read the user's inbox"
has nowhere in seed to consume from and would hand-roll a Gmail client
(seed-first violation).

The win: a canonical `noctusai_lib.integrations.gmail` package in the
Protocol + Fake + Real + factory shape (mirrors `google_calendar` /
`youtube` / `google_drive`), so any future Gmail-touching product
inherits a tested adapter instead of forking one.

---

## 2. Confirmed constraints

> **None confirmed yet — this is a filed stub.** The following are
> OPEN until the user is interrogated (§7). Do not treat as locked.

- **Read vs send scope** — unknown. *(Drives whether v1 is send-only,
  read-only, or both; gates which OAuth scopes / App Review path.)*
- **Per-user OAuth vs workspace service-account** — unknown.
  *(Gmail API has no system-user analogue like Meta; likely per-user
  OAuth refresh-token via the existing `CredentialStore`.)*
- **Driving consumer** — unknown (N=0 today). *(Seed-ahead-of-consumer
  is acceptable only with explicit user authorization, per the
  youtube/drive precedent — confirm before lifting.)*

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
   scopes out-of-scope-with-destination, mirroring the meta
   read-only-v1 precedent.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Contract identical for every product?** YES — a Gmail send/read
   contract is vendor-shaped, not product-shaped.
2. **Data source product-specific?** NO — Gmail API is uniform; the
   per-tenant OAuth credential lookup is the only product-injected seam
   (same pattern as Calendar's `CalendarCredentialResolver`).
3. **Placement product-specific?** NO —
   `noctusai_lib.integrations.gmail`, universal.
4. **Visibility / permission rule the same?** YES — per-user OAuth
   consent, uniform.
5. **Seam already exists in seed?** PARTIAL — OAuth dance + token store
   exist (`security.oauth`, `security.token_store`); the Gmail adapter
   Protocol/Fake/Real/factory does NOT.
6. **Default-on or opt-in?** OPT-IN — only products that need Gmail
   wire it; not every product.

**Litmus — per-product code count:** **0 lines** in product code (pure
cross-product seed concern; products inherit from the factory + inject
a credential resolver). §6 phases work IN SEED, never walk products.

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

> Placeholder — re-plan after §7 interrogation. Do NOT execute as-is.

- **P1 (blocked-user)** — interrogate user (read vs send, per-user vs
  SA, driving consumer, seed-ahead authorization). Lock §2.
- **P2 (blocked-dep)** — Protocol + value objects + Fake + factory +
  tests (no network).
- **P3 (blocked-dep)** — Real adapter (`googleapiclient` Gmail v1) +
  error mapping + credentials resolver wiring through `CredentialStore`.
- **P4 (blocked-dep)** — `KB § INTEGRATIONS/google.md` §6 +
  INDEX/CLAUDE/memory three-way sync.

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
