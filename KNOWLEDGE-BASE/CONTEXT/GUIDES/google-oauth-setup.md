# Google Cloud Console OAuth Setup — Calendar API

Copy-paste runbook for creating a Google OAuth 2.0 client that lets a product call the Google Calendar API on a user's behalf. First adopter: **therapy-platform** (per-therapist `/api/scheduling/gcal/*` flow). Reusable for any future product that needs user-delegated GCal access.

This runbook covers Google Cloud Console steps only. The application side (env vars, redirect handler, token storage) is already shipped in `products/therapy-platform/`; you fill in env vars at the end.

---

## Prerequisites

- A Google account with permission to create projects in Google Cloud Console (`https://console.cloud.google.com/`).
- The product's frontend dev URL (default for therapy: `http://localhost:5173`) and prod URL (whatever Render / etc. assigns).
- The product's backend dev URL (default for therapy: `http://localhost:8004`) — only matters if you ever swap the redirect handler to the backend; current shape redirects to the frontend, which calls the backend to exchange the code.

---

## Step 1 — Create (or pick) a Google Cloud project

1. Open `https://console.cloud.google.com/`.
2. Top-bar project picker → **New Project**.
3. Name: `noctusai-therapy` (or whatever name reflects the deployment). Org / location: leave defaults unless you have a specific Workspace tenant.
4. **Create**.
5. Wait ~10s for the project to spin up. Switch to it via the top-bar picker once it's listed.

---

## Step 2 — Enable the Google Calendar API

1. Left sidebar → **APIs & Services** → **Enabled APIs & services**.
2. **+ ENABLE APIS AND SERVICES** at the top.
3. Search "Google Calendar API".
4. Click the result → **Enable**.

Wait until the dashboard shows it as enabled (a few seconds).

---

## Step 3 — Configure the OAuth consent screen

1. Left sidebar → **APIs & Services** → **OAuth consent screen**.
2. User type: **External** (unless this is a Google Workspace tenant where every connecting therapist is in the same org — in which case **Internal** simplifies verification).
3. **Create**.

### App information

- **App name:** `NoctusAI Therapy` (visible to therapists on the consent screen — pick a name they'll recognise).
- **User support email:** your support inbox (e.g. `joaoraphaelsst@gmail.com` during pilot).
- **App logo:** optional for test-mode; required for production verification.

### App domain

- **Application home page:** the deployed frontend URL.
- **Application privacy policy link:** the product's privacy page (e.g. `https://<prod-host>/privacidade`).
- **Application terms of service link:** the product's terms page (e.g. `https://<prod-host>/termos`).

### Authorised domains

- Add the bare domain of your prod host (e.g. `noctus.ai`). Localhost does not require listing here.

### Developer contact information

- Your email.

**Save and continue.**

### Scopes

1. **Add or remove scopes**.
2. Tick the box for `https://www.googleapis.com/auth/calendar` — this is the only scope the therapy app needs (full read/write on the connected user's calendars; matches what `app/routers/scheduling.py:69` requests).
3. **Update** → **Save and continue**.

### Test users (test-mode only)

While the OAuth app is unverified, Google restricts who can consent. Until you complete production verification, only listed test users can complete the flow.

1. **+ Add users**.
2. Add the Google accounts of every therapist who'll connect during the pilot. **Pilot rollout note:** start with the developer's own Google account; add real therapists as they onboard.
3. **Save and continue**.

### Summary → **Back to dashboard**.

---

## Step 4 — Create the OAuth 2.0 client ID

1. Left sidebar → **APIs & Services** → **Credentials**.
2. **+ CREATE CREDENTIALS** → **OAuth client ID**.
3. **Application type:** **Web application**.
4. **Name:** `therapy-platform-web` (internal — therapists don't see it).

### Authorised JavaScript origins

Add the frontend origins that will initiate the OAuth flow:

- `http://localhost:5173` (dev)
- The deployed frontend origin (e.g. `https://therapy.noctus.ai`)

### Authorised redirect URIs

The frontend callback page exchanges the code with the backend. The redirect URI **must match exactly** (scheme + host + port + path) what the app sends. The app default is the frontend callback:

- `http://localhost:5173/therapist/scheduling/gcal-callback` (dev)
- `<prod-frontend-origin>/therapist/scheduling/gcal-callback` (prod)

Anti-pattern: adding `/api/scheduling/gcal/callback` (a backend path) — the current `app/routers/scheduling.py` shape sends users to the frontend callback page, which then calls the backend with the `code`. If a future project flips the redirect to the backend, register that path too.

5. **Create**.
6. A modal pops up with the **Client ID** and **Client secret**. **Download JSON** (keeps a backup); also copy the two strings — you need them for the env vars.

---

## Step 5 — Wire the credentials into the deployed env

The therapy backend reads two env vars (`products/therapy-platform/backend/app/config.py:37-38`):

- `THERAPY_GOOGLE_CLIENT_ID`
- `THERAPY_GOOGLE_CLIENT_SECRET`

### Local dev (`.env` at repo root)

```bash
# .env (gitignored — never commit)
THERAPY_GOOGLE_CLIENT_ID=<client-id-from-step-4>.apps.googleusercontent.com
THERAPY_GOOGLE_CLIENT_SECRET=<client-secret-from-step-4>
```

The therapy backend's Pydantic Settings loads these on startup. Restart the backend after adding them.

### Production (Render / Fly / wherever)

Add the same two env vars in the host's secret-management UI. They are required at process boot — restart the service after adding.

### Verify the credentials loaded

After restart, hit `GET /api/scheduling/gcal/authorize` (logged-in therapist). A `200` with an `authorize_url` field that includes your client-id confirms the credentials are wired. A `500` with `"OAuth credentials not configured"` means the env vars didn't reach the process — check the host's deploy logs.

---

## Step 6 — End-to-end smoke test

1. Open the app at `/therapist/agendamento`.
2. Click **Conectar Google Calendar**.
3. You should land on Google's consent screen with the app name from Step 3.
4. Pick a Google account that's in your **Test users** list (Step 3) — otherwise Google blocks with an `access_denied` error.
5. Accept → you should land back at `/therapist/scheduling/gcal-callback?code=...` → the page exchanges the code → the app shows "Conectado".
6. Verify in Supabase: `SELECT gcal_authorized_at, length(gcal_refresh_token_encrypted) FROM therapy.therapist_profiles WHERE user_id = '<your-uid>';` — both columns populated.

---

## Production verification (when you outgrow test-mode)

Test-mode caps connections at the listed test users + ~100 users total + Google shows an "unverified" warning before consent. To remove these limits:

1. OAuth consent screen → **Publish App** → **Push to production**.
2. If you're using only the `calendar` scope, this is a non-sensitive scope flow — usually no full verification needed. Google will tell you if it does.
3. If a sensitive / restricted-scope review is requested, expect 4–6 weeks plus a privacy policy / security assessment.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `redirect_uri_mismatch` on consent | URI in Step 4 doesn't match what the app sends | Add the exact URI (scheme + host + port + path) to **Authorised redirect URIs** |
| `access_denied` immediately after consent | User not in test-users list (Step 3) | Add the account, OR publish to production |
| `invalid_client` | Wrong client-id or secret in env vars | Re-copy from the Credentials page; restart the process |
| 500 from `/api/scheduling/gcal/authorize` | `THERAPY_GOOGLE_CLIENT_ID` / `_SECRET` unset | Check `.env` is loaded; restart |
| Therapist consents, but refresh-token is empty after a few minutes | Re-consent without `prompt=consent` | The backend already pins `prompt=consent` + `access_type=offline` (`app/routers/scheduling.py:77-78`); if you see this, file a follow-up — the app default is correct |
| `invalid_grant` on token refresh after 7 days | Re-auth window expired (by design) | The UI prompts re-consent — that's `feedback_webhook_verify_before_side_effect` not a bug. The therapist re-runs Step 6 |

---

## What lives where

- **Client-id + secret:** Google Cloud Console → Credentials page (this runbook) + deployed `.env`.
- **Scopes:** hardcoded at `products/therapy-platform/backend/app/routers/scheduling.py:69` (`_GCAL_SCOPES`).
- **Redirect URI:** request-time arg defaulting to `http://localhost:5173/therapist/scheduling/gcal-callback` (`app/routers/scheduling.py:202-203, 255-256`); must match Step 4.
- **Refresh-token storage:** `therapy.therapist_profiles.gcal_refresh_token_encrypted` (encrypted via `therapy.encrypt_gcal_token` / `decrypt_gcal_token`, migration 011).
- **7-day re-auth window:** enforced by checking `gcal_authorized_at` against `now() - interval '7 days'` (`app/services/scheduling.py`).

---

## Reusing this runbook for another product

The steps above are identical for any product that needs user-delegated GCal. The two product-specific pieces:

1. **Env-var names** — convention is `<PRODUCT_SLUG>_GOOGLE_CLIENT_ID` + `<PRODUCT_SLUG>_GOOGLE_CLIENT_SECRET`.
2. **Redirect URI path** — convention is `<frontend-origin>/<role>/scheduling/gcal-callback` (matches the page that exchanges the code).

If a third product adopts this flow, the OAuth-adapter seam is already in the seed (`seed/lib/backend/noctusai_lib/integrations/google_calendar/oauth_adapter.py`) — only the env-var binding + redirect URI are per-product.
