# meta-video-reels-publish — Project Document

> **Filed 2026-05-20** as the **§2.13a class-1 external-blocker** follow-up to `media-creator-w2-4` close-out. User explicitly authorized filing because the blocker is structural: the Meta video / Reels publish flow uses a different Graph contract (resumable upload + async processing-status poll) than the image publish flow, AND no consumer has yet surfaced a "we need to publish a video" requirement. Self-contained (durable-docs rule). Symbol-first authoring per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-24
- **Status:** ⏳ **SEED SHIPPED** (Phases 1+2+4 done 2026-05-24) — Protocol+Fake+Real+poll helper+tests+KB live in `noctusai_lib.integrations.meta`. Phase 3 (consumer wiring in `social-wiring/media_creation/publish_service.py`) is the remaining thin step, gated on a `format='video'` consumer surfacing.
- **Owner / stakeholders:** USER (joaoraphaelsst) · architect
- **Related docs:**
  - `KB § INTEGRATIONS/meta.md` § publish methods (the image-publish surface this extends)
  - `seed/lib/backend/noctusai_lib/integrations/meta/oauth_adapter.py` — the live image-publish code shape to mirror
  - `products/social-wiring/backend/app/modules/media_creation/services/publish_service.py` — first image-publish consumer; will extend with a video target when this ships
  - `KB § PATTERNS/seed-fake-real-adapter.md` — Protocol + Fake + Real + factory shape (which this MUST follow)
- **Project slug:** `meta-video-reels-publish` (root `projects/` — cross-product seed extension)

---

## 1. Context & Purpose

The image-publish surface (`publish_facebook_post` / `publish_instagram_media` / `publish_instagram_carousel`) ships in `noctusai_lib.integrations.meta` and works end-to-end on the Fake + Real adapters. It covers **photos + carousels** of photos. It does NOT cover **video** or **IG Reels**.

**Why video is structurally different.**
- IG video / Reels publish requires a **resumable upload** flow: `POST /{ig-user}/media?media_type=REELS&video_url=<...>` returns a creation id whose container is in `IN_PROGRESS` state — Graph processes the video asynchronously. The publisher MUST poll `GET /{creation-id}?fields=status_code` until `FINISHED` (`ERROR` raises) BEFORE calling `media_publish`. Wait can be 0-30+ seconds.
- FB Page video upload uses `POST /{page-id}/videos` with multipart upload (or `file_url` for hosted assets); Reels via `POST /{page-id}/video_reels` with a similar processing-status flow.
- Both surfaces require additional Meta App Review scopes — `instagram_content_publish` covers IG Reels, but FB Page video posting may need different scope review depending on the surface.

**Why this is a separate project (not inline to `meta-app-review-publish-scopes`).**
- The code shape is genuinely new (poll-until-ready helper + new value objects + Real adapter polling loop with timeout + Fake state machine).
- The consumer demand signal is N=0 today. `media_creation.format` allows `'video'` in the DB CHECK constraint but no pipeline emits video assets yet.
- Building it pre-emptively is the **seed-ahead-without-N1-consumer** anti-pattern — except for cross-cutting concerns the user explicitly authorizes (like Gmail).

**This project ships the seed extension + its first consumer when a consumer materializes.**

---

## 2. Confirmed constraints

- **No consumer today (N=0).** This project does NOT execute until either (a) `media_creation` extends to video output, or (b) a different product surfaces a video-publish need.
- **Resumable-upload + status-poll contract** — fundamentally different shape than image publish. Cannot piggyback on existing methods.
- **App Review scope coverage** — `instagram_content_publish` (already covered by sibling project `meta-app-review-publish-scopes`) gates IG Reels too; FB video may need additional review.
- **Polling timeout discipline** — the Real adapter MUST cap polling (e.g., 90s) and raise a typed `MetaGraphError` on timeout, never block indefinitely. Same gated-capability-honesty principle as the App-Review gate.

---

## 3. Design principles

1. **Mirror the image-publish shape exactly.** Protocol method per surface (IG Reel, FB Video, FB Reel) + Fake (deterministic, instant-ready) + Real (poll-until-ready with timeout + propagated typed errors) + factory injection. Per `KB § PATTERNS/seed-fake-real-adapter.md`.
2. **Lift the poll-until-ready helper to `_meta_api`** — it will be reused across IG Reels and FB Video. One implementation, two callers.
3. **Surface processing status to the consumer.** The Real adapter returns a `PublishedMedia` with `processing_duration_ms` set, so consumers can log / surface for slow renders.
4. **No new App Review scope assumption.** Use the same scope set the image publish requires unless Meta documents otherwise.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Contract identical for every product?** YES — every product wanting to publish video will want the same shape (`publish_instagram_reel(ig_user_id, video_url, caption=None)`).
2. **Data source product-specific?** NO — Graph API uniform.
3. **Placement product-specific?** NO — `noctusai_lib.integrations.meta`.
4. **Visibility / permission rule the same?** YES — per-user OAuth + App-Review-gated scope.
5. **Seam already exists in seed?** PARTIAL — Protocol exists (extend it); Fake/Real publish flow exists for images (don't reuse — different contract); poll-until-ready helper does NOT exist.
6. **Default-on or opt-in?** OPT-IN — only products that need video publish call it.

**Litmus — per-product code count:** **0 lines** new in product code. Consumer wires through the existing service-injection pattern.

---

## 4. Scope

**In scope (when project executes):**
- Extend `MetaAdapter` Protocol with:
  - `publish_instagram_reel(ig_user_id, video_url, caption=None) -> PublishedMedia`
  - `publish_facebook_video(page_id, video_url, description=None, *, as_reel: bool=False) -> PublishedPost`
- `_meta_api.poll_media_status(creation_id, *, token, timeout_seconds=90)` helper — used by both methods on the Real adapter.
- Fake: deterministic instant-ready simulation (record on `published_media`).
- Real: full Graph implementation with poll-until-ready, timeout enforcement, typed errors on `ERROR` status, `processing_duration_ms` populated.
- Seed tests covering: Fake records + bounds (e.g. video URL required), Real happy path (mock 2-step poll → FINISHED), Real timeout path, Real `ERROR` status path, Real scope-absent → `requires_app_review`.
- Consumer extension (when the demand surfaces): `social-wiring/media_creation/services/publish_service.py` accepts `target='instagram_reel'` / `'facebook_video'` / `'facebook_reel'`; the `mc_posts.published_target` CHECK constraint widens to allow the new enums.

**Out of scope:**
- Hosted upload (raw multipart bytes) — `video_url` only in v1; consumer uploads to Supabase Storage / a CDN first.
- Auto-transcoding (the video must meet IG / FB spec — aspect ratio, length, codec — at upload time).
- Long-form video (>60s for Reels, >90s for IG Feed, etc.) — surface as separate target if needed.
- The Meta App Review submission for video scopes — covered by `meta-app-review-publish-scopes` if the same scope set applies, or a sibling project if Meta requires additional review.

---

## 6. Implementation phases (when executed)

### Phase 1 — Seed extension (Protocol + Fake) ✅
- [x] Add Protocol methods on `MetaAdapter` (`publish_instagram_reel`, `publish_facebook_video`).
- [x] Implement on `FakeMetaAdapter` (deterministic, instant-ready, records on existing `published_media` / `published_posts` lists).
- [x] Fake tests: records-call + bounds (empty video_url rejected).

**Improvements:** none — clean Protocol+Fake mirror of the existing image-publish surface.

### Phase 2 — Real adapter + polling helper ✅
- [x] Implement `_meta_api.poll_media_status(creation_id, *, access_token, timeout_seconds=90, poll_interval_seconds=2, transient_retries=3, sleep=time.sleep)`.
- [x] Implement `MetaOAuthAdapter.publish_instagram_reel` (3-step: `media_type=REELS` container → poll → `media_publish`).
- [x] Implement `MetaOAuthAdapter.publish_facebook_video` (unified `as_reel` flag: `/videos` synchronous-or-poll vs `/video_reels` start→poll→finish).
- [x] Real tests: happy path (mocked `httpx.get`/`httpx.post` cycles) · timeout path · `ERROR`/`EXPIRED` status path · scope-absent (`requires_app_review`) path · transient-5xx-retry path.

**Improvements:** factored the poll loop into a shared `_meta_api.poll_media_status` helper (reused by both the Reel and video paths) instead of duplicating the IN_PROGRESS→FINISHED loop per method.

### Phase 3 — Consumer wiring (gated on N≥1 consumer) ⏳ REMAINING
- [ ] Extend `social-wiring/media_creation/services/publish_service.py` with new target enums (`instagram_reel` / `facebook_video` / `facebook_reel`). **The remaining thin step** — deferred here because (a) the project's own gate ("awaits a consumer", N=0 video-output pipeline) and (b) Engineer E was concurrently refactoring `products/social-wiring/` backend (file-disjoint discipline).
- [ ] Widen `mc_posts.published_target` CHECK constraint via additive migration.
- [ ] Consumer tests: 422 unsupported-target (only `'video'` format), 200 fake-path, persisted state.

### Phase 4 — Three-way sync ✅ (seed half)
- [x] `KB § INTEGRATIONS/meta.md` §1 publish-methods section extended (2 video methods + `poll_media_status`) + value-objects table (`MediaProcessingStatus`).
- [x] `KB § INTEGRATIONS/meta.md` §5 video / Reels row updated "out-of-scope v1" → **SHIPS** (behind same App Review scope).
- [x] Memory note `feedback_meta_video_reels_publish_shipped` — written 2026-05-24 (architect-side).

**Improvements:** none — doc + memory sync only.

---

## 7. Open questions

1. **Trigger condition.** When does this project unfreeze from `FILED` → `IN PROGRESS`? Recommendation: (a) `media_creation` adds a video-output pipeline, OR (b) a different product files a `publish-video` need. Either is sufficient.
2. **FB Page Reel vs FB Page Video — separate targets or unified `as_reel: bool` flag?** Recommendation: unified flag — same endpoint family (`/video_reels` vs `/videos`), same Protocol method shape, easy boolean discriminator.
3. **Polling timeout default.** Recommendation: 90s (covers typical IG Reels processing). Configurable per-call. Raise `MetaGraphError("video_processing_timeout")` on timeout.
4. **Re-poll on transient HTTP 5xx during status read?** Recommendation: yes, with capped retries (e.g. 3) via the existing `RetryPolicy` seed seam. Surface unrecoverable 5xx as `MetaGraphError`.

---

## 8. Dependencies & blockers

- **Hard:** A consumer surfacing a video-publish need (currently N=0).
- **Soft:** `meta-app-review-publish-scopes` approved first (so the Real adapter doesn't immediately raise `requires_app_review` on every test against a real account). Not blocking for code work — only for activation smoke.

---

## 9. Success criteria

- Protocol + Fake + Real adapters ship the video / Reel publish surface.
- Polling helper handles ready / timeout / error states; never blocks indefinitely.
- Real adapter respects the App-Review gate (typed error, never silent).
- First consumer publishes one IG Reel + one FB Video end-to-end on a sandbox tenant (when activation smoke runs).
- `KB § INTEGRATIONS/meta.md` reflects the new surface.

---

## 10. How to use this plan

Project is FILED, not yet dispatched. When a consumer surfaces (or the user signals "start"):
1. Fresh worktree off `origin/main`.
2. Execute Phase 1 + Phase 2 (seed extension + Real) — likely a single engineer dispatch (~300-500 LoC across 3 seed files + 1 test file).
3. Phase 3 (consumer wiring) waits on a specific consumer.
4. Phase 4 ships with Phase 3.

Per the inline-cutoff rule: this is too large to inline-dispatch in a sibling close-out (>100 LoC + multi-file + multi-phase). Project execution is the right destination.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-24 | Seed extension shipped (Phases 1+2+4): `publish_instagram_reel` + `publish_facebook_video` (Protocol+Fake+Real) + `poll_media_status` async-poll helper + `MediaProcessingStatus` value object + `processing_duration_ms` on `PublishedMedia`/`PublishedPost` + 19 new seed tests (107 meta-dir tests green) + KB §1/§5 sync. Phase 3 consumer wiring is the remaining thin step (gated on a `format='video'` consumer + file-disjoint from concurrent social-wiring refactor). | Engineer F |
| 2026-05-20 | Filed per user's explicit request as a class-1 external-blocker follow-up to `media-creator-w2-4` close-out. The image-publish surface is live; video / Reels uses a structurally different Graph contract (resumable upload + processing-status poll) and has N=0 consumers today. | Architect |
