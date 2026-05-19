# social-wiring-google-seed-consume — Project Document

> **Living document.** Revise phases, fold in optimizations, update §11 as work
> lands. Written for a **zero-context reader** — assume the next agent has not
> seen the conversation that produced this.

- **Created:** 2026-05-19
- **Last updated:** 2026-05-19
- **Status:** Phase 0 ✅ → **Phase 1 dispatching** (seed `[F]` token_store table-shape seam — Wave-1 engineer surfaced a tree-verified seed gap; Phase 1 re-scoped to consume it + 40-site metadata-map migration). Throughput mode ("resolve it all"). Isolated worktree `../noctusai-wt-sw-google` on `feat/sw-google-seed-consume` (main tree parallel-agent-contended — do NOT execute there).
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
   youtube ∧ calendar ∧ drive ∧ oauth — refactor it (Phase 2) before the
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
- Replace hand-rolled OAuth (`calendar/oauth_adapter.py`, `drive_api/oauth_adapter.py`, youtube OAuth flow) → `noctusai_lib.security.oauth` (`GoogleProvider` + generic `oauth_router` + `CallbackHook` persisting via the Phase-2 store).
- Replace `youtube_service.py` API layer → `make_youtube_client`; keep `video_cache_service`/`upload_service`/`dashboard_service` orchestration calling the seed client.
- Replace `services/calendar/*` + `services/drive_api/*` API adapters → `noctusai_lib.integrations.{google_calendar,google_drive}`.
- Formalize the 2 seed gaps (`set_thumbnail`, `get_processing_status`) into `noctusai_lib.integrations.youtube` (Protocol+Fake+Real).
- Reconcile `MASTER-PROMPT.md` / `README.md` (doc⊥code → doc=true).

**Out of scope (for now — with reason):**
- The actual new YouTube **feature** — sequenced AFTER this (user decision §2); a separate effort on the clean surface.
- `services/meta/*` — Meta adapter, not Google-stack; separate recurrence if it exists. Note in Phase 0; file a fast-follow if hand-rolled.
- Folding youtube app-level code into a `modules/youtube/` package (the app-level-vs-`modules/` asymmetry) — **decided in Phase 0**: include in Phase 6 if cheap post-refactor, else named fast-follow `social-wiring-youtube-modularize`.
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
**Phase 0 maps every current external URL/redirect** so Phase 3 preserves them
(behavior-preserving principle §3.2).

---

## 6. Implementation phases

Phase-by-phase cadence (default). Status icons per template legend.
`[F]` formalize · `[R]` refactor · `[A]` accept.

### Phase 0 — Audit & encryption-format verification ✅ (2026-05-19, architect-owned)
- [x] **Credential compat — PROVEN at code level (stronger than one live row).** social-wiring `credential_store.encrypt_tokens` = `Fernet(json.dumps(tokens,separators=(',',':')).encode).decode`; `decrypt_tokens` = `json.loads(Fernet.decrypt(...))`. Seed `encrypted_tokens.encrypt` = plain `Fernet(key).encrypt(plaintext).decode('ascii')` — **NO version prefix / envelope**; seed `token_store` = `json.loads(decrypt(row["encrypted_tokens"],key))`. **Identical envelope; `json.loads` is whitespace-agnostic so compact-separator rows parse fine.** ⇒ existing rows decrypt cleanly under the seed store. **Zero re-encrypt, zero data migration. §7.1 RESOLVED.**
- [x] **Consumers enumerated — ~12 confirmed.** 9 routers (`google,whatsapp,meta,settings,dashboard,upload,chat,videos,calendar`_router.py) + `services/dashboard_service.py` (takes `credential_store: CredentialStore` param) + `services/whatsapp_intake_service.py` (~5 `CredentialStore(self._admin, settings.encryption_key)` constructions feeding `get_calendar_adapter`/`get_drive_adapter`). Uniform shape: `CredentialStore(<supabase_client>, settings.encryption_key)` positional + `credential_store=` kwarg into services. **Note:** `meta_router.py:95` also constructs the vault → Phase 1 swaps the store construction there too (shared vault); the Meta *integration* stays out of scope.
- [x] **Seed surface mapped.** `make_credential_store(*, client=, fernet_key: bytes, table=)` (kwargs-only); Protocol = `get(org_id,provider)` · `put(org_id,provider,tokens,*,metadata=None)` · `delete(org_id,provider)` · `list_providers(org_id)` (positional `str`). social-wiring has `get(*,org_id:UUID,provider)` · `upsert(...)` · `delete(*,org_id:UUID,provider)` + internal `encrypt_tokens`/`decrypt_tokens`. `set_thumbnail`/`get_processing_status` confirmed the only genuine youtube gaps.
- [x] **OAuth route contract mapped — RESHAPES PHASE 2 (revise-loud, see below).**
- [x] `org_id UUID`→seed `str` — Phase 1 brief passes `str(org_id)`; PostgREST coerces; clean.
- [x] Decisions: extra cols (`channel_id/channel_title/scopes`) → `StoredCredential.metadata` (seed store `select("*")` ignores extras; no schema change). youtube `modules/` fold → **fast-follow** (`social-wiring-youtube-modularize`, Wave 4) — keep blast radius on substitution. `services/meta/*` → Phase-0 deferred to Wave-4 scan (Meta is not Google-stack; vault-construction touch only in Phase 2).

**Improvements:**
- Phase-0 seed-consume audits checked only the seed store **read** path; the **write** path (`put()` payload keys vs consumer DDL) was missed → caught by Wave-1 stop-before-improvise. *Deferred → resolved structurally:* Phase 1 `[F]` seed seam + findings lesson (strengthens `feedback_verify_seed_ships_it` to bidirectional shape-compat).
- `MockRequestBuilder` never validates columns ⇒ schema-shape divergence is a systemic false-green class (N≥2 with `feedback_structural_refactor_grep_blindspot`). *Deferred → codification pipeline:* candidate `check_*` diffing seed-adapter write-payload keys vs consumer migration DDL; routed to phase_learnings + surfaced to user. Interim mitigation baked into Phase 1 (payload⊆columns contract assertion).
- The "extra cols fold into `metadata`" Phase-0 decision was under-specified (assumed the seed store had a writable `metadata` column on this table). *Applied:* §6/§7 corrected in-flight (Phase 1 + Q6); no silent carry-forward.

> **⚠️ §6 REVISED 2026-05-19 (Phase 0 finding — revise-loud per CLAUDE/projects.md).** Seed `oauth_router` **hardcodes** `APIRouter(prefix="/api/oauth")` + `/{provider}/{authorize,callback,refresh,revoke}`. social-wiring's **live registered redirect URIs** are `/api/youtube/oauth/callback` and `/api/calendar/oauth/callback` (`settings_router.py:228` explicitly warns *"relocating breaks every existing consent"* — they are registered in Google Cloud Console). The seed router offers **no prefix/path override** → a naive swap is **production-breaking + hard-to-reverse** (orphans every existing OAuth consent). This is a **seed gap** → Phase 2 gains a `[F]` sub-task: formalize a `prefix=`/`redirect_path=` seam into `noctusai_lib.security.oauth.oauth_router` (the canonical "absorbed product carries pre-registered OAuth redirect URIs" need — seed-first, pilot-gated). Phase 2 is now seed-work-first, then consume.

> **⚠️ §6 REVISED 2026-05-19 #2 (Wave-1 engineer blocker, tree-verified — revise-loud).** Phase 0 audited the seed store **read** path (`select("*")` ignores extras — correct) but NOT the **write** path. `SupabaseCredentialStore.put()` (`supabase_store.py:125`) **unconditionally** writes `"metadata": {...}`; the seed's documented table contract requires `metadata jsonb`. `social_wiring.credentials` has **no `metadata` column** — instead it has denormalized `channel_id/channel_title/scopes`, and **40 consumer sites** read `StoredCredential.channel_id/.channel_title/.scopes` as first-class fields. Real PostgREST `put()` → PGRST204 (100% write failure); `MockRequestBuilder` doesn't model columns ⇒ **false-green** under pytest. Phase 0's "fold extras into `metadata`" is unrealizable without a seed seam. **Exact same class as the Phase 3 `oauth_router` seam** (absorbed product whose table predates the seed contract). Resolution = a predecessor seed `[F]` phase, NOT a product shim / NOT a silent schema migration. Phase 0's §7.1 "clean refactor" stands for **crypto + read**; the **write data-model** needs the seam below.

> **Phase renumber 2026-05-19 (tooling-compat — see §11 / findings):** the
> predecessor seed seam was briefly "Phase 1"; `check_phase_state_consistency`
> parses `### Phase 1` as integer `Phase 0` (regex `^### Phase\s+(\d+)\b`),
> colliding with the shipped Phase 0. Fractional phase numbers are unsupported
> by the gate ⇒ renumbered to integers: seed-seam = **Phase 1**, old 1–5 → 2–6.
> Phase 0 (audit) unchanged.

### Phase 1 — `[F]` Seed `token_store` table-shape seam (predecessor; pilot-gated)
- [ ] Extend `noctusai_lib.security.token_store` (Protocol+Fake+Real+factory) with **back-compat-defaulted** table-shape config on `make_credential_store` / `SupabaseCredentialStore`:
  - `metadata_column: str | None = "metadata"` — `None` ⇒ omit the JSON metadata column entirely from `put()` payload + `_row_to_stored` (table has none).
  - `metadata_columns: dict[str,str] | None = None` — map `StoredCredential.metadata` keys ↔ discrete physical columns (e.g. `{"channel_id":"channel_id","channel_title":"channel_title","scopes":"scopes"}`): `put()` flattens those keys to columns, `get()`/`_row_to_stored` re-inflates them back into `.metadata`. Unmapped keys still go to `metadata_column` (if set).
  - **Defaults preserve today's behavior exactly** (`metadata_column="metadata"`, `metadata_columns=None`) → zero existing-consumer impact; additive.
- [ ] Update seed Fake to mirror the same mapping (test parity). Colocated seed tests for: omit-metadata-column, column-map round-trip, default back-compat.
- [ ] Pilot-gate: `pytest` for any token_store consumer in pilots erp·therapy·social-wiring+core stays green (seam is additive-with-defaults → expected no-op for them; verify, don't assume).

### Phase 2 — Credential vault → seed `token_store` (shared root; consumes Phase 1)
- [ ] Replace `services/credential_store.py` with `make_credential_store(client=<supabase>, fernet_key=settings.encryption_key.encode(), table="credentials", metadata_column=None, metadata_columns={"channel_id":"channel_id","channel_title":"channel_title","scopes":"scopes"})`. Map: `.upsert(...)`→`.put(str(org_id),provider,tokens,metadata={"channel_id":…,"channel_title":…,"scopes":…})` · `.get(org_id=,provider=)`→`.get(str(org_id),provider)` · `.delete(...)`→`.delete(str(org_id),provider)`.
- [ ] Migrate the **40** `.channel_id/.channel_title/.scopes` field-reads + `channel_id=/channel_title=/scopes=` kwargs → `StoredCredential.metadata["channel_id"]` etc. (libcst; behavior-preserving — the Phase-1 column-map keeps them in the same physical columns).
- [ ] **Verify no external caller of `encrypt_tokens`/`decrypt_tokens`** (engineer recon CONFIRMED: internal-only + the module's own unit test — clean; just re-confirm post-edit).
- [ ] Migrate the ~12 store-construction consumers (9 routers + dashboard_service + whatsapp_intake_service ×5 + meta_router) to the factory — libcst.
- [ ] `git rm` `credential_store.py`; `pytest` green. **Anti-false-green:** add one real-PostgREST-shape contract assertion (payload keys ⊆ `credentials` columns) so the mock blind spot can't hide a column mismatch.

### Phase 3 — Seed `oauth_router` prefix seam `[F]`, then OAuth lifecycle consume
- [ ] **`[F]` SEED FIRST:** add a `prefix=` (default `"/api/oauth"`) + per-provider `callback_path` override to `noctusai_lib.security.oauth.oauth_router` so legacy registered redirect URIs are preservable. Protocol+Fake+Real+factory untouched; pilot-gate (erp·therapy·social-wiring+core green).
- [ ] Replace `calendar/oauth_adapter.py` + `drive_api/oauth_adapter.py` + youtube OAuth flow with `GoogleProvider` + `oauth_router(..., on_callback=<persist via Phase-2 store>)` mounted to **preserve** `/api/youtube/oauth/callback` + `/api/calendar/oauth/callback` exactly (Phase-0 contract — DO NOT relocate). Tests green.

### Phase 4 — YouTube API → seed `integrations.youtube`
- [ ] Refactor `youtube_service.py` API layer to `make_youtube_client`; keep cache/upload/dashboard orchestration calling the seed client.
- [ ] `[F]` Formalize `set_thumbnail` + `get_processing_status` into seed `noctusai_lib.integrations.youtube` (Protocol+Fake+Real+factory). Pilot-cadence: seed change → erp·therapy·social-wiring+core green gate.
- [ ] Tests green (youtube/video/upload/dashboard suites).

### Phase 5 — Calendar + Drive API → seed integrations
- [ ] Replace `services/calendar/*` + `services/drive_api/*` adapters with `noctusai_lib.integrations.{google_calendar,google_drive}`; reuse seed Fakes for test parity. Tests green.

### Phase 6 — Cleanup, doc reconcile, verify
- [ ] (If Phase-0 says in-scope) fold thin youtube surface into `modules/` — resolve app-level-vs-`modules/` asymmetry; else confirm the named fast-follow filed.
- [ ] Reconcile `MASTER-PROMPT.md` / `README.md` (doc⊥code → doc=true; remove the drift marker).
- [ ] Full verify: `pytest` (social-wiring + seed + pilots erp·therapy·core if seed changed) · frontend `tsc --noEmit` + `vite build` · keeper `--review` · `noctus.hound.scan` · KB sync · three-way-sync any methodology learnings.

---

## 7. Open questions

1. ~~At-rest bundle shape decrypts under seed store?~~ — **✅ RESOLVED Phase 0** (code-proven: identical Fernet(JSON) envelope, no version prefix; `json.loads` whitespace-agnostic). Clean refactor, zero data migration.
2. **`set_thumbnail` / `get_processing_status` — seed-formalize vs product wrapper?** — decided in Phase 3. *Rec:* **formalize into seed** (both are YouTube-generic, Protocol-shaped; upload-status is broadly useful; re-forking violates the rule that drove this project).
3. ~~Fold youtube into `modules/` this project or fast-follow?~~ — **✅ DECIDED Phase 0:** fast-follow `social-wiring-youtube-modularize` (Wave 4) — keep blast radius on the seed-consume substitution.
4. ~~Branch?~~ — **✅ DECIDED:** `feat/sw-google-seed-consume` off `origin/main` (clean isolated worktree at `../noctusai-wt-sw-google`; the contended main-tree branch `feat/social-wiring-google-seed-consume` was abandoned due to parallel-agent contention). Carries the cherry-picked pre-commit fix `a27843e2`.
5. **seed `oauth_router` prefix/path seam** (Phase 0 finding) — *Decided:* **`[F]` formalize** into the seed in Phase 3 (legacy registered redirect URIs cannot move; the seed router currently hardcodes `/api/oauth`). Pilot-gated. Canonical "absorbed product with pre-registered OAuth URIs" need — seed, not product shim.
6. **NEW — seed `token_store` table-shape seam** (Wave-1 engineer blocker, tree-verified) — *Decided:* **`[F]` formalize** as predecessor **Phase 1** (`metadata_column=None` + `metadata_columns={…}` map, back-compat-defaulted, pilot-gated). The absorbed `credentials` table predates the seed `metadata jsonb` contract + carries denormalized `channel_id/title/scopes` (40 consumer reads). Same class as Q5. Re-fork / silent schema-migration rejected (project thesis + §5 "no schema change").

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
| 2026-05-19 | **Parallel-agent contention** in shared main tree (foreign commits on the first branch, live `.git/index` mutation). STOPPED per multi-agent-shared rule, surfaced, user chose isolated-worktree+dispatch. Re-based to clean isolated worktree `../noctusai-wt-sw-google` on `feat/sw-google-seed-consume` off `origin/main@000620a2`; scaffold committed `78825fdf`; pushed dispatch base. | Claude (architect) |
| 2026-05-19 | **Pre-commit hook** (user-flagged): cherry-picked parallel session's `a27843e2` (scoped KB-restage fix, hook-only, original authorship preserved) → `07f3c8e6`; verified shared active hook already = fixed (symlink → main tree); re-pushed base. | Claude (architect) |
| 2026-05-19 | **Phase 0 ✅** (architect-owned audit). Credential compat code-proven (zero data migration, §7.1 resolved). ~12 consumers + seed surface mapped. **§6 revised-loud:** seed `oauth_router` hardcodes `/api/oauth` but legacy registered redirect URIs can't move → Phase 2 gains a `[F]` seed-prefix-seam sub-task. §7 Q1/Q3/Q4 resolved, Q5 added. | Claude (architect) |
| 2026-05-19 | **Phase renumber + tooling finding.** `check_phase_state_consistency` parses `### Phase 0.5` as integer `Phase 0` (`^### Phase\s+(\d+)\b`) → collided with shipped Phase 0, blocked the commit (gate working). Renumbered: audit=Phase 0; seed-seam=Phase 1; vault=2; oauth=3; youtube=4; cal/drive=5; cleanup=6. Prior §11 rows keep their as-written wording (history); this row is the pointer. **Codification candidate:** convention forbids fractional phases OR the regex handles `\d+(\.\d+)?` — routed to findings/phase_learnings. | Claude (architect) |
| 2026-05-19 | **Wave-1 engineer SW-W1 blocked correctly (stop-before-improvise).** Surfaced + I tree-verified: seed `put()` unconditionally writes a `metadata` column the absorbed `credentials` table lacks (40 denormalized-field consumers) → real PostgREST 100% write-fail, mock false-green. Phase 0 missed the write path. **§6 revised-loud #2:** inserted predecessor **Phase 1** `[F]` seed `token_store` table-shape seam (`metadata_column`/`metadata_columns`, back-compat-defaulted, pilot-gated); Phase 1 re-scoped to consume it + 40-site metadata-map migration + anti-false-green payload⊆columns assertion. §7 Q6 added. Engineer authored zero code (recon-only, correct). Codification candidate routed (payload-vs-DDL keeper). | Claude (architect) |
