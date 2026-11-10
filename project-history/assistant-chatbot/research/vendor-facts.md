# Vendor fact-check — Google OAuth + WAHA (as of 2026-11-09)

Legend: VERIFIED = quoted from a primary page fetched today. UNVERIFIED = from memory, not quoted today; check before relying on it.

## Google

### Q3: Verification exemptions (the key correction)
Source: https://support.google.com/cloud/answer/13464323
- "If the app is for your personal use (fewer than 100 users)" (no verification needed). VERIFIED
- "Apps in development/testing/staging mode are not subject to verification." VERIFIED
- "The app is only used by people in your Google Workspace or Cloud Identity organization." VERIFIED
- Service-account-only access, and admin-trusted / Marketplace admin-installed apps, are also exempt. VERIFIED
- The page does not list a separate domain-wide exemption.
Source: https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification
- Verification is not required "if you are the only user of your app or if your app is used by only a few users." VERIFIED

### Q1: Testing mode
Source: https://support.google.com/cloud/answer/15549945
- "limited to up to 100 test users listed in the OAuth consent screen." VERIFIED
- "Google will display a warning message before allowing a specified test user to authorize scopes." VERIFIED
- "Authorizations by a test user will expire seven days from the time of consent." VERIFIED
- Unverified apps in production: "100 new users in total, after the app presents the unverified app screen." VERIFIED
Source: https://developers.google.com/identity/protocols/oauth2
- An External-type project in "Testing" "is issued a refresh token expiring in 7 days", unless "the only OAuth scopes requested are a subset of name, email address, and user profile." VERIFIED. Every scope in this app triggers the 7-day expiry.
- Internal user type (Workspace only): not subject to the 7-day Testing expiry. UNVERIFIED wording; the restriction is stated only for "external user type".

### Q2: Scope classes
The scopes page (https://developers.google.com/identity/protocols/oauth2/scopes) gives descriptions but no class flags in the fetched text. The classes below are UNVERIFIED (standard Google classification as I know it; confirm in Cloud Console > Data Access, which shows the flags):
| Scope | Class |
|---|---|
| drive.file | non-sensitive (Google's recommended choice) |
| calendar, spreadsheets, documents, forms.body, presentations, contacts, tasks | sensitive |
| drive (full), drive.readonly | restricted |
| gmail.readonly, gmail.modify, gmail.compose, full mail.google.com | restricted |
| gmail.send, gmail.labels | sensitive |
- Restricted scopes accessed via a server: the app "must go through a security assessment from Google-empanelled security assessors", reassessed "at least every 12 months". VERIFIED. That page gives no cost. CASA cost (roughly USD hundreds to thousands per year) and timelines (weeks): UNVERIFIED.

### Q4: Extra enablement
- Every API must be enabled in the Cloud project (standard). UNVERIFIED wording.
- Photos Library API: "The `photoslibrary.readonly`, `photoslibrary.sharing`, and `photoslibrary` scopes will be removed." Calls "will return a `403 PERMISSION_DENIED` after March 31, 2025." VERIFIED (https://developers.google.com/photos/support/updates). Only app-created media plus the Picker API remain.
- Keep API scope exists ("See, edit, create and permanently delete all your Google Keep data"), VERIFIED. It is restricted to Workspace/enterprise use and is not usable with consumer @gmail accounts: UNVERIFIED.
- Forms API is GA and needs only normal enablement: UNVERIFIED.

### Q5: Bottom line
The owner's belief is wrong. A personal app used only by the owner is exempt from verification and from CASA (both quotes above). In Testing mode with the owner added as a test user, every listed API works today, restricted Gmail and Drive scopes included. The owner clicks through an "unverified app" warning once per consent.
What breaks:
(a) The refresh token and the authorization expire 7 days after consent, so the owner must re-consent weekly.
(b) The app is capped at 100 test users.
Fixes:
- Set the publishing status to "In production" while still unverified. For an app under 100 users this is allowed under the personal-use exemption, removes the 7-day expiry, and keeps the warning screen. The no-expiry effect is inferred from the Testing-only wording, not separately quoted.
- Or, if the owner has Workspace, use the Internal user type.

## WAHA

### Q6: Core vs Plus (major change)
Source: https://waha.devlike.pro/docs/how-to/waha-plus/
- As of version 2026.6.1, "all features that used to be in WAHA Plus" are in Core: unlimited sessions, multimedia, all storages and built-in security. VERIFIED
- "There's no separate Plus image anymore." Use `devlikeapro/waha`. Core is "100% free and open source, for everyone." VERIFIED
- Optional Community tier at $5/month, described as giving no perks. VERIFIED
- Engines listed: WEBJS, WPP, GOWS, NOWEB, VENOM. VERIFIED. Per-engine status was not checked.
- The old rule "Core = only the `default` session" is obsolete. Source: https://waha.devlike.pro/docs/how-to/sessions/, which says "**WAHA** supports multiple sessions in one container." VERIFIED
- QR code: `GET /api/{session}/auth/qr` returns a binary image by default, base64 via the Accept header, or `?format=raw` with a `value`. The first QR lasts 60 s, later ones 20 s, up to 6. VERIFIED
- Webhooks are set per session in `config.webhooks[]` (url, events, hmac, customHeaders, retries). VERIFIED
- API key: `WHATSAPP_API_KEY` env var and `X-Api-Key` header. UNVERIFIED today.
- Current stable version is at least 2026.6.1 (exact tag not checked). Resource footprint: not checked; NOWEB/GOWS are lighter than WEBJS, which runs Chromium (UNVERIFIED).

### Q7: One container per line
Not documented as a recommended pattern. The docs support many sessions per container, and multi-session is now free in Core, so one container per line is optional (useful for isolation, but costs more RAM). The docs consulted today give no caveat against it. UNVERIFIED beyond that.

### Q8: WhatsApp ToS
Source: https://faq.whatsapp.com/1217634902127718 (search-result summary of the page, not a direct fetch)
- Unofficial apps are third-party versions "without WhatsApp's approval". Using or linking them is treated as a breach of the Terms and can lead to temporary or permanent bans or loss of device linking.
Source: https://faq.whatsapp.com/1104252539917581
- "Nossos produtos não foram projetados para o envio de mensagens automáticas ou em massa" ("Our products were not designed for sending automated or bulk messages"). VERIFIED
WAHA is an unofficial client, so every line it runs carries ban risk.
