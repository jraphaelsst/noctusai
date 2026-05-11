# Google OAuth — your next steps before therapy-scheduling-pilot Phase 3 manual QA

> **Created 2026-05-11** after you authorized the credential migration from `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/.env` into noc's `.env`.
>
> **Naming**: keys live as **`GOOGLE_OAUTH_CLIENT_ID`** / **`GOOGLE_OAUTH_CLIENT_SECRET`** / **`GOOGLE_OAUTH_REDIRECT_URI`** (plus `GOOGLE_MAPS_API_KEY` + `GOOGLE_CALENDAR_ID` + `GOOGLE_OAUTH_ACCOUNT_EMAIL`) — **global**, not therapy-prefixed. Every product reads from these dev creds. Per-product overrides (`THERAPY_GOOGLE_CLIENT_ID`, `IMOBI_GOOGLE_CALENDAR_OAUTH_CLIENT_ID`) honored by AliasChoices when you scope per-product for production (future).
>
> But **you still need to do two things in Google Cloud Console** before the live OAuth flow works for therapy-platform.

---

## ⚠️ Critical reminder — redirect URI registration

The OAuth client we imported was originally created for the `whatsapp-google-scheduling` sibling repo. Its **redirect URI** is registered for the sibling's domain, NOT for therapy-platform's domain.

**Google Cloud Console will reject the OAuth callback** when therapy tries to use it, with `redirect_uri_mismatch` error.

### Fix (5 minutes in the Console)

1. Open Google Cloud Console → APIs & Services → Credentials.
2. Find the OAuth 2.0 Client ID (matches `THERAPY_GOOGLE_CLIENT_ID` in noc `.env`).
3. Click the pencil/edit icon.
4. Under **Authorized redirect URIs**, click **+ ADD URI** and add therapy's callback:
   - **Local dev**: `http://localhost:8000/api/scheduling/gcal/callback` (or whatever port therapy backend runs on)
   - **Tunnel dev** (`./start.sh therapy-platform tunnel`): `https://<your-cloudflare-tunnel>.trycloudflare.com/api/scheduling/gcal/callback`
   - **Production**: `https://<your-prod-domain>/api/scheduling/gcal/callback`
5. Save.

Add **all environments** you'll test against — each tunnel URL is different, so you may need to add a new redirect each time you start a fresh tunnel.

The exact path is `/api/scheduling/gcal/callback` (defined at `products/therapy-platform/backend/app/routers/scheduling.py`).

---

## OAuth consent screen — verify scopes

The OAuth client probably already has the right scopes from the sibling's setup, but verify:

- `https://www.googleapis.com/auth/calendar.events` (Calendar event read + write — required for therapy to read therapist's availability blocks AND write therapy appointments to their calendar)
- `https://www.googleapis.com/auth/userinfo.email` (to identify the therapist; optional but helpful)

If scopes are missing, OAuth consent will refuse the flow.

---

## After both steps are done

1. Bring up the therapy stack: `./start.sh therapy-platform tunnel` (the `tunnel` mode is needed if the redirect URI requires HTTPS).
2. Walk through the `products/therapy-platform/projects/therapy-scheduling-pilot-rollout/` Phase 3 checklist:
   - Live connect: `/therapist/agendamento` → click "Conectar Google Calendar" → consent → expect `connected: true`
   - Verify DB: `gcal_authorized_at` populated, `gcal_refresh_token_encrypted` length > 0
   - Live book: pick a slot → enter `patient_id` → confirm. Expect both `therapy.appointments` row AND a Calendar event in the connected calendar.
   - Live blackout: manually add a 1-hour event in the connected calendar → refresh `/candidates` → confirm slot is excluded.
   - Live re-auth: `UPDATE therapy.therapist_profiles SET gcal_authorized_at = now() - interval '8 days' WHERE user_id = ...;` → reload page → confirm re-auth banner appears.
   - Live reschedule: PATCH an appointment to a new slot → confirm Calendar event MOVES (same event_id) instead of being recreated.

When all 6 checks pass, mark Phase 3 ✅ in `products/therapy-platform/projects/therapy-scheduling-pilot-rollout/PROJECT.md` and run `./start.sh therapy-platform` to validate the same flow works without the tunnel (if applicable).

---

## When this file can be deleted

Once Phase 3 of `therapy-scheduling-pilot-rollout` is closed (✅) AND archived to `archive/projects/<date>/`, delete this file (`GOOGLE_OAUTH_NEXT_STEPS.md`) from the repo root.

The credentials themselves stay in noc `.env` for the lifetime of the deployment.
