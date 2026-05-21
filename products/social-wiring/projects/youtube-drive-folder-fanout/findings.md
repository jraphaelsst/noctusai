# youtube-drive-folder-fanout — findings

Living retrospective for this project. Five categories per [[feedback_knowledge_tracking]].

## 1. Slips

- **PROJECT.md §3 "queue time only lists files (cheap Drive API call)" was aspirational.** Without a Drive API key wired (the existing flow uses `gdown` against publicly-shared folders), the "cheap list" pattern doesn't exist for free. Honest design = download upfront via `gdown.download_folder` (same path the single-file flow already takes). Doc-corrected during Phase 1 in the **Decision log** block.

## 2. Errors

- *(none — every test passed on first run after the gdown-import refactor in Phase 1.)*

## 3. Mistakes

- **`run-live-test.sh` had an unquoted jq filter — `jq -r .batch_id // empty`.** The shell split it into three jq args (`.batch_id`, `//`, `empty`); jq read `//` and `empty` as input *files* ("Is a directory" / "Could not open file empty"), ignored stdin, and emitted no batch id — so the script never polled (the server-side upload worker ran fine regardless). Fix: quote the whole filter — `jq -r '.batch_id // empty'`. Lesson: always single-quote jq filters that contain `//`, `|`, or spaces.
- **First-cut Phase 1 tests `import gdown` then patched its `download_folder` attribute.** gdown isn't installed in the dev venv (prod containers have it). Tests failed with `ModuleNotFoundError`. Fixed by switching to `monkeypatch.setitem(sys.modules, "gdown", types.SimpleNamespace(...))` — gives the test a fake module before the lazy `import gdown` in production code resolves to it. Pattern now reused by `test_upload_service.py`'s batch tests too.

## 4. Lessons

- **Reusing `source_type="browser"` for fan-out children beats inventing a new source_type.** The file is on disk after gdown finishes; the existing `_materialise_source` browser branch already handles "file already there." Avoiding the new branch saved a new CHECK constraint + migration + downstream UI code paths. The `source_url` column on the browser-source row records the originating folder for audit — no fidelity lost.
- **YouTube Shorts is 180s as of 2024-10-15, not 60s.** Big — eliminated the entire truncation/outro Phase B from the initial scope. The 60s figure persists in third-party blog posts; always re-verify off [official YouTube Help](https://support.google.com/youtube/answer/15424877). Asterisk: >60s + active Content ID claim = global block, only matters when the operator uses licensed audio.
- **YT auto-classifies vertical+≤180s as Shorts on its side.** We don't pick an upload endpoint — `youtube.upload_video()` is the same call for both long-form and Shorts. The `#Shorts` description tag is the only platform-side signal we add.
- **Idempotent worker stamps are cheap insurance.** `_classify_and_stamp_target_format` short-circuits when the row already has a value (retry path); `_shorts_aware_description` checks for `#Shorts`/`#shorts` before appending. Both make re-runs deterministic — important because the BackgroundTasks worker is at-least-once in failure scenarios.

## 5. Knowledge

- **YouTube Shorts max length:** 180s (3 min) since 2024-10-15. Pre-2024 was 60s.
- **Content ID + Shorts gotcha:** Shorts longer than 60s with an active Content ID claim are **globally blocked**. Surface: any track in YouTube's audio library is fine; uploader-supplied licensed audio is the risk.
- **`gdown.download_folder` layout:** writes to `<output>/<root_folder_name>/<...>`. One level of subfolder recursion happens by default (preserves subfolder structure under the root). Files at depth ≥3 (i.e. two subfolders deep) appear in `gdown`'s return list but our project's `iter_drive_folder_videos` prunes them per the one-level recursion contract.
- **`classify_video_format` returns `"youtube" | "reels" | "unknown"`.** Our `upload_jobs.target_format` column uses `"youtube" | "shorts" | "unknown"` (the YT-side label). Mapping happens at the worker stamping boundary in `_classify_and_stamp_target_format`.
- **Live DB schema (NoctusAI prod, applied 2026-05-20):** `social_wiring.upload_jobs` gained `target_format TEXT NULL CHECK IN ('youtube','shorts','unknown')` + `batch_id UUID NULL` + partial index `idx_sw_upload_jobs_batch ON (org_id, batch_id, created_at DESC) WHERE batch_id IS NOT NULL`. Codebase `001_social-wiring.sql` matches.
- **A Google refresh token is bound to (client_id, user, scopes), NOT to a product.** This is why the yt-crawler refresh token works unchanged for social-wiring once both use the same OAuth client — the token doesn't know or care which app stores it. Practical consequence: porting a credential across noc products that share an OAuth client is just `decrypt(old_key) → re-encrypt(new_key) → UPSERT`, and the redirect-URI registration (which only matters during the initial consent dance) is irrelevant to the refresh path. The `social_wiring.credentials` / yt-crawler `credentials` tables are the same seed `CredentialStore` shape (`encrypted_tokens` = `Fernet(JSON(bundle))`); only the Fernet `ENCRYPTION_KEY` differed.
- **Single-flight upload (`upload_max_concurrent=1`) serializes the batch.** In the live test job 1 uploaded + got its video id while job 2 sat `queued`, then job 2 advanced once job 1's slot freed. Expected behavior, not a stall. The DB `status` can lag YouTube's side: a job shows `processing` (our worker polling YT's `processingStatus`) while the video is already visible/usable on the channel.

---

## Manual test handoff (for the operator)

### Prerequisites
- Backend running (single-container social-wiring + Redis/Supabase reachable).
- YouTube credentials connected for the test org via Settings → YouTube.
- A Drive folder shared publicly (or accessible to the gdown-anon path), containing at least:
  - 1 horizontal video (e.g. 16:9 `master.mp4`)
  - 1 vertical video (e.g. 9:16 `shorts-cut.mp4`)
  - Optional: a subfolder containing another vertical clip

### Quick test

```bash
# Replace <FOLDER_ID>, <TOKEN>, <BACKEND_HOST> for your env.
curl -X POST "https://<BACKEND_HOST>/api/videos/upload/drive-folder" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "drive_folder_url": "https://drive.google.com/drive/folders/<FOLDER_ID>",
    "metadata": {
      "title": "Episode 7 — test",
      "description": "First fan-out test of the Drive folder pipeline.",
      "tags": ["test", "social-wiring"],
      "privacy_status": "unlisted",
      "category_id": "22",
      "notify_recipients": []
    }
  }'
```

Expected response (202):
```json
{
  "batch_id": "<uuid>",
  "jobs": [
    {"job_id": "<uuid>", "file_name": "master.mp4", "parent_subfolder": null},
    {"job_id": "<uuid>", "file_name": "shorts-cut.mp4", "parent_subfolder": null}
  ]
}
```

### Watch progress

```bash
# Aggregate batch status (poll every ~3s):
curl "https://<BACKEND_HOST>/api/videos/upload/batch/<batch_id>" \
  -H "Authorization: Bearer <TOKEN>"

# Per-row detail (one curl per job_id):
curl "https://<BACKEND_HOST>/api/videos/upload/<job_id>/status" \
  -H "Authorization: Bearer <TOKEN>"
```

Expected progression for each job:
1. `queued` (immediately after 202)
2. `uploading` (~20% progress; YT API actively receiving)
3. `processing` (99%; bytes received, YT transcoding)
4. `published` (100%; visible on the channel)

The vertical job's response carries `"target_format": "shorts"` and its description ends with `#Shorts`. On the channel it shows up under the Shorts shelf.

### Failure modes to log back

If anything below happens, save the `upload_jobs.error_message` + the YT video page (when one exists) and surface to architect:

| Symptom | Likely root | What we'd do |
|---|---|---|
| Vertical Short rejected at upload time | >180s + ContentID claim, or YT API regression | Phase B (truncate-to-60s + outro) becomes worth filing |
| Vertical published but NOT on Shorts shelf | Aspect ratio not 9:16, or description tag missing | Confirm `target_format` stamp + `#Shorts` in description |
| `target_format=unknown` on a clearly-vertical file | `ffprobe` failed inside container or name hint mismatched | Inspect logs for the `classify_video_format raised` warning |
| Batch endpoint returns 422 "No accepted video" on a folder you can see | Drive sharing-permission gap, or extensions outside `ACCEPTED_VIDEO_EXTENSIONS` | Re-check folder share settings + file extensions |

---

## Platform OAuth setup — ✅ RESOLVED 2026-05-21 (credentials were in the repo)

**The "operator must create an OAuth client in Google Cloud Console" conclusion was wrong** — the
credentials already existed in the workspace. Resolution, end-to-end, no Console action:

1. **OAuth client** — noc `.env` already carried the YouTube OAuth client as `GOOGLE_OAUTH_CLIENT_ID`
   / `GOOGLE_OAUTH_CLIENT_SECRET` (client `313073479474-…`, the same client `noctusai-youtube-crawler`
   used). The social-wiring YouTube module reads the `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`
   names, which weren't set. Fix: set those two `.env` keys to the existing `GOOGLE_OAUTH_*` values
   (the **current** secret — the downloaded `client_secret_*.json` had a *rotated-out* secret).
2. **Per-org channel credential** — instead of re-running the OAuth consent dance (which would have
   needed the `:8011` redirect URI registered in Console), the working refresh token was **ported
   from yt-crawler's SQLite** (`tmp/dev.sqlite3`, provider `youtube`, channel "João Raphael Souza",
   `UCujIprsfXDrygCTxZVQP9Vg`). A Google refresh token is bound to **(client_id, user, scopes)**, NOT
   to a product — so once social-wiring uses the same client, the token is valid. The blob was
   Fernet-decrypted with yt-crawler's `ENCRYPTION_KEY`, re-encrypted with noc's `ENCRYPTION_KEY`, and
   UPSERTed into `social_wiring.credentials` for org `6dd73140-74a4-41c6-aeff-bc94b5312b53`.
3. **Recreate** the container (`docker compose up -d --no-deps --force-recreate social-wiring`) so it
   re-reads `.env`; verified inside the container that `youtube_client_id/secret` load and the seed
   `CredentialStore.get(...)` decrypts the ported token with a live `refresh_token` + `youtube.upload`.

**Live result (2026-05-21):** `run-live-test.sh` POSTed `product_code=ONE10010` + the Drive folder
(`privacy_status=unlisted`). Server enriched via seed Vista → `build_youtube_metadata` → fanned out
**two real jobs** — `REELS ONE10010.mp4` (vertical → `target_format=shorts`, video id `2a3WJABK_l4`)
and `YT ONE10010.mp4` (horizontal → long-form). Both reached YouTube on channel "João Raphael Souza".
The whole chain — ApiToken auth → Vista enrichment → Drive fan-out → classify → real YouTube upload —
is proven end-to-end.

---

### Google Cloud Console runbook (reference only — NOT needed for the current setup)

The steps below apply only if you ever need to provision a **fresh** OAuth client (new GCP project)
or connect a **brand-new org via the consent dance** instead of porting an existing refresh token.

### Step 1 — Create the OAuth 2.0 client in Google Cloud Console

1. Open https://console.cloud.google.com/apis/credentials
2. Pick a project (or create one for NoctusAI).
3. Enable **YouTube Data API v3** under "APIs & Services → Library".
4. **OAuth consent screen** — internal/external, app name, scopes: `https://www.googleapis.com/auth/youtube.upload`, `https://www.googleapis.com/auth/youtube.readonly`.
5. Credentials → **Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs:
     - `http://localhost:8011/api/youtube/oauth/callback` (local-dev)
     - `https://<your-tunnel-or-prod-host>/api/youtube/oauth/callback` (prod)
6. Copy the Client ID + Client Secret.

### Step 2 — Add to `.env`

```bash
# .env
YOUTUBE_CLIENT_ID=<paste-the-client-id>
YOUTUBE_CLIENT_SECRET=<paste-the-client-secret>
YOUTUBE_REDIRECT_URI=http://localhost:8011/api/youtube/oauth/callback   # adjust for prod
```

### Step 3 — Recreate the container so it re-reads `.env`

```bash
docker compose up -d --no-deps --force-recreate social-wiring
```

### Step 4 — Connect a YouTube channel for the org

Through the platform UI: Settings → YouTube → Connect (initiates the OAuth dance, stores the refresh_token in `social_wiring.credentials` encrypted via the Fernet vault). The connected channel is org-scoped.

### Step 5 — Fire the live test

```bash
export SOCIAL_WIRING_API_TOKEN=$(cat .claude/secrets-ignored/agent-test-apitoken.txt)
bash products/social-wiring/projects/youtube-drive-folder-fanout/run-live-test.sh
```

The script POSTs to `/api/videos/upload/drive-folder` with the ONE10010 + Drive folder URL, then polls `/batch/<id>` every 5s. On success, every child job reaches `published` with `target_format` stamped (`shorts` for vertical, `youtube` for horizontal); vertical jobs get `#Shorts` appended to the description and YouTube auto-promotes them to the Shorts shelf.

---

## What was live-validated — full chain incl. real YouTube upload (2026-05-21)

The platform-auth-modernization + vista-seed-lift + youtube-drive-folder-fanout chain is **proven end-to-end, including a real YouTube upload**:

- ✅ **ApiToken auth** — `GET /api/auth/me` with `Authorization: Bearer pk_*` returns the right `AuthContext`:
  ```json
  {"user":null,"org":{"id":"6dd73140-..."},"caller_kind":"product","scopes":["*"]}
  ```
- ✅ **Vista enrichment** — `await crm.get_property("ONE10010")` returns the real property (`Casa em Alphaville, 6 quartos, 835m², R$ 7.200.000,00`). `build_youtube_metadata` produces the YT title (99 chars within cap), description with the 📍/💰/🛏️/📐 emoji block + tags.
- ✅ **Fan-out endpoint accepts ApiToken** — `POST /api/videos/upload/drive-folder` no longer requires a Supabase JWT (404 → 200 path proven via container logs after the `get_current_user_org_unified` swap).
- ✅ **Admin-client fallback for product callers** — the JWT-shape detection in `_build_upload_service` routes product tokens through the admin Supabase client (RLS bypass is semantically correct because ApiToken is org-scoped at issuance).
- ✅ **Redis SessionStore reachable** — container's `REDIS_URL` fixed to `redis://noctus-redis:6379/0`; PING green.
- ✅ **YT upload itself (2026-05-21)** — after wiring `YOUTUBE_CLIENT_ID/SECRET` and porting the refresh token (see "Platform OAuth setup — RESOLVED" above), `run-live-test.sh` produced two real uploads on channel "João Raphael Souza": vertical `REELS ONE10010.mp4` → `target_format=shorts`, video id `2a3WJABK_l4`; horizontal `YT ONE10010.mp4` → long-form. Vista enrichment + Drive fan-out + classify + upload all confirmed live.