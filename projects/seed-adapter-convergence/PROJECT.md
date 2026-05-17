# seed-adapter-convergence — Project Document

> Living document. Filed 2026-05-16 as the **named destination** for the deferred seed-convergence of social-wiring's 4 OAuth-write-coupled adapters (decision recorded in `KB § PATTERNS/accept-with-rationale.md` → "Entries from social-wiring-absorption Wave 2"). Self-contained — no dependency on the absorption project folder surviving.

- **Created:** 2026-05-16
- **Status:** Filed / not started — **gated** on the seed-side prerequisites below
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `seed-adapter-convergence` (cross-product / seed-infra → `projects/seed-adapter-convergence/`)

## 1. Context & Purpose

During the social-wiring absorption (2026-05-16), Wave-1 reconciled the seed Google/Meta/credential integrations to a **resolver-Protocol architecture**. social-wiring's validated OAuth-write-coupled adapters (`app/services/{calendar,meta,routing,drive_api}` + `credential_store.py`) are **contract-incompatible** with that seed shape on 4 axes (credential-read · OAuth credential-WRITE path · `isinstance` adapter-type labeling · Meta method-set capability gap — Wave-1.E4 dropped `me()`/`get_page()`). Two engineers (W2.5/W2.5b) proved a forced convergence would destroy validated behavior + the 69-test internal oracle. Decision: keep those 4 product-local at N=1, converge later — here.

### 1a. Routed-in adjacent seed-adapter follow-ups (W5.7-rest / W5.9-rest, 2026-05-16 — recorded here to avoid a duplicate stub)

- **`VistaClientProtocol`** (Wave-1.E6) — `noctusai_lib.integrations/vista/` shipped Real-only pre-W1; Fake+factory were added during W1 but a `VistaClientProtocol` is still deferred (touches the ERP showcase + `mcp/vista` consumers). W2.5 extended the requirement: verify-the-seed-ships-it must assert the *factory signature the named consumer needs*, not merely a same-name factory — the Vista convergence inherits that 4th-shape check.
- **`ts-morph` → seed-frontend devDeps** — `ts-morph` (TS AST-edit tool, AST-first rule) belongs in the seed-frontend `devDependencies` so every product frontend inherits it rather than each re-adding; route the dependency-placement with this convergence's frontend-adapter pass (same seed-frontend surface).

## 2. Prerequisites (seed work FIRST — this project is gated on all three)

1. **Seed Meta capability gap.** `noctusai_lib.integrations.meta` must ship `me()` + `get_page(page_id)` + `auth_mode` (Wave-1.E4 reconcile renamed+dropped these vs the validated workspace adapter). Without it, social-wiring's `meta_router`/`whatsapp_intake_service` consumers cannot converge.
2. **`credential_store=`-convenience factory path.** `get_calendar_adapter`/`get_meta_adapter`/`make_drive_reader` should accept a product `CredentialStore` directly (today only the resolver Protocol + `token_store`), so consumers don't each hand-roll a resolver bridge. N≥2 once a 2nd product needs it → seed formalize.
3. **OAuth credential-WRITE seam.** The seed delegates OAuth start/callback to `noctusai_lib.security.oauth` but exposes no provider-constant + callback-write contract equivalent to the workspace `store.upsert(provider=CALENDAR_PROVIDER/META_PROVIDER)`. A seed write seam is required before the routers can drop the workspace `credential_store`.

## 3. Scope (after prerequisites land)

- Converge social-wiring `services/{calendar,meta,routing,drive_api}` → seed factories; retire `credential_store.py` (becomes N≥2 → seed-absorb candidate at that point).
- Preserve behavior; migrate the 69 internal-oracle tests to the seed seam (the convergence makes the internal tests obsolete by construction — replace with seam-level tests).
- Apply the verify-the-seed-ships-it **4th-shape** keeper (consumer-method-set + write-path compat) so this class of under-ship is caught at reconcile time, not absorption time.

## 4. Success criteria

social-wiring consumes the seed for ALL its integrations (no product-local OAuth adapters); the accept-with-rationale entry flips `accept`→`formalized`; full social-wiring suite green on the seam.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the named destination for the social-wiring-absorption Wave-2 deferral (Option A). Gated on 3 seed prerequisites. | Claude Opus 4.7 |
