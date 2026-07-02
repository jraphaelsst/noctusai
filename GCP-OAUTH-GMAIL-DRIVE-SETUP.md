# Google Cloud Console — enable Gmail + Drive for social-wiring (per-cliente connect)

> **Who does this:** you (Google Cloud Console is manual, human-only config).
> **Why:** Gmail + Google Drive reuse the **same** Google OAuth client as YouTube/Calendar,
> but "Conectar Gmail / Google Drive" in the **/clientes** ClienteModal only completes end-to-end
> once that client has (a) the **Gmail + Drive scopes** enabled on the consent screen and
> (b) the **new callback URIs** registered. Until then the flow starts but Google rejects it
> (`redirect_uri_mismatch` or a scope error).
>
> Adapted from the working YouTube setup (`GCC-OAUTH-SETUP.md`). YouTube/Calendar already work —
> this doc is only the **incremental Gmail + Drive** step.

---

## Prerequisites (already true — just confirm)

- The social-wiring Google OAuth **2.0 Client ID** (type **Web application**) exists — the one whose
  ID/secret are in social-wiring's `.env` as `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`
  (Gmail/Drive intentionally reuse this same client).
- Privacy Policy + Terms are live (needed by the consent screen):
  - Privacy: `https://social.noctusai.com/consent/privacy-policy`
  - Terms: `https://social.noctusai.com/consent/terms-of-use`

**Where everything below happens:** [Google Cloud Console](https://console.cloud.google.com) →
select the correct **project** (top bar) → **APIs & Services**.

---

## Step 1 — Enable the APIs

APIs & Services → **Enabled APIs & services** → **+ ENABLE APIS AND SERVICES** → search + enable each:

- [ ] **Gmail API**
- [ ] **Google Drive API**

(YouTube Data API v3 + Google Calendar API should already be enabled.)

---

## Step 2 — Add the Gmail + Drive scopes to the OAuth consent screen

APIs & Services → **OAuth consent screen** → **Edit App** → **Scopes** step → **ADD OR REMOVE SCOPES**.
Add these (the ones YouTube already uses stay; **add the two new blocks**):

```
# Drive
https://www.googleapis.com/auth/drive            # full access — OR use drive.readonly for read-only
# Gmail
https://www.googleapis.com/auth/gmail.send       # send only — OR gmail.modify for read + send
```

> ⚠️ **Restricted / sensitive scopes:** `drive` and `gmail.*` are **restricted scopes** in Google's
> classification. In **Testing** mode they work for Test users immediately. To use them with any
> Google account (Production/Published), Google requires **OAuth verification / a security
> assessment** for restricted scopes — plan for that if you publish. For now, keep yourself as a
> **Test user** (Step 4) to develop/verify without the full assessment.

Confirm the consent screen still has the privacy + terms links from the prerequisites (App
information → "Application privacy policy link" / "Application Terms of Service link"), and
**Authorized domain** = `noctusai.com`.

---

## Step 3 — Register the new callback (redirect) URIs

APIs & Services → **Credentials** → click your **OAuth 2.0 Client ID** → **Authorized redirect URIs**
→ **+ ADD URI** for each of these **4** (dev `localhost:8011` + prod `social.noctusai.com`), then **SAVE**:

```
http://localhost:8011/api/integrations/accounts/gmail/oauth/callback
http://localhost:8011/api/integrations/accounts/google_drive/oauth/callback
https://social.noctusai.com/api/integrations/accounts/gmail/oauth/callback
https://social.noctusai.com/api/integrations/accounts/google_drive/oauth/callback
```

> These are the **multi-account / per-cliente** callback paths the ClienteModal OAuth-start uses
> (`POST /api/integrations/accounts/{gmail|google_drive}/oauth/start` → Google → these callbacks →
> the new account is created scoped to the cliente). No "Authorized JavaScript origins" needed —
> social-wiring uses the server-side auth-code flow, so only redirect URIs matter.

---

## Step 4 — Test users (while the consent screen is in Testing)

OAuth consent screen → **Audience / Test users** → **+ ADD USERS** → add your Google account(s).

> In **Testing** mode only Test users can consent, **and refresh tokens expire after 7 days**. That's
> fine for verifying. For durable production use you must **Publish** the app (and, for the restricted
> `drive`/`gmail` scopes, complete Google's verification — see the ⚠️ in Step 2).

---

## Step 5 — Verify end-to-end (allow a few minutes to propagate)

1. **Prod:** `https://social.noctusai.com` → **Clientes** → open a cliente → **Contas** tab →
   **Conectar Gmail** (and **Conectar Google Drive**) → Google consent screen appears → approve →
   you're redirected back to `/clientes?account_created=…` and the account shows under that cliente.
2. **Local:** same flow on `http://localhost:8011`.

**If it fails:**
- `redirect_uri_mismatch` → the exact callback URI isn't registered (Step 3) — copy it verbatim from
  the error and add it.
- `access_denied` / scope error → the scope isn't added (Step 2), or you're not a Test user (Step 4).
- `refresh token missing / expired after ~7 days` → Testing-mode limitation → Publish (Step 4 note).

---

## Notes

- **Reuses the YouTube client on purpose** — one Google app, one consent bundle for all Google
  providers (YouTube · Calendar · Gmail · Drive). Don't create a second client.
- **Maps & Gemini use API keys, not OAuth** — no redirect URI; the key just goes in `.env`.
- **Meta is a *separate* app** (developers.facebook.com, not this GCP client) — see
  `docs/integrations/META-APP-VERIFICATION.md`.
- Related in-repo: `GCC-OAUTH-SETUP.md` (the fuller YouTube scratch), `KB § INTEGRATIONS/oauth-patterns.md`,
  `KB § GUIDES/google-oauth-setup.md`, and the per-cliente model in `project_clientes_own_connections` (memory).
