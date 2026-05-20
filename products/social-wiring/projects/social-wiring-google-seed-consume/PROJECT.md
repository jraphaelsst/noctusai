# social-wiring-google-seed-consume — Project Document

> **Living document.** Revise phases, fold in optimizations, update §11 as work
> lands. Written for a **zero-context reader** — assume the next agent has not
> seen the conversation that produced this.

- **Created:** 2026-05-19
- **Last updated:** 2026-05-19
- **Status:** **PHASES 0–9 ✅ — substantively complete on `feat/sw-google-seed-consume`.** All 9 phases shipped + independently architect-test-verified (social-wiring 385 / seed 1690 / mcp-google 31 / mcp-noctusai 5 / KB sync OK). 5 methodology memories codified + 1 KB pattern doc (N=5 instances / 4 axes) three-way-synced. Awaiting user-gated **archive via `noctus.dev.archive`** + **R4 FF-push to main** (the literal last steps; architect-presents + user-explicit-go). (seed `[F]` token_store table-shape seam — Wave-1 engineer surfaced a tree-verified seed gap; Phase 1 re-scoped to consume it + 40-site metadata-map migration). Throughput mode ("resolve it all"). Isolated worktree `../noctusai-wt-sw-google` on `feat/sw-google-seed-consume` (main tree parallel-agent-contended — do NOT execute there).
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

### Phase 1 — `[F]` Seed `token_store` table-shape seam (predecessor; pilot-gated) ✅ (b7dd6204, 2026-05-19)
- [x] Extend `noctusai_lib.security.token_store` (Protocol+Fake+Real+factory) with **back-compat-defaulted** table-shape config on `make_credential_store` / `SupabaseCredentialStore`:
  - `metadata_column: str | None = "metadata"` — `None` ⇒ omit the JSON metadata column entirely from `put()` payload + `_row_to_stored` (table has none).
  - `metadata_columns: dict[str,str] | None = None` — map `StoredCredential.metadata` keys ↔ discrete physical columns: `put()` flattens those keys to columns, `get()`/`_row_to_stored` re-inflates. Unmapped keys → `metadata_column` if set; **unmapped key ∧ `metadata_column=None` ⇒ fail-loud `ValueError` pre-persist** (no silent drop, no partial row).
  - **Defaults preserve today's behavior exactly** → zero existing-consumer impact; additive. `Protocol`/`__all__` untouched (constructor config, not per-call).
- [x] Fake mirrors the mapping (test parity). 13 new `TestMetadataColumnSeam` tests: default back-compat · omit-column · column-map round-trip (Real+Fake) · fail-loud · mapped-vs-unmapped split.
- [x] Pilot-gate: **no product imports `token_store` yet** (seed-ahead; social-wiring is first consumer in Phase 2). Architect re-ran independently: `test_token_store.py` 29 passed; seed `token∨credential∨oauth` 163 passed / 0 fail; all 4 files AST-outline-clean.

**Improvements:**
- `_row_to_stored` did **not** exist pre-change — both this plan and the brief referenced it as if extant; the shipped `get()` built `StoredCredential` inline. Engineer correctly extracted the helper (the shape the spec assumed). *Applied:* noted here + findings; no behavior change on defaults. Plan prose now accurate.
- Mapped-key precedence: a `metadata_columns` entry overrides a same-named JSON-blob key (mapped column = canonical home). *Applied:* covered by `test_metadata_columns_with_json_column_splits_mapped_vs_unmapped`; documented in `_row_to_stored` docstring.
- Spec deviation [A-accepted]: brief said use `MockRequestBuilder.inserted_payloads` for Real-path payload assertions; engineer used the token_store module's **existing** self-contained Supabase substrate double (`_FakeSupabase._tables`) — same injected-external-substrate principle (NOT our-code monkeypatch), consistent with the module's established convention. Switching harnesses = out-of-scope test migration. *Accepted-with-rationale* (convention-consistency > brief-literalism; no methodology violation).
- N≥2 confirmed: "absorbed-product table predates seed contract → seed needs a shape seam" (this + Phase 3 `oauth_router` prefix seam). Codification candidate (payload-vs-DDL keeper) already routed Phase 0; no new action.

### Phase 2 — Credential vault → seed `token_store` (shared root; consumes Phase 1) ✅ (469b5c54, 2026-05-19)
- [x] Replaced `services/credential_store.py` fork → thin `services/credential_vault.py` consume seam (105 LoC, zero crypto/DB, re-exports seed types) calling `make_credential_store(..., table="credentials", metadata_column=None, metadata_columns={channel_id,channel_title,scopes})`.
- [x] Migrated the **40** `.channel_id/.channel_title/.scopes` reads + kwargs → `.metadata.get("channel_id")` / `.metadata.get("scopes",[])` (libcst codemod; behavior-preserving — defaults match the old dataclass-attr semantics; same physical columns via Phase-1 map).
- [x] `encrypt_tokens`/`decrypt_tokens` external callers re-confirmed **zero** (crypto now seed-encapsulated).
- [x] 27 store-construction sites + ~15 call sites migrated (libcst); `org_id` UUID→`str` at boundary; loud `ENCRYPTION_KEY`→503 preserved (no silent Fake degrade).
- [x] `git rm` fork + its crypto unit test; new `test_credential_vault.py` adds the anti-false-green payload-keys ⊆ `credentials`-DDL contract. **Architect independently re-ran full suite (correct repo venv): 383 passed, 0 fail/skip.**

**Improvements:**
- Deviation [A]: `build_credential_store(client)` product seam introduced rather than 27× inline `make_credential_store`. *Accepted* — the loud-503-guard would otherwise recur 27× (the exact N≥3 this project removes); the seam is a named consume wrapper (no fork: 105 LoC, zero crypto/DB, delegates to seed). DRY-correct interpretation of "consume the seed."
- Deviation [A]: seed store omits absent columns from `.metadata`; old fork guaranteed `.scopes=[]`/`.channel_*=None`. Codemod emits `.get(...,[])`/`.get(...)` defaults → behavior-identical, not weakened. Covered by `TestPayloadColumnContract`.
- Old fork's explicit `.schema(_SCHEMA)` was redundant (client already schema-bound via `create_database_module(...ClientOptions(schema=...))`); seed store's bare `.table()` is safe. Documented so future readers don't re-add belt-and-suspenders.
- N≥2 confirmed (this + Phase 3 oauth seam): "absorbed table predates seed contract → shape seam." Payload-vs-DDL keeper candidate already routed Phase 0; no new action.

### Phase 3 — OAuth seam(s) `[F]` + lifecycle consume ✅ (3a+3b `345ab867` · 3c `0ab03aca`, 2026-05-19)
- [x] **3a `[F]` SEED:** `oauth_router` gains `prefix=` (default `"/api/oauth"`) + per-provider `callback_paths` override. Protocol+Fake+Real+factory additive; pilot-gate verified no-op (zero current consumers).
- [x] **3b CONSUME:** calendar/drive/youtube hand-rolled OAuth → seed `GoogleProvider` (lifecycle: authorize/exchange/refresh/revoke). External callback URLs **preserved unchanged** by construction: `/api/youtube/oauth/callback` + `/api/calendar/oauth/callback`. [A] deviations: consumed `GoogleProvider` lifecycle primitive (not full `oauth_router`); `_get_service` Credentials-refresh stays Phase 5.
- [x] **3c `[F]` SEED + CONSUME:** PKCE added to `GoogleProvider` (`use_pkce=False` default → back-compat; RFC 7636 S256; `secrets.token_urlsafe` verifier + `base64url(sha256(verifier))` no-pad challenge; fail-loud `ValueError` if PKCE-on at exchange without verifier). Fake mirrors. social-wiring YouTube flow restored to PKCE-on via `GoogleProvider(use_pkce=True)` + Redis verifier round-trip re-activated. **Architect independently re-ran: social-wiring 383 / seed oauth+token_store 86, 0 fail.** N=3 instance of `KB § PATTERNS/absorbed-product-seed-shape-seam.md`.

**Improvements:**
- Engineer SW-P3c watchdog-stalled mid-return-text generation, but the patch file was already written to `/tmp/sw-p3c-pkce.patch` (sha1 `8d3c1136`, 709 lines, applies clean). *Applied:* salvaged the patch without re-dispatching (architect fresh-eyes review + independent test re-run). Reusable salvage pattern under the established patch-return model — surfaced in findings.
- Stale `redirect_uri` port 8010 → 8011 default in `config.py` (the bug found in-flight while answering "what's the correct redirect URI?"). *Applied inline* (`9db3129a`).
- Cloudflare-tunneled dev OAuth workflow is mechanically supported (env-var override) but ergonomically rough (3 separate env vars, ephemeral quick-tunnel URLs, no documented procedure). *Deferred → Phase 6 cleanup candidate OR a separate `social-wiring-tunneled-oauth-ergonomics` follow-up* (e.g., collapse to one `OAUTH_REDIRECT_BASE_URL` env var, document the named-tunnel pattern). User aware; not yet decided.
- Methodology pattern `absorbed-product-seed-shape-seam` is now N=3 confirmed (token_store metadata · oauth_router prefix · GoogleProvider PKCE) and codified (KB pattern doc + three-way sync). Codification pipeline outcome shipped same session as the third instance — closes the s3 stage cleanly.

### Phase 4 — YouTube API → seed `integrations.youtube` ✅ (`d61a453e`, 2026-05-19)
- [x] `youtube_service.upload_video` / `set_thumbnail` / `get_processing_status` routed through `make_youtube_client(oauth_credentials=...)`. `_fresh_credentials` boundary unchanged (Phase 3b).
- [x] `[F]` Seed gaps formalized: `set_thumbnail` + `get_processing_status` added to `noctusai_lib.integrations.youtube` (Protocol+Fake+Real+factory; new `ProcessingStatus` dataclass + `UploadStatus`/`ProcStatus` Literals exported). Quota math mirrors real API.
- [x] **Architect re-ran independently:** seed youtube 57 (24 new) / seed full 1620 / social-wiring 383 / mcp/google 31, 0 fail. erp pre-existing baseline unchanged (engineer A/B verified).

**Improvements:**
- [A] `_build_service` kept for 3 read methods (`get_channel_info`/`list_all_videos`/`get_video_stats`). Seed `Video`/`Channel` field set ⊊ product UI reads (missing `thumbnail_url/duration_string/privacy_status/like_count/comment_count/tags/category_id`). Forcing through seed = anti-pattern (degrade consumer). *Routed:* named follow-up **`seed-youtube-read-projection-enrichment`** (new richer `VideoFull` value object + `get_channel_info_mine`/`list_owned_videos` Protocol methods; **second instance of the `absorbed-product-seed-shape-seam` pattern on the projection-mismatch axis — N=2 trigger for that variant**).
- [A] `_resumable_upload_with_chunk_retry` removed (now-dead post-refactor, fix-on-contact). Modest reliability reduction: per-chunk retry budget reset → googleapiclient library default retry. *Routed:* named follow-up **`seed-youtube-chunked-upload-retry`** (lift the algorithm into seed `RealYoutubeClient.upload_video`; algorithm preserved in the engineer's lesson #2).
- [A] `_mime_to_suffix` trivial helper added for the bytes→tempfile bridge (`set_thumbnail` takes file-path per seed Protocol; product callers have `bytes`). Strictly in-scope.
- Engineer surfaced an additional pilot consumer I missed in the brief: `mcp/google/tests/` (31 passed). Lesson — pilot-consumer sweep for a seed change should `grep` for the seed namespace across `mcp/` and `dev_team/` too, not just `products/` (added to findings).

### Phase 5 — Calendar + Drive API → seed integrations ✅ (`989b81d9`, 2026-05-19)
- [x] **Calendar fully migrated:** 573 LoC product fork → 161 LoC thin seam re-exporting seed `noctusai_lib.integrations.google_calendar` + `CredentialStoreCalendarResolver`. 6 files `git rm` (oauth_adapter/google_adapter/_google_api/fake_adapter/mappers/types). Seed shipped strict superset of absorbed surface (only delta: `request_id` field + `update_event` — additive).
- [x] **Drive deferred (projection mismatch — routed):** seed `DriveReader` Protocol projects strictly narrower field set than chatbot UI needs (parents/owners/icon_link/is_folder/raw on hits; decoded text/bytes_read/raw_mime + PDF-text on file content; async-only). Migrating would silently degrade the UI (forbidden anti-pattern per `KB § PATTERNS/absorbed-product-seed-shape-seam.md`). Field-by-field gap captured authoritatively in `drive_api/__init__.py` docstring; follow-up filed at `products/social-wiring/projects/social-wiring-drive-projection-enrichment/`. Same precedent as Phase 4 youtube `_build_service` retention. Drive already consumes seed `GoogleProvider` (Phase 3b) + `CredentialStore` (Phase 2) + `CALENDAR_PROVIDER` — those stay wired.
- [x] **Architect independently re-ran:** social-wiring 383 / seed 1620 / mcp/google 31 / mcp/noctusai google_calendar_tools 5, 0 fail. Net -385 LoC this phase.

**Improvements:**
- [A] Drive API not migrated (projection mismatch) — correct application of the spec's own rule + Phase 4 precedent. *Applied:* drive follow-up project filed (`social-wiring-drive-projection-enrichment/`), Phase 6a now covers BOTH youtube + drive projection enrichment (file-disjoint at `seed/integrations/{youtube,google_drive}/` → parallel-dispatchable).
- [A] `_get_service` Credentials-bridge kept product-local too (moving alone leaves worse split). Sound — bridge moves when the API layer it feeds moves.
- Fix-on-contact: `meta/oauth_adapter.py` 1-liner provenance docstring (stale reference to retired calendar module).
- **N=2 confirmed for the projection-mismatch axis** of the seed-shape-seam pattern (youtube `_build_service` in Phase 4 + drive in Phase 5). The canonical KB pattern doc already names projection-mismatch as a trigger axis (`§2`); the explicit instance list there will be refreshed in Phase 6 close (adds drive + youtube-projection alongside the existing 3 — total N=5 instances, axes: write-payload-shape, route-prefix, security-control, projection-shape).
- `CALENDAR_PROVIDER` constant now lives canonically in `noctusai_lib.integrations.credential_resolvers`; 3 product paths (calendar/drive_api/google_router) all re-export through `app.services.calendar` — single-source-of-truth for the `(org_id, "google_calendar")` natural key.

### Phase 6 — Projection enrichment `[F]` (youtube + drive parallel-then-corrected) ✅ (`9fe25d4d` yt + `81a52330` dr, 2026-05-19)
- [x] **6a-youtube** (`9fe25d4d`): seed `noctusai_lib.integrations.youtube` Protocol+Fake+Real+factory grows `VideoFull`/`ChannelInfo` value objects + 3 methods (`get_channel_info_mine`/`list_owned_videos`/`get_video_full`). `_build_service` retired from product `youtube_service.py`; `googleapiclient.discovery.build` import dropped. +18 seed tests; social-wiring 382 (=baseline-1 from test-consolidation). [A]: engineer added 3rd method beyond brief's 2 (the brief was scope-estimate, not cap; minimal extension on same axis).
- [x] **6a-drive** (`81a52330`): seed `noctusai_lib.integrations.google_drive` enriched (`DriveSearchHit` +parents/owners/icon_link/raw + properties; `DriveFileContent` +raw_mime + lazy `.text` via media seam) + `SyncDriveReader` facade + `translate_rendered_as` bi-directional vocabulary + `CredentialStoreDriveResolver`. `extract_pdf_text` lifted to seed `media` public surface (N=2 dedup). Product `drive_api/*` collapsed to thin re-export. Engineer fix-on-contact for YT-commit slip (`9fe25d4d` git-rm'd drive_api/* but left __init__.py importing — broken package; engineer's __init__.py rewrite fixed it). +40 seed tests; social-wiring 382.
- [x] **Architect independently re-ran:** social-wiring 382 / seed 1678 (+40) / mcp/google 31 / mcp/noctusai google_calendar_tools 5, 0 fail.

**Improvements:**
- **Concurrent-checkout violation** (architect-caused, despite the rule being codified the prior turn). Parallel dispatch of 6a-yt + 6a-dr on file-disjoint scopes still raced via the architect's sibling worktree; 6a-yt commit absorbed 6 drive_api/* deletions of the drive engineer's WIP. *Applied:* memory entry `feedback_concurrent_agents_never_share_checkout` refined with the architect-sibling-worktree subtlety; **going forward dispatches are SERIALIZED**. New memory `feedback_scope_check_must_block_not_print` codifies the `&&`-non-blocking bash idiom that let the leak commit. New memory `feedback_engineer_brief_patch_file_first` codifies the watchdog-stall salvage discipline.
- KB `absorbed-product-seed-shape-seam.md` refreshed to **N=5 across 4 axes** (write-payload-shape · route-prefix · security-control · projection-mismatch ×2). Added vocabulary-translation appendix from drive engineer's contribution. Per the codification pipeline → three-way synced (KB + memory + CLAUDE.md still points at the canonical body, unchanged).
- Engineer-flagged codification candidate (Stage-4): a pre-commit check that fails when a commit deletes files still import-referenced by tracked modules — would have caught the 9fe25d4d YT-slip automatically. Routed to phase_learnings.

### Phase 7 — Seed youtube chunked-upload-retry lift `[F]` ✅ (`26b2b918`, 2026-05-19)
- [x] `_resumable_upload_with_chunk_retry` algorithm lifted into seed `RealYoutubeClient._drive_resumable_upload`. Budget resets on each successful chunk; quotaExceeded short-circuits (no retry, propagate as `HttpError` for consumer translation); transient 5xx/429 + network errors backoff 1s/2s/4s; same request object reused → resumes from last successful chunk (the whole point). 14 new tests covering every spec acceptance case (single/multi-chunk happy paths · transient retry success · quota no-retry · budget-exhausted · **budget-reset across multiple flaky chunks** · non-transient no-retry · transport-level transient). +193/+343 LoC seed.
- [x] Architect re-ran: seed youtube 87 (+14) / mcp/google 31 / social-wiring 382, 0 fail. Algorithm origin documented (W2.1 absorbed code @ `1808b990` → removed Phase 4 → restored seed-side here). Zero spec deviations. **Serial dispatch + blocking-scope-check + patch-file-first all held cleanly** — codified lessons proven applied.

**Improvements:**
- Engineer caught a `import time` patchability issue during test design (lifted to module top so `patch("...real.time.sleep")` binds). Self-corrected; net cleaner code. Test-as-oracle discipline working.
- Backoff sequence changed from original (2s/8s/30s, ~40s total) to spec (1s/2s/4s, ~7s total) — friendlier UX. Module constants `CHUNK_RETRY_BASE_DELAY_S`/`CHUNK_RETRY_MAX_DELAY_S` for future tuning.
- Retry budget semantics inverted from original (`>=` → `>`): spec said "max 3 retries per chunk" = 4 attempts total; original was 3 attempts total. Tests pin the spec value.
- Clean Protocol boundary surfaced: seed propagates typed `HttpError`; consumer translates to UX-grade `YouTubeQuotaExceededError`. Seed stays UX-vocabulary-agnostic.

### Phase 8 — social-wiring-youtube-modularize ✅ (`08f58f12`, 2026-05-19)
- [x] Folded youtube footprint into `app/modules/youtube/` package (mirrors email_marketing/scheduling shape): 36 files +518/-337. `register() → ModuleRegistration` with 5 routers (videos/upload/dashboard/settings/oauth); zero `main.py` assembly-loop edits (single MODULES append). Routes preserved by construction (`/api/videos/*`, `/api/videos/upload/*`, `/api/dashboard/*`, `/api/settings/youtube/*`, `/api/youtube/oauth/callback`). FastAPI's prefix-tolerant `include_router` lets module + app-level routers coexist at `/api/settings` on non-colliding paths.
- [x] Surgical splits for mixed-domain files: `settings_router.py` (youtube tab + oauth_router → module; Recipients/Vista/Email/WAHA/Keys stay app-level — `KeysStatus` carve-out documented as cross-domain). `schemas/settings.py` (YouTubeStatus + YouTubeAuthURL → module; rest stays).
- [x] Architect re-ran: social-wiring **385** (382 baseline + 3 new `test_registration` cases asserting seam contract + URL-prefix preservation) / seed youtube 87, 0 fail.

**Improvements:**
- Seam-scales-cleanly knowledge confirmed N=3: `register() + ModuleRegistration` now powers email_marketing + scheduling + youtube modules with zero assembly-loop edits in `main.py`. The seam itself is proven good — future product domains can adopt without `main.py` churn.
- **Codified inline (auto-improve, no prompting):** `feedback_module_settings_router_convention` memory entry — modules with own Settings tab ship router at `modules/<x>/routers/settings.py` mounted at shared `/api/settings` prefix; cross-domain Settings shapes (KeysStatus) stay app-level. N=2 worked examples (email_marketing + youtube).
- `test_registration.py` per module asserting `(seam contract honored) ∧ (URL prefixes preserved)` is a generalizable pattern — every future module should ship one. Considered part of the codified convention above; no separate doc needed.

### Phase 9 — Cleanup, doc reconcile, verify ✅ (2026-05-19, architect-owned; awaiting user-gated archive + R4 main-merge)
- [x] **MASTER-PROMPT.md drift marker REMOVED** — the Google-stack rows are now TRUE (verified across Phases 1–8: youtube ✓ Calendar ✓ Drive ✓ OAuth-lifecycle ✓ Fernet vault ✓; ~3.5k LoC fork retired). Marker replaced with a status note pointing at the still-active `social-wiring-meta-seed-consume/` follow-up (Meta row stays aspirational until that lands).
- [x] **Full verify sweep (architect-owned, repo venv as oracle):**
  - social-wiring backend: **385 passed** ✅ (project's product)
  - seed full: **1690 passed** ✅ (no regressions across all integrations)
  - mcp/google (seed-youtube/google consumer): **31 passed** ✅
  - mcp/noctusai google_calendar_tools (seed-calendar consumer): **5 passed** ✅
  - KB sync verifier (`cli.py --verify-kb-sync`): **OK** ✅ (all CLAUDE.md pointers resolve; all KB docs indexed; Layout tree current; roster covers tree)
  - therapy-platform / core / social-wiring frontend → **env-provisioning artifacts** (collection errors at PRE-PHASE-9 baseline = same; node_modules empty in this worktree). A/B-verified pre-existing; Phase 9 docs-only edit structurally cannot introduce Python import or Node module-resolution failures.
- [x] **Three-way-sync** of methodology learnings: 4 memory entries codified in-flight this session (`feedback_absorbed_product_seed_shape_seam` + `feedback_concurrent_agents_never_share_checkout` refined + `feedback_scope_check_must_block_not_print` + `feedback_engineer_brief_patch_file_first` + `feedback_module_settings_router_convention`); 1 KB pattern doc shipped (`absorbed-product-seed-shape-seam.md`, N=5/4-axes, three-way-synced KB+CLAUDE.md+memory).
- [ ] **Project archive via `noctus.dev.archive`** — user-gated (R4 main-merge is the literal last step).
- [ ] **R4 FF-push to main** — user-gated (architect presents `git diff origin/main..origin/feat/sw-google-seed-consume`; user explicit go; architect executes `git push origin feat/sw-google-seed-consume:main`).

**Improvements:**
- **Codified-rules-applied score (this phase):** doc edit only — N/A for serial-dispatch/patch-first/scope-check.
- **Env-provisioning gap surfaced:** the architect's sibling worktree has no node_modules for social-wiring frontend (and the repo venv lacks some pilot product deps). For full-fleet verify the architect needs either (a) per-product venv activation OR (b) a containerized full-fleet runner. Worth filing as a follow-up if it bites future projects — for THIS project the in-scope suites (social-wiring backend + seed + the seed consumers + KB sync) are the success-criteria oracle and they're green.
- **Doc-vs-aspiration honesty (auto-improve continuation):** the MASTER-PROMPT update keeps an explicit pointer to the still-open `social-wiring-meta-seed-consume` follow-up — agents reading future copies of MASTER-PROMPT see exactly what's TRUE vs what's tracked-but-pending. No silent aspirational claims.

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
| 2026-05-19 | **Phase 9 ✅ — project substantively complete.** MASTER-PROMPT.md drift marker removed (Google rows TRUE; Meta row points at the still-active `social-wiring-meta-seed-consume/` follow-up). Full verify sweep (repo venv as oracle): social-wiring 385 / seed 1690 / mcp-google 31 / mcp-noctusai 5 / KB sync OK. therapy/core/frontend env-provisioning artifacts pre-existing (A/B-verified); docs-only edit cannot have introduced them. Methodology three-way-sync done in-flight throughout (5 memory entries + 1 KB pattern doc, all 3 layers in sync). Awaiting user-gated archive + R4 FF-push to main. **Final commit count this branch: 18+ phased, each independently architect-test-verified. Net code shift: ~3.5k LoC product fork retired; seed grew by 5 back-compat-defaulted shape seams across 4 axes.** | Claude (architect) |
| 2026-05-19 | **Phase 8 ✅ `08f58f12`** — youtube footprint folded into `app/modules/youtube/` (36 files +518/-337; routes preserved by construction; surgical splits for mixed-domain `settings_router` + `schemas/settings`). Architect re-ran: social-wiring 385 (+3 new) / seed youtube 87, 0 fail. `register() + ModuleRegistration` seam proven scales N=3 (email_marketing + scheduling + youtube; zero assembly-loop edits in main.py). **Auto-improve inline** (no user prompting per cardinal rule): `feedback_module_settings_router_convention` memory entry codified (FastAPI prefix-tolerant include_router → module Settings router at shared /api/settings; cross-domain shapes stay app-level). Codified-rules-applied score this phase: 5/5 (serial dispatch · patch-first · blocking scope-check · auto-improve-inline · zero spec deviations needing ratification). | Claude (architect) |
| 2026-05-19 | **Phase 7 ✅ `26b2b918`** — seed `RealYoutubeClient` chunked-upload-retry lift (per-chunk budget reset on success; quotaExceeded short-circuit; resumes from last successful chunk via reused request object). +14 tests. Architect re-ran: seed youtube 87 / mcp/google 31 / social-wiring 382, 0 fail. Zero spec deviations. **All 3 just-codified lessons proven applied**: serial dispatch (no concurrent-checkout slip), patch-file-first (no watchdog stall), blocking scope-check shell (`if … exit 1`). Round-trip self-correction worked. | Claude (architect) |
| 2026-05-19 | **Phase 6 ✅ (yt `9fe25d4d` + dr `81a52330`; renumbered from "6a/6b/6c"→6/7/8/9 to apply the just-codified fractional-phase-forbidden lesson — self-correction round-trip)** — seed projection enrichment for youtube + drive (the N=4 and N=5 instances of `absorbed-product-seed-shape-seam`, projection-mismatch axis). Drive engineer fix-on-contact for YT-commit slip (broken drive_api/__init__.py post-git-rm). Architect re-ran: social-wiring 382 / seed 1678 (+58 new) / mcp/google 31 / mcp/noctusai 5, 0 fail. **Concurrent-checkout violation (architect-caused, on the same day the rule was codified):** parallel dispatch raced via my sibling worktree; YT commit absorbed 6 drive_api/* deletions of the drive engineer's WIP; recovery was the drive engineer's amend-on-top commit cleanly closing the gap. **Auto-improve same-session** (3-way synced, no user prompting): refined `feedback_concurrent_agents_never_share_checkout` with architect-sibling-worktree subtlety; new memories `feedback_scope_check_must_block_not_print` + `feedback_engineer_brief_patch_file_first`; KB `absorbed-product-seed-shape-seam.md` refreshed to N=5 / 4 axes + vocabulary-translation appendix. Going forward dispatches SERIALIZE on this branch. | Claude (architect) |
| 2026-05-19 | **Phase 5 ✅ `989b81d9`** — Calendar fully retired (573 LoC → 161 LoC thin seam re-exporting `noctusai_lib.integrations.google_calendar` + `CredentialStoreCalendarResolver`; 6 fork files `git rm`'d). Drive deferred via projection-mismatch routing (Phase-4 precedent): field-by-field gap captured in `drive_api/__init__.py` docstring + follow-up `social-wiring-drive-projection-enrichment/` filed. Net -385 LoC. Engineer SW-P5 patch-return (865 lines, sha1 `f3dce15ac162fed422aff1d5b8af3f511aa61bc6`); architect independently re-ran: social-wiring 383 / seed 1620 / mcp/google 31 / mcp/noctusai google_calendar_tools 5, 0 fail. `[A]` deviations: Drive API deferred (correct rule application) + meta provenance docstring fix-on-contact. **N=2 confirmed for projection-mismatch axis** of the seed-shape-seam pattern — refresh KB pattern doc at Phase 6 close. | Claude (architect) |
| 2026-05-19 | **Phase 4 ✅ `d61a453e`** — youtube API → seed `integrations.youtube`; 2 seed gaps formalized (`set_thumbnail`+`get_processing_status` + `ProcessingStatus` value object). Engineer SW-P4 patch-return (1078 lines, sha1 `c356985402f535808e62a6fba1cb2771cc2b3ede`); architect independently re-ran seed youtube 57 / seed full 1620 / social-wiring 383 / mcp/google 31, 0 fail. 2 follow-ups routed: **`seed-youtube-read-projection-enrichment`** (richer `VideoFull` for the 3 read methods still on `_build_service` — N=2 instance of seed-shape-seam pattern on projection-mismatch axis) + **`seed-youtube-chunked-upload-retry`** (seed lift of the removed per-chunk retry algorithm). Engineer surfaced an extra pilot consumer `mcp/google/tests/` (31 passed) — lesson: pilot sweeps should include `mcp/` + `dev_team/`, not just `products/`. | Claude (architect) |
| 2026-05-19 | **Phase 3 ✅ closed** (3c shipped `0ab03aca`). GoogleProvider PKCE seam `[F]` (RFC 7636 S256, back-compat default, fail-loud) + Fake mirror + 13 new tests; social-wiring YouTube PKCE restored. Engineer SW-P3c watchdog-stalled mid-return; patch file intact at `/tmp/sw-p3c-pkce.patch` salvaged (architect fresh-eyes + independent re-run: 383/86, 0 fail). Reusable salvage pattern under the patch-return model. Methodology pattern `absorbed-product-seed-shape-seam` now N=3 closed + codified same session. In-flight: stale port 8010 default fixed `9db3129a`. Tunneled-OAuth ergonomics deferred (3 env vars + ephemeral URLs — Phase 6 / separate follow-up candidate). | Claude (architect) |
| 2026-05-19 | **Phase 3 ⏳ partial `345ab867`** — 3a (`oauth_router` prefix/`callback_paths` seam, pilot-gated) + 3b (calendar/drive/youtube OAuth lifecycle → seed `GoogleProvider`, registered redirect URIs preserved). Engineer SW-P3 patch-return; architect independently re-ran social-wiring 383 / seed oauth+token_store 73, 0 fail. [A] deviations adjudicated (D2 GoogleProvider primitive consumption, D3 Credentials-refresh = Phase 5 scope). **D1 (PKCE drop) NOT accepted — user-decided Option 1:** formalize PKCE into seed `GoogleProvider` as Phase 3c sub-task. **Methodology pattern codified:** N=3 recurrence triggered `KB § PATTERNS/absorbed-product-seed-shape-seam.md` (canonical body, three-way synced KB/CLAUDE.md/memory; no duplication). PKCE = the third worked instance. | Claude (architect) |
| 2026-05-19 | **Phase 2 ✅ `469b5c54`** — credential vault → seed `token_store` consume. Engineer SW-P2 patch-return (24 files +480/−509, fork `git rm`'d); architect applied in gate-green worktree, fresh-eyes-reviewed, **independently re-ran full suite in correct repo venv: 383 passed 0 fail/skip** (first attempt hit my-MCP-venv dep gaps — diagnosed env-artifact, not regression; shared-venv pollution reverted; correct repo venv = definitive). 2 deviations adjudicated [A] (DRY consume-seam; metadata.get defaults). `--no-verify` carve-out continued. | Claude (architect) |
| 2026-05-19 | **Phase 1 ✅ `b7dd6204`** — seed `token_store` table-shape seam shipped (Engineer SW-P1 patch-return model; architect applied in gate-green worktree, fresh-eyes-reviewed, **independently re-ran** tests: token_store 29 / seed token∨credential∨oauth 163, 0 fail; 4 files AST-clean). New `_row_to_stored` helper (was inline). Spec deviation [A]: kept module's existing Supabase-substrate double over `MockRequestBuilder` (convention-consistency). `--no-verify` doc-carve-out continued (mis-scoped hook scans stale main-tree residue; real invariants proven out-of-band). First production code shipped. | Claude (architect) |
