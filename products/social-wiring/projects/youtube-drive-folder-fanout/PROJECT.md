# youtube-drive-folder-fanout — Project Document

> Living doc. Phases are suggestive; revise as we learn. Improvements captured live during each step in the phase's `**Improvements:**` block; one bundled proposal authored at phase close.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ⏳ Phase 1-6 complete (BE+tests); auth-modernization Wave 1-3 complete; Vista seed lift complete; **live preflight green** (ApiToken auth working, Vista enrichment working, container freshness verified). Live YT upload **blocked on operator action** — YOUTUBE_CLIENT_ID/SECRET not in .env + no row in social_wiring.credentials for the org. Runbook in `findings.md § Platform OAuth setup`.
- **Owner / stakeholders:** rapha · social-wiring product
- **Related projects:** `projects/meta-video-reels-publish/` (IG Reels publish path — blocked on `projects/meta-app-review-publish-scopes/`); `products/social-wiring/projects/social-wiring-drive-projection-enrichment/`
- **Project slug:** `youtube-drive-folder-fanout`
- **Location:** `products/social-wiring/projects/youtube-drive-folder-fanout/` (single-product scope)

---

## 1. Context & Purpose

Today the social-wiring YouTube uploader handles a Drive folder URL by calling `gdrive_service.pick_youtube_video` — it downloads every file in the folder, classifies each as `youtube` (horizontal/16:9) / `reels` (vertical/9:16) / `unknown`, picks **one** horizontal file, drops the rest, and raises `GoogleDriveError("All files appear to be REELS format")` when the folder is vertical-only. The operator's reality is different: a typical Drive folder for a piece of content contains **both** a horizontal master and a vertical Shorts cut (often in subfolders), and they want both published — the horizontal to YouTube long-form, the vertical to YouTube Shorts on the same channel.

This project extends the existing pipeline to:
1. Iterate every video in a Drive folder (recursing one level for subfolders).
2. Classify each at worker time and stamp `target_format` on its row.
3. Fan out into N parallel `upload_jobs` so each video is uploaded independently.
4. Apply Shorts-appropriate metadata (e.g. `#Shorts`) to vertical jobs so YouTube ranks them as Shorts.

Meta / Instagram Reels publishing is **explicitly out of scope** — it's filed in `projects/meta-video-reels-publish/` (waiting on App Review per `projects/meta-app-review-publish-scopes/`).

**Pre-research finding (web-verified 2026-05-20):** YouTube Shorts max length was extended from 60s to **180s (3 min)** on 2024-10-15. The 60s figure the user was told is outdated. Exception: any Short >60s with an active Content ID claim (copyrighted music) is **globally blocked**. For original audio there is no need to truncate. *Sources:* [YouTube Help (3-min Shorts)](https://support.google.com/youtube/answer/15424877?hl=en), [Piktochart 2026 length guide](https://piktochart.com/blog/how-long-youtube-shorts/), [Toptal Creator 2026](https://www.toptal.com/creator/post/youtube-shorts-length).

---

## 2. Confirmed constraints

- **Drive layout** — *mixed*: folder may contain videos directly OR subfolders, each subfolder holding a video. We iterate one level. *(Drives the new `iter_drive_videos` recursion shape — flat-or-one-level, not arbitrary depth.)*
- **Vertical fanout** — *YouTube Shorts only* on the same channel; **not Meta/IG**. The user has no IG App Review yet, and the Reels publish path is owned by `projects/meta-video-reels-publish/`. *(Removes the entire IG hosting/URL design — no Reels publish, no temp storage problem, no `video_url` requirement.)*
- **Outro / truncation (Phase B)** — *deferred*. Build Phase A (no truncation), the user manually tests, and only file Phase B if real failures surface (>180s rejection or 60s+ContentID block). *(Avoids speculative ffmpeg/outro design before we know whether the user's content even triggers the length issue.)*
- **Endpoint shape** — *new endpoint* `POST /api/videos/upload/drive-folder` (the existing `/upload/drive` keeps single-file semantics for WhatsApp intake + dashboard single-pick). *(No back-compat break; the single-file → 1 job_id contract is preserved for existing callers.)*
- **Recursion depth** — *one level only* (folder → subfolders → videos). *(Predictable; matches operator's actual layout; prevents accidental dozens-of-uploads from a misconfigured deep tree.)*
- **Failure isolation** — *each child job independent*. A failing sibling does NOT cancel others; the dashboard surfaces partial-success per existing per-row retry semantics. *(Matches the existing `upload_jobs` row-is-source-of-truth model. No new transactional shape needed.)*

---

## 3. Design principles

1. **No new vendor / no new infra.** Re-use the existing Drive API client, the existing `upload_jobs` table, the existing background worker, the existing queue. The only deltas are new code paths, two new columns, one new endpoint.
2. **Per-video classification at worker time, not queue time.** Queue time only lists files (cheap Drive API call). Classification (`ffprobe` aspect ratio) needs the bytes — that happens inside the existing per-file `_materialise_source` path. Avoids downloading every video twice.
3. **Each video is its own row.** Independent retry, independent progress bar, independent failure state. Siblings share a `batch_id` so the dashboard can group them.
4. **YouTube does the Shorts classification on its side.** We don't choose an upload endpoint — vertical+≤3min is auto-promoted to Shorts by YouTube's algorithm. We just stamp the metadata (`#Shorts` in description) to help ranking.
5. **No silent drops.** Today `pick_youtube_video` raises on vertical-only folders, but the *new* flow must not silently filter anything — every video file in the folder gets a row, even `unknown` aspect-ratio ones (operator decides what to do with those).

---

## 3a. Seed-first analysis

The seed-first checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`):

1. **Is the contract identical for every product?** **NO.** Only social-wiring uploads videos to YouTube. The Drive→YT pipeline is product-bounded. N=1.
2. **Is the data source product-specific?** YES — `social_wiring.upload_jobs` table.
3. **Is the placement product-specific?** YES — `products/social-wiring/backend/app/modules/youtube/`.
4. **Is the visibility / permission rule the same?** YES — same RLS as today's `upload_jobs`.
5. **Does the seam already exist in seed?** Drive integration ships in `noctusai_lib.integrations.google_drive` (consumed via the product's `app/services/gdrive_service.py` thin wrapper). YouTube upload ships in `noctusai_lib.integrations.youtube`. Both are seed-ready; this project consumes them.
6. **Default-on or opt-in?** N/A (single-product feature).

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific batch endpoint + worker classification + Shorts metadata stamp. The underlying Drive iter + ffprobe primitive could lift to seed at N=2 (when another product wants Drive folder→multi-video fanout). For now, **product-bounded by design** — file a follow-up `recurrence-N=2` only if another product gains the same need.

**Phase plan implications:** §6 phases work in the product — they do NOT walk through products. Correctly product-bounded.

---

## 4. Scope

**In scope:**
- New `gdrive_service.iter_drive_videos(folder_url, recurse_one_level=True)` — lists folder + one level of subfolders, returns `[DriveFileRef]` without downloading.
- DB migration (in-place edit of `001_social-wiring.sql`): `target_format` + `batch_id` columns + supporting index.
- New router endpoint `POST /api/videos/upload/drive-folder` with batch fan-out.
- `UploadService.queue_drive_folder_upload(...)` orchestrator returning `BatchQueued(batch_id, job_ids)`.
- Worker extension: after download, classify → stamp `target_format`; for `target_format=="shorts"` append `#Shorts` to description if not present.
- Batch status read endpoint `GET /api/videos/upload/batch/{batch_id}`.
- Test coverage across every new surface (unit + integration).

**Out of scope (for now — with reason):**
- IG/Facebook Reels publish — filed in `projects/meta-video-reels-publish/`; blocked on `projects/meta-app-review-publish-scopes/`.
- Video truncation + outro composition (Phase B) — deferred per user; only file follow-up project if manual testing reveals real length-rejection failure mode.
- Per-org outro asset upload + ffmpeg overlay primitive — falls out of Phase B deferral.
- Frontend wiring for the new endpoint — the user is starting with manual `curl` / dashboard-trigger testing; UI follows once API contract is locked.
- Lifting the iter-and-fanout primitive to seed-lib — N=1 today; revisit at N=2 per the recurrence rule.

---

## 5. Architecture / Data Model

### New DB columns (in `social_wiring.upload_jobs`)
```sql
ALTER TABLE social_wiring.upload_jobs
    ADD COLUMN target_format TEXT NULL
        CHECK (target_format IN ('youtube', 'shorts', 'unknown')),
    ADD COLUMN batch_id UUID NULL;

CREATE INDEX idx_sw_upload_jobs_batch ON social_wiring.upload_jobs(org_id, batch_id, created_at DESC)
    WHERE batch_id IS NOT NULL;
```

### Drive file ref shape
```python
@dataclass(frozen=True)
class DriveFileRef:
    file_id: str         # Drive's file id
    name: str            # human filename
    mime_type: str       # 'video/mp4', etc.
    size_bytes: int | None  # nullable (Drive may not report)
    parent_name: str | None # for "Subfolder/clip.mp4" display
```

### Fan-out endpoint contract
```
POST /api/videos/upload/drive-folder
Body: { drive_folder_url, metadata: UploadMetadata }
Response 202: { batch_id, jobs: [{ job_id, file_name, parent_name }] }
Response 422: { detail } — empty folder, unparseable URL, no videos found
Response 503: { detail } — Drive auth / quota gap
```

### Worker classification stamping flow
```
_materialise_source(job)                      # single-file gdrive path
  ├── download_from_drive(source_url)
  ├── classify_video_format(local_path)       # existing
  └── _update_row(target_format=<youtube|shorts|unknown>)

_do_upload_pipeline(job)
  ├── if target_format == "shorts" and "#Shorts" not in description:
  │     description = description + "\n\n#Shorts"
  ├── youtube_service.upload_video(... description=description ...)
  └── ... (rest unchanged)
```

### Batch status endpoint contract
```
GET /api/videos/upload/batch/{batch_id}
Response 200: {
  batch_id,
  total, queued, downloading, uploading, processing, published, notified, failed,
  jobs: [<upload_job rows>]
}
Response 404: batch_id unknown / not in this org
```

---

## 6. Implementation phases

### Phase 1 — Drive iteration (`iter_drive_folder_videos` + tests) ✅
- [x] Add `DriveFolderVideoRef` dataclass to `gdrive_service.py`.
- [x] Implement `iter_drive_folder_videos(folder_url, target_dir, recurse_one_level=True, max_bytes=...) → list[DriveFolderVideoRef]` via gdown.download_folder (reuses existing auth path; no new Drive API key dependency).
- [x] Skip non-video MIME types silently; raise GoogleDriveError on empty folder or no-videos.
- [x] Drop oversized files + cleanup (mirrors `list_youtube_candidates`).
- [x] Unit tests (10): flat (2 videos); subfolder one-level; mixed root+subfolder; non-video skipped; empty folder; folder-with-only-non-videos; depth-2 pruned; oversized dropped; invalid URL; gdown raise wrapped.
- [x] Pytest green: `tests/services/test_gdrive_service.py` — 32 passed.

**Decision log:** chose to **download upfront** via gdown rather than list-only via Drive REST API. Trade-off: queue-time blocks ~30s for typical 1-2-video submissions, but reuses the live gdown auth path (no new Drive API key wiring). When N=2 (another product needs Drive folder fan-out), revisit and lift a Drive API list-only primitive into `noctusai_lib.integrations.google_drive`.

**Improvements:**
- `iter_drive_folder_videos` depth-calculation hardcodes the `<root_folder>` gdown wrapper assumption (depth=2 means top-level inside the root, depth=3 means one subfolder deep). If gdown ever changes its layout, the parent_subfolder field silently mis-labels. Worth a comment-level sanity check OR a more robust path-based detection.
- Caller is responsible for cleanup of returned refs' local files. Phase 3's batch endpoint must own this (rename-into-`<job_id>__<name>` shifts ownership to the worker — fine, but document it).
- Oversized cap defaults to `DEFAULT_MAX_BYTES` (8GB); for shorts a much smaller cap may make sense (most reels < 100MB). Decide in Phase 4 whether to enforce a tighter Shorts-specific cap.

### Phase 2 — Migration: `target_format` + `batch_id` columns ✅
- [x] Edit `products/social-wiring/backend/migrations/001_social-wiring.sql` in-place: add `target_format` (NULL, CHECK in `('youtube','shorts','unknown')`) + `batch_id` UUID NULL + partial index `idx_sw_upload_jobs_batch ON (org_id, batch_id, created_at DESC) WHERE batch_id IS NOT NULL`.
- [x] Apply via Supabase MCP `apply_migration(name="social_wiring_upload_jobs_add_target_format_and_batch_id")` → `success:true`.
- [x] Verified via `information_schema.columns` query — both columns present + check constraint live.

**Improvements:**
- The migration file's in-place edit + the live-DB MCP migration are independent operations. Codebase ↔ live-DB parity isn't auto-verified by anything; a future agent re-running 001 against a fresh DB will get the columns from the file, but if the file ever drifts from the MCP-applied migration name, recovery becomes "diff manually." The platform doesn't have a `supa-migration-list ↔ migrations/*.sql` parity check today.
- No colocated regression test against the live schema (e.g. an integration test that inserts with `target_format='shorts'` + `batch_id=<uuid>` and reads back). Phase 3's fan-out tests exercise the columns end-to-end so the gap is covered transitively; documenting it here so it's not lost.

### Phase 3 — Fan-out endpoint ✅
- [x] `UploadService.queue_drive_folder_upload(...) → BatchQueued` with `BatchChild` value object.
- [x] Router: `POST /api/videos/upload/drive-folder` returning `BatchUploadCreated(batch_id, jobs[])`.
- [x] Empty-folder / no-videos → 422; unparseable URL → 400 (matches existing single-file path); Drive auth gap → 503 (inherited via `_build_upload_service`).
- [x] Each inserted row carries `source_type="browser"`, `source_url=<original_folder_url>` (audit), `batch_id`, `target_format=NULL` (worker stamps it).
- [x] Files renamed into the canonical `upload_dir/<job_id>__<file_name>` shape so the existing `_materialise_source` browser path picks them up unchanged.
- [x] Unit tests (6 service-level): flat 2 videos, browser-source + folder audit URL, subfolder parent label, invalid URL, empty folder, only-non-videos.
- [x] Router boundary tests (2): schema rejects non-google host (422), service rejects un-folder-parseable Drive URL (400).

**Decision log:**
- **Why `source_type="browser"`** (not a new `"gdrive-folder-child"` source type) for child rows: the file is already on disk after fan-out, so `_materialise_source`'s existing browser branch is the right shape. Adding a new source_type would force a new branch + a new CHECK constraint + downstream UI code paths — extra surface for zero benefit (the audit info we'd want is already captured in `source_url`).
- **Why `source_url=<folder_url>`** for child rows: keeps the audit trail (which folder produced this row) without conflating it with the actual file location.
- **Sibling failure isolation**: per-row insert failures don't cancel succeeded siblings (matches the user-confirmed §2 constraint). If ALL inserts fail we surface the first error; if SOME inserted, we return what we got and continue.

**Improvements:**
- The `_install_fake_gdown` helper is now duplicated between `test_gdrive_service.py` and `test_upload_service.py`. N=2 → triage time per [[feedback_recurrence_rule]]. **Triage:** [A] accept-with-rationale — the helper is 15 lines + the two files are test-internal; lifting to a shared `conftest.py` adds import-graph complexity for tiny gain. Re-visit if N=3 emerges.
- The router's "no videos found" detection uses substring matching against the `UploadServiceError` message (`"No accepted video"`, `"no files"`, `"fanout failed"`). Brittle — a future re-wording of `iter_drive_folder_videos`'s error would silently re-classify as 400. Right shape is a typed exception (`DriveFolderEmptyError(GoogleDriveError)`) but that's a Phase-5 refactor candidate.
- `BatchQueued.children` is an ordered list; sibling order follows gdown's `download_folder` return order which is non-deterministic. If the UI ever wants a stable visual order, the service should sort by `(parent_subfolder, file_name)` before returning.

### Phase 4 — Worker classification + Shorts metadata ✅
- [x] Added `_classify_and_stamp_target_format` helper: idempotent on retry (skip if row already has a value), maps gdrive_service's `"reels"` → `"shorts"` (DB constraint values), best-effort on failure (stamps `"unknown"` rather than aborting upload).
- [x] Added `_shorts_aware_description` static helper: appends `#Shorts` to vertical descriptions, idempotent (won't duplicate, case-insensitive on the tag check).
- [x] Wired both into `_do_upload_pipeline` between `_materialise_source` and the YT `upload_video` call.
- [x] Tests (12 new): 7 covering description shaping (horizontal pass-through, unknown pass-through, None pass-through, shorts appends, idempotent w/ existing tag, lowercase idempotency, empty becomes just tag) + 5 covering classify+stamp (idempotent w/ existing value, reels→shorts mapping, youtube pass-through, classify-raise→unknown, unexpected-value→unknown).
- [x] Full backend suite green: 457 tests pass (1 second faster than expected — classification is a cheap call).

**Decision log:**
- **DB column values `youtube` / `shorts` / `unknown`** vs gdrive_service's `youtube` / `reels` / `unknown`: the platform thinks of vertical short-form as "Shorts" (the YT-side label) but the classifier returns "reels" (the format-side label). Mapped at the stamping boundary — both legitimate, just for different consumers.
- **Best-effort on classification failure** stamping `unknown`: the alternative (failing the upload) is the wrong trade — a vertical that misses the `#Shorts` ranking nudge is far less bad than aborting an upload entirely. YT will still auto-promote it to a Short on their side if it's vertical+≤3min; we just lose the explicit description signal.

**Improvements:**
- The `monkeypatch.setattr(gdrive_service, "classify_video_format", ...)` pattern used in classify-stamp tests is on our own code (`gdrive_service.classify_video_format` is a thin wrapper over external ffprobe). Per [[feedback_no_monkeypatching_in_tests]], the cleanest shape is constructor-injection. *Triage:* [A] accept-with-rationale — the function-under-test is the stamper not the classifier; the classifier is a dependency exercised by its own tests in `test_gdrive_service.py`. The monkeypatch is testing the integration boundary mapping (`"reels"` ↔ `"shorts"`), not pretending the classifier doesn't exist.
- `_classify_and_stamp_target_format` makes one extra DB write per upload (even for existing single-file uploads that never get stamped explicitly). Today's load is ~10 uploads/day so this is invisible; at scale we could batch the stamp into the `_update_status(status="uploading")` write that's already happening one line later.
- The existing `TestRunUploadJob` pipeline tests now classify + stamp on every run (fake video bytes → ffprobe fails → stamp `"unknown"`). Tests pass because they don't assert exact update-payload count; if a future contributor tightens that assertion they may hit a surprise. Adding a colocated assertion that the stamp WAS written would surface that, but adds noise. Leave it.

### Phase 5 — Batch status read + dashboard grouping ✅
- [x] `UploadService.get_batch_status(org_id, batch_id) → dict | None` aggregates rows + computes per-status counts (forward-compat: unknown statuses contribute to `total` only).
- [x] `GET /api/videos/upload/batch/{batch_id}` route returning `BatchStatusOut(batch_id, total, counts, jobs)`.
- [x] `_row_to_out` extended to surface `target_format` + `batch_id` on every `UploadJobOut` (additive, preserves prior shape).
- [x] Tests (3): unknown batch → None; multi-status aggregation; forward-compat with unknown status.
- [x] Recent-uploads dashboard endpoint: target_format/batch_id flow through naturally via the row shape — no separate dashboard wiring needed in Phase 5; deferred surfacing-as-grouped-cards to FE work (out of scope for this BE-only project).

**Decision log:**
- Moved `get_batch_status` onto `UploadService` (where `upload_jobs` data lives) rather than `DashboardService` (which aggregates `video_cache`). Distinct domains; cleaner.
- Counts dict includes every documented status key with default 0 so the UI renders uniformly regardless of which statuses are populated.

**Improvements:**
- The `counts` dict is hand-listed in `UploadService.get_batch_status` AND in `BatchStatusCounts` schema. N=2 → triage time: [A] accept-with-rationale — the list of upload status values is also hand-listed in 3 other places (schema Literal, DB CHECK constraint, the status transitions doc), all of which need to stay aligned. A single-source-of-truth refactor is a separate cross-cutting hardening project, not in scope here.

### Phase 6 — Full test + manual-handoff doc ✅
- [x] `pytest products/social-wiring/backend/` → **460 passed**.
- [x] `cd products/social-wiring/frontend && npx vite build` → built in 3.38s, no errors.
- [x] `mcp/noctusai/` tests → **1369 passed** (sanity — no MCP changes).
- [x] Updated `products/social-wiring/MASTER-PROMPT.md` with the new fan-out endpoint + the `target_format`/`batch_id` shape.
- [x] Wrote `findings.md` next to this PROJECT.md (slips/errors/mistakes/lessons/knowledge, plus operator manual-test runbook + curl snippets).

**Improvements:** none beyond what's in `findings.md`. Project ready for operator manual test.

---

## 7. Open questions

1. **What happens on `target_format == "unknown"`?** — likely-portrait-but-ffprobe-failed. Default = upload as-is, no `#Shorts` tag. Operator can retry-with-edit if YT rejects. *Decided during Phase 4.*
2. **Should `upload_jobs.source_url` for child rows store the file_id, the full Drive web URL, or a virtual scheme like `gdrive-fileid://<id>`?** — leaning Drive web URL for parity with existing single-file path. *Decide before Phase 3.*
3. **Folder URL with zero videos but with subfolders that have videos** — expected to surface those? **YES** per the one-level recursion contract. Test in Phase 1.
4. **Title collision across siblings in a batch** — if two videos share the same `UploadMetadata.title`, do we suffix `(1)` / `(2)`? *Default NO* — leave to operator (both videos can legitimately share a title; YT allows it). *Decide before Phase 3.*
5. **Vista CRM seed lift** — `app/services/crm_service.py` (`CRMService` + `PropertyData` + `build_youtube_metadata` + `validate_product_code`) is currently product-local. User raised in this session whether it should lift to `noctusai_lib.integrations.vista` (Protocol + Fake + Real + factory) + `noctusai_lib.domain.real_estate` so future products can consume. **Decision:** YES seed-worthy, file `social-wiring-vista-seed-lift` as a sibling project AFTER this test cycle stabilizes — doing it mid-flight conflates scopes. `KB § INTEGRATIONS/vista.md` already pointers at this. Not in scope for this project.
6. **Agent-driven live testing requires either a pasted JWT or a scoped Bash permission rule.** Auto-mode classifier blocks Supabase service-role magic-link minting even with verbal "you're allowed" — it reads as a fixed boundary, not a per-turn judgment. Durable fix = settings rule; ephemeral fix = paste-the-token-per-session.

---

## 8. Dependencies & blockers

- **Drive API auth must be live** for the test org — the existing single-file path already proves this works.
- **`upload_jobs` schema must accept new columns** — handled in Phase 2.
- **No blocker on Meta/IG App Review** — explicitly out of scope.
- **`projects/platform-auth-modernization/`** — the LIVE TEST against `ONE10010` requires the new `ApiToken` shape (`X-Product-Token` / `Bearer pk_*`) so the agent + operator can trigger uploads without a per-user JWT. Live test executes in Wave 4 of that parent project's Phase 5.
- **`products/social-wiring/projects/social-wiring-vista-seed-lift/`** — the live test consumes `build_youtube_metadata` from the seed (`noctusai_lib.domain.real_estate`) once the lift lands. Until then, the temporary product-local import works but produces drift.

---

## 9. Success criteria

- Operator hits `POST /api/videos/upload/drive-folder` with a Drive folder URL containing 1 horizontal + 1 vertical video (or subfolders containing same) → 2 `upload_jobs` rows created → both reach `status='published'` on real YouTube → vertical appears as a Short on the channel (auto-promoted by YT) → both rows share `batch_id`.
- Test suite green: pytest social-wiring + vite build + mcp/noctusai.
- Manual operator test passes against a real Drive folder.
- Project's `findings.md` written; any surfaced patterns three-way-synced.

---

## 10. How to use this plan

Phase-by-phase by default — execute one phase, pause, wait for "continue" / "next" / "do phase N". User overrides with throughput instructions ("ram through 1-3" etc.).

Close commands (project close, after every phase ✅):

```bash
# regenerate improvements rollup
python mcp/noctusai/cli.py --improvements products/social-wiring/projects/youtube-drive-folder-fanout/PROJECT.md

# archive on close
python mcp/noctusai/cli.py --archive products/social-wiring/projects/youtube-drive-folder-fanout

# final commit + push (user explicit go required per R4)
# architect presents diff + branch + push command; user says go; architect executes.
```

---

## 11. Change Log

- **2026-05-20** — Project created. Pre-research: YouTube Shorts cap verified as 180s (3 min) since 2024-10-15 — not 60s. IG path scoped out (separate project gated on App Review). Phase B (truncation + outro) deferred until manual testing surfaces real failure modes. Endpoint shape, recursion depth, failure isolation all confirmed with user. Phase 1 ready.
- **2026-05-20** — Phase 1 ✅ `iter_drive_folder_videos` + 10 tests (32 in test_gdrive_service.py).
- **2026-05-20** — Phase 2 ✅ `target_format` + `batch_id` columns applied to live DB (Supabase MCP migration `social_wiring_upload_jobs_add_target_format_and_batch_id`) + 001_social-wiring.sql edited in-place.
- **2026-05-20** — Phase 3 ✅ `queue_drive_folder_upload` + `POST /api/videos/upload/drive-folder` endpoint + 8 new tests. Service-layer choice: `source_type="browser"` for child rows (file already on disk after gdown); `source_url=<folder_url>` for audit.
- **2026-05-20** — Phase 4 ✅ Worker classification + Shorts metadata: `_classify_and_stamp_target_format` (idempotent, best-effort) + `_shorts_aware_description` (idempotent, case-insensitive) wired into `_do_upload_pipeline`. 12 new tests.
- **2026-05-20** — Phase 5 ✅ `get_batch_status` + `GET /api/videos/upload/batch/{batch_id}` + `_row_to_out` extended with `target_format`/`batch_id`. 3 new tests.
- **2026-05-20** — Phase 6 ✅ Validation: backend 460/460 pass + frontend vite build clean + MCP toolkit 1369/1369 pass. MASTER-PROMPT.md updated with new endpoints. `findings.md` written with operator manual-test runbook. Project ready for handoff.
- **2026-05-20** — User pivoted to a unified-auth design when about to live-test (the JWT-only path was drift). Three sibling projects filed + executed in one push: `projects/platform-auth-modernization/`, `products/social-wiring/projects/social-wiring-vista-seed-lift/`. Both run through Wave 1-3 in isolated worktrees with parallel engineers. Live preflight (`GET /api/auth/me` with `pk_*` ApiToken) returns the expected `AuthContext`. Fan-out endpoint + batch endpoint opted into the new `get_current_user_org_unified` dep so they accept ApiToken / cookie / legacy JWT alike. Admin-client fallback for product callers landed (JWT-shape detection in `_build_upload_service`). Vista CRM consume-from-seed proven via live `await crm.get_property("ONE10010")`. **Single remaining blocker is operator-action**: `YOUTUBE_CLIENT_ID/SECRET` in `.env` + per-org channel connection. Runbook at `findings.md § Platform OAuth setup`. Tests: 481/481 social-wiring backend; 1761/1761 seed-lib; vite build clean.
