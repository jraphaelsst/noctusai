# social-wiring-google-seed-consume — Project Document

> **Living document.** Revise phases, fold in optimizations, update §11 as work
> lands. Written for a **zero-context reader** — assume the next agent has not
> seen the conversation that produced this.

- **Created:** 2026-05-19
- **Last updated:** 2026-05-19
- **Status:** Design locked → Phase 0 ready (awaiting "go", phase-by-phase cadence)
- **Owner / stakeholders:** joaoraphaelsst · architect (Claude)
- **Related docs:** `products/social-wiring/MASTER-PROMPT.md` (§"Seed seams consumed" — currently doc⊥code, see §1) · `KB § INTEGRATIONS/google.md` · `KB § INTEGRATIONS/oauth-patterns.md` · `KB § PATTERNS/seed-fake-real-adapter.md` · sibling closed project `projects/social-wiring-absorption-debt/` (different debt class — compliance counts, NOT seed-consume)
- **Project slug:** `social-wiring-google-seed-consume` — intent ≈ `wiring` (the canonical `<product>-seed-wiring` remediation per `KB § 01-PHILOSOPHY.md § Compliance`); named `-google-seed-consume` for zero-context clarity (the product name already contains "wiring"). Location: `products/social-wiring/projects/` (single-product scope).

---

## 1. Context & Purpose

`social-wiring` was developed externally and absorbed (Wave 1–4, 2026-05-16). It
hand-rolls **its entire Google integration stack** against `googleapiclient` +
raw OAuth + a product-local Fernet vault, while the seed **already ships every
one of those seams**. Verified against the tree 2026-05-19:

| Hand-rolled in social-wiring | LoC | Seed seam that already ships it |
|---|---|---|
| `services/youtube_service.py` (API + OAuth flow + resumable upload) | 800 | `noctusai_lib.integrations.youtube` — `make_youtube_client`, OAuth-aware `upload_video` |
| `services/credential_store.py` (Fernet vault; ~12 consumers) | 211 | `noctusai_lib.security.token_store` — `make_credential_store`, `SupabaseCredentialStore` |
| `services/calendar/*` (googleapiclient + `oauth_adapter`) | 573 | `noctusai_lib.integrations.google_calendar` + `security.oauth` |
| `services/drive_api/*` (googleapiclient + `oauth_adapter`) | 773 | `noctusai_lib.integrations.google_drive` + `security.oauth` |
| OAuth lifecycle (authorize/exchange/refresh/revoke) across all of the above | — | `noctusai_lib.security.oauth.GoogleProvider` + `oauth_router` |

**~2,357 LoC duplicating shipped seed seams.** The seed
`oauth/google_provider.py` docstring **explicitly states it was built to cure
"the hand-rolled … oauth_adapter's refresh logic"** — this is the exact drift
class the seam was formalized from. Recurrence is **N≥3 within this one
product** (youtube ∧ calendar ∧ drive each independently re-implement API +
OAuth + creds) ⇒ DRY rule = MUST refactor (`[A]` accept is off the table;
recurrence flips accept→refactor, and the formalization already exists).

`MASTER-PROMPT.md:77–78` asserts these seams are *"consumed (do NOT
re-implement product-locally)"* — the code re-implements all of them. **Doc⊥code;
code wins** (a same-session drift marker was added to MASTER-PROMPT pointing
here; the claim becomes TRUE when this project lands).

**Win:** ~2.3k LoC of security-sensitive duplication retired; one OAuth/creds
codepath for the whole fleet; the upcoming YouTube feature is built on the
clean seed surface (decided refactor-first — see §2).

---

## 2. Confirmed constraints

- **Scope = full Google stack** — youtube + calendar + drive + shared OAuth +
  credential_store, ONE project. *(User-chosen over youtube-only: same root
  cause, overlapping files (`credential_store`, `oauth_adapter`); piecemeal
  re-opens the shared files twice.)*
- **Sequencing = refactor-first, then feature** — land this on a clean
  baseline, THEN build the YouTube feature on the seed-consuming surface.
  *(User-chosen. `no-quick-fixes` / framework-first: building the new feature
  on the divergent hand-rolled surface manufactures more drift to unwind.)*
- **Clean refactor, NOT a data migration** — seed `SupabaseCredentialStore`
  expects `encrypted_tokens TEXT` Fernet(JSON) keyed `(org_id, provider)`;
  social-wiring's `credentials` table is **column-identical** (verbatim DDL
  comment "Fernet-encrypted JSON"). Only the table *name* differs
  (`credentials` vs default `oauth_credentials`) — handled by the store's
  `table=` param. Zero rename, zero re-encrypt expected. *(Closes the only
  scope-blowup risk; Phase 0 verifies the at-rest bundle shape decrypts.)*

---

## 3. Design principles

1. **Shared root first.** The credential vault is the common dependency of
   youtube ∧ calendar ∧ drive ∧ oauth — refactor it (Phase 1) before the
   integrations that consume it.
2. **Behavior-preserving.** Every external contract (OAuth redirect URIs,
   route paths, response shapes, pt-BR copy) is preserved; this is a
   substitution refactor, not a redesign. Phase 0 maps every contract first.
3. **Tests are the oracle.** Segmented construction evades grep
   (`feedback_structural_refactor_grep_blindspot`) — full backend `pytest` +
   frontend `vite build` are the merge gate, not greps.
4. **Seed gaps → formalize, never re-fork.** `set_thumbnail` /
   `get_processing_status` are not in the seed `YoutubeClient` Protocol →
   triage to seed-formalize (Protocol+Fake+Real), not a product wrapper.
5. **AST-first.** All `.py` edits via libcst (`feedback_ast_first`).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Identical contract for every product?** YES — OAuth + credential storage +
   Google API access are fleet-generic; the seed already ships the canonical
   Protocol+Fake+Real+factory for each.
2. **Data source product-specific?** NO — uniform (OAuth tokens, Google APIs).
   The product-specific part is *which providers* + *the video catalog domain*,
   which stays product-local and consumes the seam.
3. **Placement product-specific?** NO — the seam is universal; social-wiring is
   one consumer.
4. **Visibility / permission rule the same?** YES — RLS-scoped per org via the
   existing `(org_id, provider)` key; unchanged.
5. **Seam already in seed?** **YES, all of it** —
   `noctusai_lib.security.token_store` (`make_credential_store`) ·
   `noctusai_lib.security.oauth` (`make_oauth_provider`/`GoogleProvider`/`oauth_router`/`CallbackHook`) ·
   `noctusai_lib.integrations.{youtube,google_calendar,google_drive}`
   (`make_*_client`). Verified `__init__.py` exports + Real adapters 2026-05-19.
6. **Default-on or opt-in?** N/A — this is consumer remediation, not a new
   capability. The seams are already default-available via the lib.

**Litmus — per-product code count this design requires:** the *correct* end
state is a thin product wiring layer (factory calls + the video-catalog domain)
≈ **a small section**, replacing ~2,357 LoC of forked structure. Any seed gap
found (thumbnail / processing-status) is **formalized into the seed**, not
re-forked → that delta lands in `seed/`, not the product.

**Phase plan implications:** §6 phases work on the **consumer↔seam boundary**
(replace fork with factory call) + the seed (formalize the 2 gaps). NO
per-product replication framing — there is exactly one product.

---

## 4. Scope

**In scope:**
- Replace `services/credential_store.py` → `noctusai_lib.security.token_store.make_credential_store(table="credentials")`; migrate ~12 consumers to the `CredentialStore` Protocol.
- Replace hand-rolled OAuth (`calendar/oauth_adapter.py`, `drive_api/oauth_adapter.py`, youtube OAuth flow) → `noctusai_lib.security.oauth` (`GoogleProvider` + generic `oauth_router` + `CallbackHook` persisting via the Phase-1 store).
- Replace `youtube_service.py` API layer → `make_youtube_client`; keep `video_cache_service`/`upload_service`/`dashboard_service` orchestration calling the seed client.
- Replace `services/calendar/*` + `services/drive_api/*` API adapters → `noctusai_lib.integrations.{google_calendar,google_drive}`.
- Formalize the 2 seed gaps (`set_thumbnail`, `get_processing_status`) into `noctusai_lib.integrations.youtube` (Protocol+Fake+Real).
- Reconcile `MASTER-PROMPT.md` / `README.md` (doc⊥code → doc=true).

**Out of scope (for now — with reason):**
- The actual new YouTube **feature** — sequenced AFTER this (user decision §2); a separate effort on the clean surface.
- `services/meta/*` — Meta adapter, not Google-stack; separate recurrence if it exists. Note in Phase 0; file a fast-follow if hand-rolled.
- Folding youtube app-level code into a `modules/youtube/` package (the app-level-vs-`modules/` asymmetry) — **decided in Phase 0**: include in Phase 5 if cheap post-refactor, else named fast-follow `social-wiring-youtube-modularize`.
- Compliance-count debt (RLS / monkeypatch tests) — already handled by closed `social-wiring-absorption-debt` (P5 follow-up `social-wiring-monkeypatch-test-refactor`).

---

## 5. Architecture / Data Model

**No schema change.** `social_wiring.credentials` stays as-is; the seed store
binds to it via `make_credential_store(client, fernet_key, table="credentials")`.
Extra columns (`channel_id`, `channel_title`, `scopes`) → either folded into
`StoredCredential.metadata` or kept as denormalized read-columns (Phase-0
decision; low risk — the seed store does `select("*")` and ignores extras).

**Seam map (consumer → seed):**

```
credential_store.CredentialStore        → noctusai_lib.security.token_store.CredentialStore (make_credential_store, table="credentials")
calendar/oauth_adapter + drive/oauth    → noctusai_lib.security.oauth.GoogleProvider + oauth_router(on_callback=<persist via store>)
youtube_service (OAuth bits)            → same oauth seam
youtube_service (API: list/get/upload)  → noctusai_lib.integrations.youtube.make_youtube_client
  · gap: set_thumbnail, get_processing_status → FORMALIZE into seed youtube Protocol+Fake+Real
calendar/_google_api + google_adapter   → noctusai_lib.integrations.google_calendar.make_*_client
drive_api/_drive_api + google_adapter   → noctusai_lib.integrations.google_drive.make_*_client
```

OAuth route surface today is bespoke per integration; seed `oauth_router`
mounts generic `/api/oauth/{provider}/{authorize,callback,refresh,revoke}`.
**Phase 0 maps every current external URL/redirect** so Phase 2 preserves them
(behavior-preserving principle §3.2).

---

## 6. Implementation phases

Phase-by-phase cadence (default). Status icons per template legend.
`[F]` formalize · `[R]` refactor · `[A]` accept.

### Phase 0 — Audit & encryption-format verification
- [ ] Decrypt a sample `social_wiring.credentials.encrypted_tokens` row with the product Fernet key; confirm shape == `Fernet(json.dumps(dict))` so seed `token_store.decrypt` reads existing rows (very likely — DDL comment matches seed docstring verbatim). If shape differs → add a one-time re-encrypt sub-task to Phase 1 (small, NOT a project blocker).
- [ ] Enumerate every `credential_store` / `youtube_service` / `calendar` / `drive_api` consumer call site (the ~12 routers/services) — exact import + construction shape.
- [ ] Read exact `__all__` + Real-adapter surface of seed `youtube` / `google_calendar` / `google_drive` / `oauth` / `token_store`; map method-by-method to the hand-rolled equivalents; confirm `set_thumbnail`/`get_processing_status` are the only genuine gaps.
- [ ] Map every current OAuth external URL / redirect-URI / route path (behavior-preservation contract for Phase 2).
- [ ] `org_id UUID` (social-wiring) vs seed store `org_id text` `.eq()` — confirm PostgREST coercion is clean.
- [ ] Decide: extra credential columns → `metadata` vs keep; youtube `modules/` fold in-scope vs fast-follow; `services/meta/*` hand-rolled? (fast-follow if yes).
- [ ] Output: green-light + revised §6 if any finding invalidates it (revise-loud, don't silently absorb).

### Phase 1 — Credential vault → seed `token_store` (shared root)
- [ ] Replace `services/credential_store.py` with `make_credential_store(client, fernet_key, table="credentials")`; map `EncryptionNotConfigured` → seed error contract.
- [ ] Migrate the ~12 consumers to the `CredentialStore` Protocol (`get`/`put`/`delete`/`list_providers`) — libcst.
- [ ] `git rm` `credential_store.py`; tests green (`pytest`).

### Phase 2 — OAuth lifecycle → seed `oauth`
- [ ] Replace `calendar/oauth_adapter.py` + `drive_api/oauth_adapter.py` + youtube OAuth flow with `GoogleProvider` + `oauth_router(on_callback=<persist via Phase-1 store>)`.
- [ ] Mount generic `/api/oauth/{provider}/*`; retire bespoke oauth routes **preserving external URLs/redirects** (Phase-0 map). Tests green.

### Phase 3 — YouTube API → seed `integrations.youtube`
- [ ] Refactor `youtube_service.py` API layer to `make_youtube_client`; keep cache/upload/dashboard orchestration calling the seed client.
- [ ] `[F]` Formalize `set_thumbnail` + `get_processing_status` into seed `noctusai_lib.integrations.youtube` (Protocol+Fake+Real+factory). Pilot-cadence: seed change → erp·therapy·social-wiring+core green gate.
- [ ] Tests green (youtube/video/upload/dashboard suites).

### Phase 4 — Calendar + Drive API → seed integrations
- [ ] Replace `services/calendar/*` + `services/drive_api/*` adapters with `noctusai_lib.integrations.{google_calendar,google_drive}`; reuse seed Fakes for test parity. Tests green.

### Phase 5 — Cleanup, doc reconcile, verify
- [ ] (If Phase-0 says in-scope) fold thin youtube surface into `modules/` — resolve app-level-vs-`modules/` asymmetry; else confirm the named fast-follow filed.
- [ ] Reconcile `MASTER-PROMPT.md` / `README.md` (doc⊥code → doc=true; remove the drift marker).
- [ ] Full verify: `pytest` (social-wiring + seed + pilots erp·therapy·core if seed changed) · frontend `tsc --noEmit` + `vite build` · keeper `--review` · `noctus.hound.scan` · KB sync · three-way-sync any methodology learnings.

---

## 7. Open questions

1. **At-rest bundle shape decrypts under seed store?** — Phase 0 / to-discover. *Rec:* very likely (DDL comment == seed docstring verbatim, same Fernet primitive); Phase 0 decrypts one row to confirm. If not → one-time re-encrypt sub-task in Phase 1.
2. **`set_thumbnail` / `get_processing_status` — seed-formalize vs product wrapper?** — decided in Phase 3. *Rec:* **formalize into seed** (both are YouTube-generic, Protocol-shaped; upload-status is broadly useful; re-forking violates the rule that drove this project).
3. **Fold youtube into `modules/` this project or fast-follow?** — Phase 0 decides. *Rec:* fast-follow `social-wiring-youtube-modularize` unless trivially cheap post-refactor (keep this project's blast radius on the seed-consume substitution).
4. **Branch?** — *Rec:* dedicated `feat/social-wiring-google-seed-consume` off `origin/main` (refactor ships independently; the YouTube-feature branch forks after — matches refactor-first §2). Decide at "go".

---

## 8. Dependencies & blockers

- **Fernet key access** — Phase 0 needs the product Fernet key to decrypt-test a sample row (env / `.env`).
- **Seed pilot gate** — the Phase-3 `[F]` seed formalization ripples; pilots `erp-imobiliario` · `therapy-platform` · `social-wiring` (+ `core`) must stay green before non-pilots (`feedback_pilot_products_first`).
- **Sequencing** — the YouTube feature is blocked on this project's close (user decision §2).

---

## 9. Success criteria

- `services/credential_store.py`, `services/calendar/*` hand-rolled adapters, `services/drive_api/*` hand-rolled adapters, and `youtube_service.py`'s forked API/OAuth layers are **deleted**; replaced by seed-seam consumption.
- `grep -rl 'googleapiclient\|build("youtube"' products/social-wiring/backend/app` → only thin wrappers, no forked clients.
- `cd products/social-wiring/backend && pytest` fully green (no hang, no skip-as-hide); frontend `vite build` clean.
- Seed youtube gaps formalized (Protocol+Fake+Real) with pilots green.
- `MASTER-PROMPT.md` "Seed seams consumed" is **true** (doc⊥code resolved; drift marker removed).
- Zero credential data loss (existing encrypted rows decrypt under the seed store).

---

## 10. How to use this plan

- `cd` to a fresh worktree off `origin/main` on branch `feat/social-wiring-google-seed-consume` (recommended §7.4) — NOT main, NOT the feature branch.
- Phase 0 FIRST: decrypt-test one `credentials` row + enumerate consumers + read seed `__all__`. Revise §6 loud if findings invalidate it.
- Phase-by-phase; pause for "continue" between phases unless throughput is requested.
- Phase order is dependency-correct (vault → oauth → youtube → calendar/drive → cleanup) — do not reorder without re-checking the shared-root dependency.
- AST-first (libcst); tests are the merge oracle, not greps.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-19 | Filed after interrogation (scope=full-stack, sequence=refactor-first — AskUserQuestion §2). Evidence-grounded: ~2,357 LoC fork quantified; seed seams verified shipped; credential-table compat confirmed (clean refactor, no data migration). Sibling `social-wiring-absorption-debt` confirmed a different debt class. Doc⊥code drift marker added to MASTER-PROMPT same session. | Claude (architect) |
