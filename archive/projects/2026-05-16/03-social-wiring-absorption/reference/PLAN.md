# YouTube Crawler — Implementation Plan

> Created: 2026-05-04
> Status: **PENDING APPROVAL**

---

## 1. Goal

Transform the seed scaffold into a working YouTube management tool with four capabilities:

1. **Upload videos** to YouTube (browser file upload + Google Drive link download-then-upload)
2. **Notify contacts** after upload via WhatsApp (WAHA) and Email (SMTP)
3. **List all channel videos** with metrics (not just app-uploaded — the full channel)
4. **Analytics dashboard** with KPIs, charts, and recent activity

Plus a **Settings UI** to manage API keys, OAuth connection, notification recipients, and SMTP/WAHA config — all backed by `.env` placeholders ready for real keys.

---

## 2. Decisions (locked in)

| Topic | Decision |
|---|---|
| **WhatsApp** | Use the `noctusai_lib.integrations.whatsapp` seed (WAHA client). Bring container configs from `whatsapp-google-scheduling` repo (`docker-compose.yml` WAHA + Redis services). |
| **Email** | SMTP (Gmail with App Password via `smtplib.SMTP_SSL`). |
| **Channels** | Single YouTube channel for now. |
| **Notification recipients** | Fixed list configured in Settings (name, email, whatsapp number, active toggle). Per-video override at upload time (select/deselect from the list). See §2.1 below. |
| **Video source** | Browser file upload (drag-and-drop) + Google Drive public/shared link (backend downloads via `gdown`/`httpx`, then uploads to YouTube). |
| **API keys** | Code references `.env` vars with placeholders. Settings UI displays connection status and lets the user see which keys are configured. Keys themselves live in `.env` (not in DB). |
| **YouTube API auth** | OAuth 2.0 for upload + full channel listing. One-time consent flow via Settings page. Refresh token stored encrypted in DB. |

### 2.1 Notification Recipients — Recommendation

**Fixed list in Settings + per-video override at upload time.**

Why: A fixed recipient list avoids re-entering contacts on every upload. But some videos may only be relevant to specific people (e.g., a sponsor gets notified about their video but not others). So the Upload page shows the recipient list with checkboxes — all active recipients pre-selected, with the option to deselect individuals for that specific upload.

---

## 3. Architecture

```
noctusai-youtube-crawler/
├── docker-compose.yml              ← NEW (adapted from whatsapp-scheduling)
├── Dockerfile                      ← NEW (adapted from whatsapp-scheduling)
├── .dockerignore                   ← NEW
├── .env.example                    ← NEW (all keys with placeholders)
├── products/youtube-crawler/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py             ← MODIFY (add new routers)
│   │   │   ├── config.py           ← MODIFY (add YouTube/SMTP/WAHA settings)
│   │   │   ├── routers/
│   │   │   │   ├── settings_router.py    ← NEW
│   │   │   │   ├── upload_router.py      ← NEW
│   │   │   │   ├── videos_router.py      ← NEW
│   │   │   │   └── dashboard_router.py   ← NEW
│   │   │   ├── services/
│   │   │   │   ├── youtube_service.py    ← NEW
│   │   │   │   ├── upload_service.py     ← NEW
│   │   │   │   ├── notification_service.py ← NEW
│   │   │   │   ├── email_service.py      ← NEW
│   │   │   │   └── gdrive_service.py     ← NEW
│   │   │   └── schemas/
│   │   │       ├── settings.py           ← NEW
│   │   │       ├── upload.py             ← NEW
│   │   │       ├── video.py              ← NEW
│   │   │       └── notification.py       ← NEW
│   │   ├── migrations/
│   │   │   ├── 002_credentials.sql       ← NEW
│   │   │   ├── 003_upload_jobs.sql       ← NEW
│   │   │   ├── 004_video_cache.sql       ← NEW
│   │   │   └── 005_notifications.sql     ← NEW
│   │   └── requirements.txt              ← MODIFY
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx                    ← MODIFY (new routes + nav)
│       │   ├── pages/
│       │   │   ├── Dashboard.tsx          ← REWRITE (real analytics)
│       │   │   ├── Videos.tsx             ← NEW
│       │   │   ├── Upload.tsx             ← NEW
│       │   │   └── Settings.tsx           ← NEW
│       │   ├── components/
│       │   │   ├── VideoCard.tsx          ← NEW
│       │   │   ├── UploadZone.tsx         ← NEW
│       │   │   ├── RecipientSelector.tsx  ← NEW
│       │   │   ├── MetricCard.tsx         ← NEW
│       │   │   └── ViewsChart.tsx         ← NEW
│       │   └── hooks/
│       │       ├── useVideos.ts           ← NEW
│       │       ├── useUpload.ts           ← NEW
│       │       ├── useDashboard.ts        ← NEW
│       │       └── useSettings.ts         ← NEW
│       └── package.json                   ← MODIFY (add recharts)
```

---

## 4. Container Infrastructure

Adapted from `whatsapp-google-scheduling/docker-compose.yml`. We bring in:

### docker-compose.yml (at repo root)

```yaml
services:
  # --- YouTube Crawler backend ---
  app:
    build: .
    environment:
      # YouTube
      YOUTUBE_CLIENT_ID: ${YOUTUBE_CLIENT_ID:-}
      YOUTUBE_CLIENT_SECRET: ${YOUTUBE_CLIENT_SECRET:-}
      YOUTUBE_REDIRECT_URI: ${YOUTUBE_REDIRECT_URI:-http://localhost:8096/api/youtube/oauth/callback}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-}
      # SMTP
      SMTP_HOST: ${SMTP_HOST:-smtp.gmail.com}
      SMTP_PORT: ${SMTP_PORT:-465}
      SMTP_USER: ${SMTP_USER:-}
      SMTP_PASSWORD: ${SMTP_PASSWORD:-}
      # WAHA
      WAHA_BASE_URL: ${WAHA_BASE_URL:-http://waha:3000}
      WAHA_API_KEY: ${WAHA_API_KEY:-}
      WAHA_SESSION: ${WAHA_SESSION:-default}
      # Supabase
      SUPABASE_URL: ${SUPABASE_URL:-}
      SUPABASE_KEY: ${SUPABASE_KEY:-}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY:-}
      # Redis
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8096:8096"
    volumes:
      - .:/app
      - ./tmp/uploads:/app/tmp/uploads
    depends_on:
      redis:
        condition: service_started
    command: >
      uvicorn app.main:app --host 0.0.0.0 --port 8096 --reload
      --app-dir products/youtube-crawler/backend

  # --- Redis (upload job queue + caching) ---
  redis:
    image: redis:7-alpine

  # --- WAHA (WhatsApp HTTP API) ---
  waha:
    image: devlikeapro/waha:latest
    platform: linux/amd64
    environment:
      WAHA_API_KEY: ${WAHA_API_KEY:-}
      WAHA_DASHBOARD_USERNAME: ${WAHA_DASHBOARD_USERNAME:-admin}
      WAHA_DASHBOARD_PASSWORD: ${WAHA_DASHBOARD_PASSWORD:-admin}
      WHATSAPP_DEFAULT_ENGINE: WEBJS
    ports:
      - "3000:3000"
    volumes:
      - waha_sessions:/app/.sessions

  # --- Cloudflare tunnel (optional, for webhook testing) ---
  tunnel:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate --url http://app:8096
    depends_on:
      app:
        condition: service_started
    profiles:
      - tunnel

volumes:
  waha_sessions:
```

### .env.example (at repo root)

```env
# --- YouTube Data API v3 ---
YOUTUBE_CLIENT_ID=your-google-oauth-client-id
YOUTUBE_CLIENT_SECRET=your-google-oauth-client-secret
YOUTUBE_REDIRECT_URI=http://localhost:8096/api/youtube/oauth/callback
ENCRYPTION_KEY=generate-with-python-c-from-cryptography.fernet-import-Fernet;print(Fernet.generate_key().decode())

# --- SMTP (Gmail) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password

# --- WAHA (WhatsApp) ---
WAHA_BASE_URL=http://waha:3000
WAHA_API_KEY=your-waha-api-key
WAHA_SESSION=default
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=admin

# --- Supabase ---
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- Frontend ---
VITE_API_URL=http://localhost:8096
VITE_SUPABASE_URL=your-supabase-url
VITE_SUPABASE_KEY=your-supabase-anon-key
```

---

## 5. Backend — Detailed File Specs

### 5.1 Config (`app/config.py`)

Extend `ProductSettings` with YouTube/SMTP/WAHA fields. All read from `.env`:

```python
class CrawlerSettings(ProductSettings):
    # YouTube OAuth
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8096/api/youtube/oauth/callback"
    encryption_key: str = ""

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""

    # WAHA (consumed by seed's get_whatsapp_client)
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_session: str = "default"

    # Redis (for upload job tracking)
    redis_url: str = "redis://localhost:6379/0"
```

### 5.2 YouTube Service (`app/services/youtube_service.py`)

Wraps `google-api-python-client`:

| Method | API Call | Quota Cost | Purpose |
|--------|----------|-----------|---------|
| `get_auth_url()` | — | 0 | Generate OAuth consent URL |
| `exchange_code(code)` | token exchange | 0 | Get access + refresh tokens |
| `refresh_access_token(refresh)` | token refresh | 0 | Refresh expired token |
| `get_channel_info()` | `channels.list(mine=True)` | 1 | Channel name, subs, video count |
| `list_all_videos(page_token?)` | `search.list` + `videos.list` | 1+1 per page | ALL channel videos with stats |
| `upload_video(file, metadata)` | `videos.insert` (resumable) | 100 | Upload video to YouTube |
| `get_video_stats(video_ids[])` | `videos.list(id=..., part=statistics)` | 1 per 50 IDs | Batch metrics fetch |

**OAuth scopes**: `youtube.upload`, `youtube.readonly`, `youtube.force-ssl`

**Token storage**: Refresh token encrypted with Fernet (`cryptography` lib), stored in `youtube_crawler.credentials` table. Access token refreshed automatically on expiry.

### 5.3 Upload Service (`app/services/upload_service.py`)

Handles the upload pipeline:

1. **Receive** — accept file from browser OR Google Drive link
2. **Download** (if Drive link) — download file to `tmp/uploads/` via `httpx` (public links) or `gdown` (shared links)
3. **Upload** — call `youtube_service.upload_video()` with resumable upload
4. **Notify** — on success, trigger `notification_service.notify_upload()`
5. **Track** — update job status in `upload_jobs` table throughout

Status flow: `queued → downloading → uploading → processing → published → notified | failed`

### 5.4 Google Drive Service (`app/services/gdrive_service.py`)

Downloads video files from Google Drive links:

- Parses Drive URL to extract file ID (`/file/d/{id}/...` or `?id={id}`)
- Downloads via direct download URL with `httpx` (stream to disk)
- Validates: file size (max 128GB per YouTube limit), file type (video MIME types)
- Falls back to `gdown` for files that require cookie confirmation

### 5.5 Notification Service (`app/services/notification_service.py`)

Dispatches notifications on upload completion:

- **WhatsApp**: Uses `noctusai_lib.integrations.whatsapp.get_whatsapp_client()` from seed.
  Calls `client.send_text(chat_id, message)` for each active WhatsApp recipient.
  Message template: "🎬 New video published: {title}\n📺 {youtube_url}\nUploaded via YouTube Crawler"
- **Email**: Uses `email_service.send_email()` with HTML template (video title, thumbnail, link)
- Logs delivery status per recipient in `notification_log` table

### 5.6 Email Service (`app/services/email_service.py`)

Simple SMTP sender:

```python
async def send_email(to: str, subject: str, html_body: str) -> bool:
    # Uses smtplib.SMTP_SSL (port 465) with settings from config
    # Returns True on success, False on failure (logged, not raised)
```

### 5.7 Routers

#### `settings_router.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/settings/youtube/status` | GET | YouTube connection status (connected? channel name?) |
| `/api/settings/youtube/auth-url` | GET | Generate OAuth consent URL |
| `/api/youtube/oauth/callback` | GET | Handle OAuth callback → store tokens |
| `/api/settings/youtube/disconnect` | DELETE | Revoke + delete tokens |
| `/api/settings/notifications/config` | GET/PUT | SMTP/WAHA config status |
| `/api/settings/recipients` | GET/POST | List / add notification recipients |
| `/api/settings/recipients/{id}` | PUT/DELETE | Update / remove a recipient |
| `/api/settings/keys/status` | GET | Which `.env` keys are configured (non-empty) |

#### `upload_router.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/videos/upload` | POST | Upload video file (multipart) |
| `/api/videos/upload-from-drive` | POST | Download from Drive link then upload |
| `/api/videos/upload/{job_id}/status` | GET | Poll upload job progress |
| `/api/videos/upload/history` | GET | Recent upload jobs |

#### `videos_router.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/videos` | GET | All channel videos (paginated, from cache) |
| `/api/videos/{video_id}` | GET | Single video detail |
| `/api/videos/sync` | POST | Force re-sync from YouTube API |

#### `dashboard_router.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/dashboard/stats` | GET | Aggregated KPIs (total views, likes, videos, etc.) |
| `/api/dashboard/top-videos` | GET | Top 5 by views |
| `/api/dashboard/recent-uploads` | GET | Last 10 uploads with notification status |

---

## 6. Database Migrations

### 002_credentials.sql

```sql
CREATE TABLE youtube_crawler.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,          -- 'youtube'
    encrypted_tokens TEXT NOT NULL,  -- Fernet-encrypted JSON
    channel_id TEXT,                 -- YouTube channel ID
    channel_title TEXT,              -- YouTube channel name
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, provider)
);
```

### 003_upload_jobs.sql

```sql
CREATE TABLE youtube_crawler.upload_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    privacy_status TEXT DEFAULT 'private',
    category_id TEXT DEFAULT '22',   -- "People & Blogs"
    source_type TEXT NOT NULL,       -- 'browser' or 'gdrive'
    source_url TEXT,                 -- Google Drive URL if applicable
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','downloading','uploading','processing','published','notified','failed')),
    progress_percent INTEGER DEFAULT 0,
    error_message TEXT,
    notify_recipients UUID[],       -- which recipients to notify
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 004_video_cache.sql

```sql
CREATE TABLE youtube_crawler.video_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    published_at TIMESTAMPTZ,
    duration TEXT,                   -- ISO 8601 duration
    privacy_status TEXT,
    view_count BIGINT DEFAULT 0,
    like_count BIGINT DEFAULT 0,
    comment_count BIGINT DEFAULT 0,
    favorite_count BIGINT DEFAULT 0,
    tags TEXT[],
    category_id TEXT,
    uploaded_via_app BOOLEAN DEFAULT false,
    synced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, youtube_video_id)
);

CREATE INDEX idx_video_cache_org ON youtube_crawler.video_cache(org_id);
CREATE INDEX idx_video_cache_published ON youtube_crawler.video_cache(published_at DESC);
```

### 005_notifications.sql

```sql
CREATE TABLE youtube_crawler.notification_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    whatsapp_number TEXT,           -- E.164 format (+5511999999999)
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE youtube_crawler.notification_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    upload_job_id UUID REFERENCES youtube_crawler.upload_jobs(id),
    recipient_id UUID REFERENCES youtube_crawler.notification_recipients(id),
    channel TEXT NOT NULL,          -- 'email' or 'whatsapp'
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sent','failed')),
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. Frontend — Detailed Page Specs

### 7.1 Settings Page (`Settings.tsx`)

Three tabs:

**YouTube tab:**
- Connection status badge (Connected / Not Connected)
- If connected: channel name, subscriber count, video count
- Connect button → redirects to Google OAuth consent screen
- Disconnect button → revokes tokens

**Notifications tab:**
- SMTP status (configured / missing) — reads from `.env`, non-editable
- WAHA status (configured / missing) — reads from `.env`, non-editable
- Recipient list: table with name, email, WhatsApp number, active toggle
- Add recipient form (inline or modal)

**API Keys tab:**
- Read-only status display of which `.env` keys are configured
- Shows: YouTube Client ID, YouTube Client Secret, SMTP, WAHA, Supabase — each with configured/missing status
- Helper text: "Configure these values in your .env file"

### 7.2 Upload Page (`Upload.tsx`)

- **Source selector**: "Upload File" tab / "Google Drive Link" tab
- **Upload File tab**: Drag-and-drop zone, accepted formats: mp4, mov, avi, mkv, webm
- **Google Drive tab**: URL input field + "Download & Upload" button
- **Metadata form** (shared):
  - Title (required)
  - Description (textarea)
  - Tags (chip/tag input)
  - Privacy: public / unlisted / private (radio)
  - Category dropdown (YouTube categories)
- **Recipient selector**: Checkboxes for all active recipients, all pre-selected
- **Upload button**: Starts the job, shows progress bar
- **Upload history**: Table of recent jobs (status, title, date, YouTube link when published)

### 7.3 Videos Page (`Videos.tsx`)

- **View toggle**: Table view / Card grid view
- **Search bar**: Filter by title
- **Filters**: Privacy status, date range, "Uploaded via app" toggle
- **Sort**: By date, views, likes, comments
- **Sync button**: Force refresh from YouTube API
- **Video cards/rows**: Thumbnail, title, published date, views, likes, comments, privacy badge
- **App badge**: Visual indicator for videos uploaded through the app
- **Click**: Expands detail view / modal with full description, tags, all metrics

### 7.4 Dashboard Page (`Dashboard.tsx` — rewrite)

- **KPI cards** (top row):
  - Total Videos (with trend vs last month)
  - Total Views
  - Total Likes
  - Total Comments
- **Views chart**: Line chart of daily views (last 30 days) — using recharts
- **Top 5 videos**: Small table (thumbnail, title, views, likes)
- **Recent uploads**: Last 5 uploads via the app (status, title, notification delivery)
- **Channel card**: Connected channel name, subs, total video count

### 7.5 Navigation Update (`App.tsx`)

```tsx
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Videos", href: "/videos", icon: PlaySquare, route: "videos" },
      { name: "Upload", href: "/upload", icon: Upload, route: "upload" },
    ],
  },
  {
    key: "config",
    label: "Configuracao",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/settings", icon: Settings, route: "settings" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
];
```

---

## 8. New Dependencies

### Backend (`requirements.txt` additions)

```
google-api-python-client>=2.120.0    # YouTube Data API
google-auth-oauthlib>=1.2.0          # OAuth 2.0 flow
google-auth-httplib2>=0.2.0          # HTTP transport
cryptography>=42.0.0                 # Fernet encryption for tokens
gdown>=5.1.0                        # Google Drive downloads
```

### Frontend (`package.json` additions)

```json
{
  "recharts": "^2.15.0"
}
```

---

## 9. WhatsApp Integration — Seed + Containers

### How it works

1. **Container**: WAHA container from `docker-compose.yml` runs at `http://waha:3000` (same setup as `whatsapp-google-scheduling`)
2. **Seed client**: `notification_service.py` instantiates WAHA client via the seed factory:
   ```python
   from noctusai_lib.integrations.whatsapp import get_whatsapp_client, chat_id_for_phone

   client = get_whatsapp_client(
       base_url=settings.waha_base_url,
       api_key=settings.waha_api_key,
       session=settings.waha_session,
   )

   chat_id = chat_id_for_phone(recipient.whatsapp_number)
   await client.send_text(chat_id, message)
   ```
3. **Fallback**: When `WAHA_BASE_URL` is empty, `get_whatsapp_client()` returns `FakeWahaClient` — safe for development without a real WhatsApp connection.

---

## 10. Execution Phases

| Phase | Scope | Estimated Files | Depends On |
|-------|-------|----------------|------------|
| **1** | Config + YouTube Service + Settings page + docker-compose + .env.example | ~12 files | Nothing |
| **2** | Upload automation + Google Drive download + Upload page | ~8 files | Phase 1 |
| **3** | Video listing + cache + Videos page | ~6 files | Phase 1 |
| **4** | Dashboard (rewrite) + Notifications (WAHA + SMTP) | ~8 files | Phase 2 + 3 |

> Phases 2 and 3 can run in parallel after Phase 1.

---

## 10.1 Phase 5 — E2E Real Estate Automation

> Added: 2026-05-12
> Status: **PENDING**
> Depends on: Phases 1–4 (all complete as code). Dev database target is now
> local SQLite; Supabase migration application is deferred until production
> validation.

### 5.0 Context — What the client does

A real estate agency sends:
1. A **property code** (format: `ONE` + digits, e.g. `ONE0000`, `ONE5555`, `ONE100121`)
2. A **Google Drive link** — may be a **single video file** or a **shared folder** containing multiple format variants

The Drive folder typically contains videos for different platforms:
- **YouTube** (landscape 16:9) — this is what we upload in this phase
- **REELS** (portrait 9:16) — skip for now

The link is to an **external** Google Drive (the agency's collaborator's account, not ours). The files are shared via public/shared link — no service account or Drive API OAuth needed. The existing `gdown` / `httpx` download paths handle this.

### 5.1 Decisions (locked in)

| Topic | Decision |
|---|---|
| **YT vs REELS detection** | 1) Filename/subfolder convention first (e.g. `YT`, `YouTube`, `16x9` in name/path); 2) Fall back to aspect-ratio probe via `ffprobe` — 16:9 or wider = YT, 9:16 or taller = REELS |
| **Product code format** | Regex `^ONE\d{3,6}$` — always starts with `ONE` followed by 3–6 digits |
| **CRM integration** | Vista CRM using the in-repo `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` reference. On upload: fetch title + description using the product code and populate YouTube metadata automatically |
| **Drive access model** | External shared link — use `gdown` for folders, `httpx` for direct files. No service account needed |
| **WhatsApp authorization** | **Single authorized number**: `+5511974693365` (hardcoded whitelist in settings). No one else can trigger uploads |
| **WhatsApp confirmation** | **Always confirm** before uploading. Bot presents: video filename, product code, CRM-sourced title/description, privacy status → waits for explicit "sim" / "confirmar" |
| **Upload privacy default** | `private` — can be overridden in confirmation step |
| **Notification post-upload** | Same as Phase 4 — dispatch to all active recipients via WhatsApp + email |

### 5.2 Architecture — New components

```
products/youtube-crawler/
  backend/
    app/
      routers/
        whatsapp_router.py          ← NEW  (inbound webhook from WAHA)
      services/
        gdrive_service.py           ← MODIFY (add folder listing + YT/REELS filter)
        crm_service.py              ← NEW  (fetch property title + description)
        whatsapp_intake_service.py  ← NEW  (parse inbound, manage conversation state)
        upload_service.py           ← MODIFY (accept product_code, wire CRM lookup)
      schemas/
        upload.py                   ← MODIFY (add product_code field)
        whatsapp.py                 ← NEW  (inbound message schemas)
    migrations/
      006_product_code.sql          ← NEW
  frontend/
    src/
      pages/
        Upload.tsx                  ← MODIFY (add product code input)
      hooks/
        useUpload.ts                ← MODIFY (add product_code to types)
```

### 5.3 Google Drive Folder Support — `gdrive_service.py` changes

#### New functions

| Function | Purpose |
|----------|---------|
| `parse_folder_id(url)` | Extract folder ID from `/drive/folders/{id}` or `?id={id}` URLs |
| `is_folder_url(url)` | Return `True` if URL matches a Drive folder shape (vs file) |
| `list_folder_files(folder_url, target_dir)` | Download folder contents via `gdown.download_folder()` to `target_dir`. Returns list of `(path, filename)` tuples |
| `classify_video_format(file_path)` | Inspect filename for YT/REELS hints, then fall back to aspect-ratio via `ffprobe`. Returns `"youtube"` \| `"reels"` \| `"unknown"` |
| `pick_youtube_video(folder_url, target_dir)` | Orchestrator: list folder → download → classify each → return the first `"youtube"` match. Cleanup non-matches |

#### Classification logic (ordered by priority)

1. **Filename convention** — case-insensitive substring match:
   - Contains `YT`, `youtube`, `16x9`, `landscape`, `horizontal` → `"youtube"`
   - Contains `REEL`, `reels`, `9x16`, `vertical`, `portrait`, `shorts` → `"reels"`
2. **Subfolder name** — if file is inside a subfolder whose name matches the above patterns
3. **Aspect ratio probe** (requires `ffprobe` in the container):
   ```python
   # ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of json {file}
   ratio = width / height
   if ratio >= 1.5:   return "youtube"    # 16:9 = 1.78, 4:3 = 1.33 → threshold at 1.5
   if ratio <= 0.75:  return "reels"      # 9:16 = 0.5625
   return "unknown"
   ```
4. **Fallback** — if only one video file exists in the folder, use it regardless

#### Dockerfile change

Add `ffprobe` (from `ffmpeg`) to the backend container:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
```

### 5.4 CRM Service — `crm_service.py` (NEW)

Fetches property data from Vista CRM. The local reference is
`KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md`; do not rely on the public
online docs for implementation details.

```python
class CRMService:
    """Fetch property metadata from the real estate CRM."""

    def __init__(self, *, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key

    async def get_property(self, product_code: str) -> PropertyData | None:
        """GET /imoveis/detalhes?imovel={product_code}&pesquisa={json}&key={key}

        Returns None when the code doesn't exist (404). Raises CRMServiceError
        on transport/auth failures (5xx, 401, 403)."""
        ...

@dataclass
class PropertyData:
    product_code: str
    title: str              # e.g. "Apartamento 3 quartos — Moema, São Paulo"
    description: str        # Full text for YouTube description
    address: str | None
    price: str | None       # formatted, e.g. "R$ 1.200.000"
    bedrooms: int | None
    area_sqm: float | None
    thumbnail_url: str | None  # property photo for reference
```

#### Config additions (`config.py`)

```python
# CRM (real estate property lookup)
crm_base_url: str = ""        # defaults from vista_base_url when empty
crm_api_key: str = ""         # defaults from vista_api_key when empty
vista_base_url: str = ""
vista_api_key: str = ""
```

#### .env additions

```env
# ─── CRM (Real Estate) ───────────────────────────────────────────────
CRM_BASE_URL=
CRM_API_KEY=
VISTA_BASE_URL=
VISTA_API_KEY=
```

Vista auth is a `key` query parameter on every request, with
`Accept: application/json`. The product uses `/imoveis/detalhes` with
`imovel=<Codigo>` as a top-level query parameter and explicit fields in
the `pesquisa` JSON parameter.

### 5.4.1 Local SQLite Dev Database

During development, do not apply 001-006 to Supabase. Use local SQLite:

```env
DATABASE_BACKEND=sqlite
SQLITE_PATH=tmp/dev.sqlite3
LOCAL_DEV_ORG_ID=00000000-0000-4000-8000-000000000001
LOCAL_DEV_USER_ID=00000000-0000-4000-8000-000000000001
```

Apply the equivalent local schema:

```bash
python3 products/youtube-crawler/backend/apply_sqlite_migrations.py
```

The production Postgres/Supabase migrations remain the source of truth in
`products/youtube-crawler/backend/migrations/001_seed.sql` through
`006_product_code.sql`; the SQLite script mirrors their table shape for
local development.

### 5.5 Product Code Field — `006_product_code.sql`

```sql
SET search_path = youtube_crawler, public;

ALTER TABLE youtube_crawler.upload_jobs
    ADD COLUMN product_code TEXT;

CREATE INDEX idx_yt_upload_jobs_product_code
    ON youtube_crawler.upload_jobs(org_id, product_code);

-- Allow product_code in the existing RLS policies (no change needed —
-- column-level additions inherit the row-level policies).
```

#### Schema change (`upload.py`)

```python
class UploadMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=500)
    privacy_status: PrivacyStatus = "private"
    category_id: str = Field(default="22", min_length=1, max_length=4)
    notify_recipients: list[UUID] = Field(default_factory=list)
    product_code: str = Field(default="", max_length=20)  # ← NEW

class UploadJobOut(BaseModel):
    # ... existing fields ...
    product_code: str | None = None  # ← NEW
```

#### Frontend change (`Upload.tsx`)

Add a "Código do Imóvel" input field to the `MetadataFields` component, with:
- Placeholder: `"ONE0000"`
- Helper text: `"Código do imóvel no CRM (ex: ONE5555)"`
- Pattern validation: `/^ONE\d{3,6}$/`

### 5.6 WhatsApp Inbound — `whatsapp_router.py` (NEW)

#### Webhook endpoint

```
POST /api/whatsapp/webhook
```

WAHA forwards all inbound messages here. The router:
1. Validates the sender against the whitelist (`+5511974693365`)
2. Parses the message text for the upload command pattern
3. Manages a simple conversation state machine

#### Message flow

```
User sends:
  "ONE5555 https://drive.google.com/drive/folders/1abc..."

Bot replies:
  "📋 Recebi o pedido de upload:
   🏠 Código: ONE5555
   📁 Link: https://drive.google.com/...

   Buscando dados do imóvel no CRM...
   ⏳ Aguarde."

  [CRM lookup + Drive folder scan happen in parallel]

Bot replies:
  "✅ Dados encontrados:
   🏠 ONE5555 — Apartamento 3 quartos, Moema
   📝 Descrição: [first 200 chars of CRM description]...
   🎬 Vídeo encontrado: ONE5555_YT.mp4 (245 MB, 16:9)
   🔒 Privacidade: Privado

   Confirma o upload? Responda SIM para prosseguir ou NÃO para cancelar."

User sends: "sim"

Bot replies:
  "🚀 Upload iniciado! Você será notificado quando estiver pronto."

  [Upload runs in background]

Bot replies (on completion):
  "✅ Vídeo publicado com sucesso!
   🎬 ONE5555 — Apartamento 3 quartos, Moema
   📺 https://www.youtube.com/watch?v=ABC123
   Enviado pelo YouTube Crawler."
```

#### Error cases

| Scenario | Bot reply |
|----------|-----------|
| Unauthorized sender | No reply (silent drop + log) |
| Invalid product code format | "❌ Código inválido. Use o formato ONExxxx (ex: ONE5555)" |
| Drive URL not found in message | "❌ Não encontrei um link do Google Drive na mensagem. Envie: ONE0000 https://drive.google.com/..." |
| CRM lookup fails | "⚠️ Não consegui buscar os dados de {code} no CRM. Deseja prosseguir com título manual? Envie o título desejado ou CANCELAR." |
| No YT video found in folder | "❌ Não encontrei um vídeo para YouTube (16:9) na pasta. Arquivos encontrados: [list]. Verifique e reenvie." |
| Drive download fails | "❌ Falha ao baixar o vídeo do Drive: {error}. Verifique as permissões de compartilhamento." |
| YouTube upload fails | "❌ Falha no upload para o YouTube: {error}" |
| User sends "não" / "cancelar" | "❎ Upload cancelado." |

#### Conversation state machine

```python
class ConversationState(Enum):
    IDLE = "idle"                          # waiting for a command
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # data presented, waiting for sim/nao
    AWAITING_MANUAL_TITLE = "awaiting_manual_title"  # CRM failed, waiting for manual title
    PROCESSING = "processing"              # upload in progress, ignore new commands
```

State is stored in Redis with key `whatsapp:conv:{phone_number}` and a 30-minute TTL.

#### Config additions (`config.py`)

```python
# WhatsApp inbound
whatsapp_authorized_numbers: str = "+5511974693365"  # comma-separated
```

### 5.7 Upload Pipeline Changes — `upload_service.py`

The `queue_drive_upload` and `run_upload_job` methods gain awareness of:

1. **Folder URLs** — `_materialise_source()` checks `is_folder_url()`:
   - `True` → `pick_youtube_video()` (download folder, classify, pick YT)
   - `False` → existing `download_from_drive()` (single file)

2. **Product code** — stored on the `upload_jobs` row, passed through to notification messages

3. **CRM auto-population** — when `product_code` is non-empty AND `title` is empty/auto, the pipeline calls `CRMService.get_property(product_code)` and fills:
   - `title` ← `"{product_code} — {property.title}"` (max 100 chars)
   - `description` ← `property.description` + standard footer
   - `tags` ← `[product_code, property.address, "imóvel", "real estate"]`

### 5.8 Cloudflare Tunnel — Live Testing

The CF tunnel is already configured in `docker-compose.yml` (profile: `tunnel`).

#### Startup procedure

```bash
# 1. Start full stack with tunnel
./start.sh tunnel

# 2. Get the tunnel URL (appears in cloudflared logs)
docker compose logs tunnel | grep "trycloudflare.com"
# Output: https://random-words.trycloudflare.com

# 3. Add the tunnel URL to CORS origins in .env
#    TUNNEL_HOSTNAME=https://random-words.trycloudflare.com

# 4. Register the tunnel callback URL in GCP Console
#    Add: https://random-words.trycloudflare.com/api/youtube/oauth/callback
#    as an authorized redirect URI in the OAuth client config

# 5. Update YOUTUBE_REDIRECT_URI in .env
#    YOUTUBE_REDIRECT_URI=https://random-words.trycloudflare.com/api/youtube/oauth/callback

# 6. Restart the backend to pick up .env changes
docker compose restart app

# 7. Configure WAHA webhook to point at the tunnel
#    In WAHA dashboard (http://localhost:3000/dashboard):
#    Settings → Webhook URL → https://random-words.trycloudflare.com/api/whatsapp/webhook
```

#### Live readiness endpoints

Authenticated Settings endpoints for pre-E2E checks:

| Endpoint | Purpose |
|---|---|
| `GET /api/settings/vista/status?product_code=ONE5555` | Calls Vista `/imoveis/detalhes` and returns a sanitized property summary |
| `POST /api/settings/email/test` | Sends a Gmail SMTP test email to `SMTP_USER` or payload `{ "to": "..." }` |
| `GET /api/settings/waha/status` | Checks WAHA session status using tolerant session response parsing |
| `POST /api/settings/waha/test` | Sends a WAHA text to payload `{ "phone": "+55...", "text": "..." }` |

WAHA webhook response/event shapes are documented in
`products/youtube-crawler/backend/WAHA_RESPONSE_FORMATS.md`.

Set `FRONTEND_BASE_URL` to the operator-facing frontend origin so the
Google OAuth callback redirects to the app UI instead of the backend path.

#### CORS update (`config.py`)

```python
tunnel_hostname: str = ""  # e.g. "https://random-words.trycloudflare.com"

# cors_origins updated to include tunnel_hostname dynamically
@property
def all_cors_origins(self) -> list[str]:
    origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
    if self.tunnel_hostname:
        origins.append(self.tunnel_hostname)
    return origins
```

### 5.9 Execution sub-phases

| Sub-phase | Scope | Estimated Files | Depends On |
|-----------|-------|----------------|------------|
| **5a** | Git baseline commit + apply local SQLite schema mirror of migrations 001–006 | ~3 files | Nothing |
| **5b** | Product code: migration 006 + schema + upload_service + router + Upload.tsx + useUpload.ts | ~6 files | 5a |
| **5c** | GDrive folder: gdrive_service additions + ffprobe in Dockerfile + upload_service changes | ~3 files | 5a |
| **5d** | CRM service: crm_service.py + config + .env | ~3 files | 5a |
| **5e** | WhatsApp inbound: whatsapp_router + whatsapp_intake_service + schemas/whatsapp + main.py + config | ~5 files | 5b + 5c + 5d |
| **5f** | CF tunnel: config CORS + .env placeholders + docs | ~3 files | 5a |
| **5g** | Frontend polish: Upload.tsx product code + Dashboard.tsx product code display | ~2 files | 5b |
| **5h** | PLAN.md update + verification | 1 file | All above |

> Sub-phases 5b, 5c, 5d, 5f can run in parallel after 5a.
> Sub-phase 5e depends on 5b + 5c + 5d.

### 5.10 Phase 5 Verification Plan

#### Automated

- `pytest` — all existing 153 + new tests pass
- New unit tests:
  - `gdrive_service`: `parse_folder_id()`, `is_folder_url()`, `classify_video_format()`
  - `whatsapp_router`: message parsing, auth whitelist check, state machine transitions
  - `crm_service`: mock API responses, error handling
  - `upload.py` schema: product code validation
- `npx vite build` — frontend builds clean

#### E2E Smoke Test (manual, via CF tunnel)

1. Start stack: `./start.sh tunnel`
2. Copy tunnel URL → register in GCP → update `.env`
3. OAuth: Settings → Connect → verify channel
4. **Platform upload (single file)**: Upload page → file + `ONE5555` → private → submit → verify YT upload
5. **Platform upload (folder link)**: Upload page → folder URL + `ONE1234` → verify it picks the YT video, skips REELS
6. **WhatsApp command**: Send `ONE5555 https://drive.google.com/drive/folders/...` from `+5511974693365`
   - Verify bot responds with CRM data + confirmation prompt
   - Reply "sim" → verify upload starts
   - Verify completion notification arrives
7. **Unauthorized sender**: Send from a different number → verify silent drop
8. **Dashboard**: Verify product code visible in recent uploads
9. **Notifications**: Verify email + WhatsApp delivery after upload

---

## 11. Verification Plan

### Per-phase checks

- `cd products/youtube-crawler/backend && pytest` — all existing + new tests pass
- `cd products/youtube-crawler/frontend && npx vite build` — clean build
- `docker compose up` — all containers start clean

### Integration testing (manual)

- OAuth flow: Settings → Connect YouTube → verify channel info appears
- Upload: Upload a private test video → verify it appears in Videos list
- Drive link: Paste a Drive link → video downloads + uploads to YouTube
- Drive folder: Paste a folder link → YT video identified, REELS skipped, upload proceeds
- WhatsApp inbound: Send product code + Drive link → confirm → upload proceeds
- CRM lookup: Product code auto-populates title + description from CRM
- Notifications: After upload → email arrives + WhatsApp message sent (if WAHA connected)
- Dashboard: Metrics match YouTube Studio numbers + product code visible
- Sync: Force sync → new videos from YouTube Studio appear in Videos list

---

## 12. YouTube API Quota Budget

With 10,000 daily units:

| Operation | Cost | Max/day | Notes |
|-----------|------|---------|-------|
| Video upload | 100 | 100 uploads | Enough for any reasonable use |
| List videos (per page, 50 results) | 2 (search + stats) | 5,000 pages | Full channel sync |
| Single video stats | 1 per 50 IDs | 10,000 batches | Dashboard refresh |
| Channel info | 1 | 10,000 | Settings page load |

Plenty of headroom for a single-channel setup. Cache layer reduces API calls further.
