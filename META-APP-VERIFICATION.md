# Meta App Review & Verification — Operator Checklist (social-wiring)

> **Audience:** the operator (João Raphael) driving the Meta App Review submission by hand in the
> Meta developer console. Follow it top-to-bottom.
>
> **Goal:** get the NoctusAI **social-wiring** Meta app approved for **Advanced Access** to the
> permissions needed to (a) publish content to users' Facebook Pages + Instagram Business accounts
> and (b) — later, optionally — read Lead Ads. Advanced Access is what lets the app act for
> businesses **other than your own** (i.e. real tenants), which is the whole point of a multi-tenant SaaS.
>
> **How this doc was built:** every factual claim about Meta's process is grounded in a source that was
> actually fetched (official Meta docs first, reputable 2025/2026 tutorials second). Source URLs are cited
> inline as `[n]` and listed in full in the **Sources** section at the bottom. Where Meta's process is
> ambiguous or could not be verified, that is called out explicitly in **§0.1 Unverified / verify-in-console**
> rather than guessed. Meta changes this UI and these rules frequently — **trust the console over this doc if
> they disagree, and update this doc when you find drift.**
>
> **NoctusAI-specific values** (app id, scopes, URLs, code paths) are drawn from our own repo notes:
> `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md`, `projects/meta-app-review-publish-scopes/{PROJECT,SUBMISSION}.md`,
> `archive/projects/2026-05-16/03-social-wiring-absorption/reference/SETUP_META.md`, and the
> `project_consent_legal_pages` memory. They are marked **⟦NOC⟧**.

---

## 0. What you need before starting (prerequisites)

Have these ready **before** you touch the console — several are hard gates that block the "Submit for Review"
button, and some (business verification) take days on their own.

- [ ] **A Meta (Facebook) developer account** and access to <https://developers.facebook.com/apps/>.
- [ ] **A Meta Business Portfolio** (formerly "Business Manager") that owns, or has admin access to, the
      Facebook Page(s) and linked Instagram Business account(s) you will publish to.
      ⟦NOC⟧ Most of our customers' Pages/IG are Business-Portfolio-owned — this is why production auth uses a
      **System User Token**, not user OAuth (see `SETUP_META.md` Path B). App Review is still required for the
      per-tenant user-OAuth path and for any scope the token exercises against non-owned assets.
- [ ] **Legal business documents** for Business Verification: official business-registration or tax-registration
      document, or a utility bill, showing the business **legal name + address**, valid/not expired, generally
      dated within the last 12 months, in one of Meta's supported languages (Portuguese is supported) [7][8].
      ⟦NOC⟧ Our LGPD controller is **João Raphael, pessoa física (no CNPJ)** per `project_consent_legal_pages`.
      **Flag:** Meta Business Verification normally expects a registered *business* entity. If you are verifying
      as an individual/sole operator without a CNPJ, confirm in Security Center which document types your
      country/account will accept before submitting — see §0.1. This is the single most likely blocker.
- [ ] **A public, reachable Privacy Policy URL and Terms URL.**
      ⟦NOC⟧ These already ship, seed-first, on every product [consent-routes-mandate]:
      - Privacy policy: **`https://social.noctusai.com/consent/privacy-policy`** (canonical apex also live:
        `https://noctusai.com/consent/privacy-policy`)
      - Terms of use: **`https://social.noctusai.com/consent/terms-of-use`**
      - Consent hub: **`https://social.noctusai.com/consent`**
      The privacy policy already contains the **Meta Platform disclosure** (§10) required for Meta review
      (`project_consent_legal_pages`).
- [ ] **A Data Deletion URL** — either a Data Deletion *Instructions* URL (a page describing how a user requests
      deletion) or a Data Deletion *Callback* URL (a real HTTPS endpoint). At least one is mandatory [5].
      ⟦NOC⟧ We can point the **Instructions URL** at `https://social.noctusai.com/consent` (the consent hub
      describes disconnect/deletion; our disconnect deletes the stored credential via
      `CredentialStore.delete`, per `SUBMISSION.md` §4). We do **not** currently ship a programmatic
      deletion-callback endpoint — the Instructions URL path is the compliant, lower-effort option [5]. If Meta
      insists on a callback for your data categories, that becomes a follow-up code task.
- [ ] **An app icon** — 1024×1024 px, square, no platform trademarks [1].
- [ ] **A live, reachable demo deployment** of social-wiring that a Meta reviewer can log into and exercise the
      publish flow on (public URL — production domain or a stable tunnel), plus **test credentials** for a
      sandbox tenant whose Page is linked to an IG Business account [1][2]. ⟦NOC⟧ `SUBMISSION.md` §5 is the
      ready-to-paste reviewer-instructions template.
- [ ] **A ≤3-minute screen recording** (1080p+), one continuous take, showing the flow end-to-end for each
      permission (see §7) [1][2]. ⟦NOC⟧ `SUBMISSION.md` §3 is the shot-by-shot script.
- [ ] **The App ID + App Secret** for the social-wiring Meta app.
      ⟦NOC⟧ These live in prod env as `META_APP_ID` / `META_APP_SECRET` (`SETUP_META.md` A.4). If you don't know
      the App ID yet, §1 covers creating/finding it. **Flag:** the concrete App ID is not committed in the repo
      (secret) — read it from the deployed env or the App Dashboard.

### 0.1 Unverified / verify-in-console (do not assume — Meta drifts these)

- **Exact left-nav labels.** Meta renames dashboard sections often (e.g. "Use Cases" vs "Products", "App
  Review > Permissions and Features"). Paths below are the current-as-of-research names; if a label differs,
  navigate by meaning. The console may show Portuguese labels (`SETUP_META.md` uses them) — both are noted.
- **Two Instagram publishing APIs / permission names.** Meta now offers **"Instagram API with Facebook Login"**
  (classic; permission `instagram_content_publish`, IG account reached via a linked Facebook Page) **and**
  **"Instagram API with Instagram Login"** (newer; permission `instagram_business_content_publishing`, no
  Facebook Page required) [2][10]. ⟦NOC⟧ **Our code uses the classic Facebook-Login path** — it resolves the IG
  Business account from the connected Facebook Page and calls the `instagram_content_publish` flow
  (`meta.md` §1; `SUBMISSION.md` §0). Request `instagram_content_publish`, **not** the `_business_` variant,
  unless you deliberately migrate the adapter. Confirm the exact permission name the Dashboard offers under the
  product you added.
- **"Standard Access" wording in the Permissions Reference.** Meta's Permissions Reference lists many of these
  permissions at "Standard Access" [4]. That is misleading for our case: **Standard Access only works for users
  who have a role on the app (admin/developer/tester) or are test users** [9][11]. To act for **real tenants**
  you must obtain **Advanced Access via App Review** for every permission the live flow uses [9][11]. Treat all
  the publish/read scopes below as **needing Advanced Access** for production.
- **Business Verification as an individual (no CNPJ).** See the prerequisite flag above — verify accepted
  document types in Security Center before relying on this.
- **Whether the supporting read scopes must be submitted.** Depends on whether the Dashboard flags them as
  Advanced-Access-limited for your app; see §6.

---

## 1. Create or locate the Meta app (type: Business)

1. Go to **<https://developers.facebook.com/apps/>**.
2. If the social-wiring app already exists, open it and skip to §2. ⟦NOC⟧ Confirm the App ID matches prod
   `META_APP_ID`.
3. To create: click **Create App** (PT: *Criar app*). When asked for a type/use-case, choose **Business**
   (`SETUP_META.md` A.1) — this is the app type that exposes Pages, Instagram, and Marketing API products and
   the App Review flow. Name it (e.g. `NoctusAI Social Wiring`).
4. After creation you land on the **App Dashboard**.

> **Single app for the fleet.** ⟦NOC⟧ Use **one platform Meta app** (the dual-auth design assumes a
> workspace-global System User Token). Do not create a per-product app. (`PROJECT.md` §7 Q2.)

---

## 2. Add the products / use cases

In the App Dashboard, add the products the app needs. Depending on the console version these appear as
**"Add Product"** tiles or as **"Use cases"** (PT: *Casos de uso*) you customize (`SETUP_META.md` A.2).

Add:

1. **Facebook Login for Business** — the OAuth mechanism that lets a business grant your app access to their
   Page/IG assets [6]. ⟦NOC⟧ Our OAuth start/callback is served by the seed
   `noctusai_lib.security.oauth` router; callback path is `…/api/meta/oauth/callback` (`SETUP_META.md` A.3).
2. **Instagram** product — for publishing to Instagram. Under it, use the **"Instagram API with Facebook
   Login"** configuration (see §0.1 — that's the path our code uses) [2].
3. **(Only if you will do Lead Ads)** **Marketing API** — for reading Lead Ads (§9). Skip for the
   publish-only first submission.

For each use case, open **Customize** (PT: *Personalizar*) and confirm the scopes you intend to request are
listed (`SETUP_META.md` A.2).

---

## 3. Configure app settings (Settings → Basic)

Path: **App Dashboard → App Settings → Basic** (`https://developers.facebook.com/apps/<APP_ID>/settings/basic/`).
These fields are **required** and are checked at submission time [1].

- [ ] **App icon** — upload the 1024×1024 square icon [1].
- [ ] **App name**, **App category**, **Contact email** — set clearly [1][2].
- [ ] **Privacy Policy URL** → ⟦NOC⟧ `https://social.noctusai.com/consent/privacy-policy` [consent-routes-mandate].
- [ ] **Terms of Service URL** (if the field is shown) → ⟦NOC⟧ `https://social.noctusai.com/consent/terms-of-use`.
- [ ] **User Data Deletion** → choose **Data Deletion Instructions URL** and enter
      ⟦NOC⟧ `https://social.noctusai.com/consent` (or a dedicated deletion-instructions page). At least one
      deletion option is mandatory [5].
- [ ] **App Domains** → add your app's public host (⟦NOC⟧ `social.noctusai.com`, plus any tunnel host used for
      the review window). Localhost is **not** accepted here — it requires a real TLD (`SETUP_META.md` A.3).

Then, under the **Facebook Login for Business → Settings** product page
(`…/fb-login-for-business/settings/`), set:

- [ ] **Valid OAuth Redirect URIs** → the **exact** production callback, e.g.
      ⟦NOC⟧ `https://social.noctusai.com/api/meta/oauth/callback` (must match the live app exactly; not
      localhost) (`SETUP_META.md` A.3, `SUBMISSION.md` §6). If you record the screencast from a temporary
      tunnel, add that tunnel's callback here too, and remember tunnel URLs rotate (`SETUP_META.md` "Tunnel URL
      rotation").

---

## 4. Complete Business Verification

Advanced Access to Page/Instagram write scopes requires the developer business to be **verified** — Business
Verification is required for **all** apps requesting Advanced Access [1][9][11]. Start this **early**; it can
take days.

1. Go to your **Meta Business Portfolio → Business Settings → Security Center**
   (PT path in `SETUP_META.md` uses `business.facebook.com/settings`). In the **Business verification** section
   click **Start Verification** [8].
2. Enter the business legal details and upload the documents from the prerequisites (§0). Meta shows a
   **country-specific list** of accepted documents [7][8].
3. Submit and wait for Meta's decision. ⟦NOC⟧ **If verifying as an individual without a CNPJ, this is the
   likely blocker — confirm accepted document types first** (§0.1).

> The App Review flow will also surface a **"Complete Business Verification"** step if it isn't already done
> [1]. You can start it from either place.

---

## 5. Make the required successful API calls (unlocks the submit button)

The **"Request Advanced Access"** button stays **greyed out** until Meta has recorded **at least one
successful API call using each permission** you want to request — made within **30 days** of submitting, and
the call data can take up to ~2 days to register [1][3].

For each permission you'll submit, exercise it once against your own/test assets (Standard Access already lets
you call it for app-role/test users) [9][11]:

- `pages_show_list` → `GET /me/accounts`
- `pages_read_engagement` → read a Page post's `permalink_url`
- `pages_manage_posts` → publish a test post to a **Page you admin**
- `instagram_basic` → resolve the linked IG Business account
- `instagram_content_publish` → publish one test image to an IG Business account you admin

⟦NOC⟧ The live adapter already makes exactly these calls: `list_facebook_pages` → `/me/accounts`,
`publish_facebook_post` → `/{page-id}/feed|/photos`, `publish_instagram_media` →
`/{ig-user}/media` → `/media_publish` (`meta.md` §1; `SUBMISSION.md` §0). Running the publish flow once end-to-end
against a **sandbox tenant with a System User token or an app-admin OAuth token** registers the calls.

> If the button is still grey after a call, wait up to 2 days for the call to register, and confirm the call
> actually **succeeded** (a 4xx/permission error does not count) [1][3].

---

## 6. Request Advanced Access for the permissions

Path: **App Dashboard → App Review → Permissions and Features** [1].

### 6.1 Publish submission (the primary one) — request Advanced Access for:

| Permission | Why (our use) | ⟦NOC⟧ code path |
|---|---|---|
| **`pages_manage_posts`** | Publish a reviewed post/photo to the user's own Facebook Page | `publish_facebook_post` → `POST /{page-id}/feed`\|`/photos` |
| **`instagram_content_publish`** | Publish a reviewed image/carousel to the user's IG Business account | `publish_instagram_media` / `publish_instagram_carousel` → `/{ig-user}/media` → `/media_publish` |

**Supporting reads — add these to the same submission only if the Dashboard flags them as needing Advanced
Access for your app** (a publishing app realistically needs Advanced Access on the Page-list + IG-link reads to
find the destination) (`SUBMISSION.md` §0):

| Permission | Why | ⟦NOC⟧ code path |
|---|---|---|
| `pages_show_list` | List the Pages the user manages (destination picker) | `list_facebook_pages` → `GET /me/accounts` |
| `pages_read_engagement` | Read back the published post's `permalink_url` | post-publish read-back |
| `instagram_basic` | Resolve the IG Business account linked to the Page | `list_instagram_accounts` |
| `business_management` | See Pages/IG owned by a Business Portfolio (most commercial customers) | adapter auth path |

> **Do NOT bundle** `ads_*` or Reels/video scopes into this submission — they are separate projects and bundling
> slows review (`SUBMISSION.md` §0). Request the **minimum** set that makes your screencast reproducible;
> over-requesting triggers extra scrutiny.

For each permission, click **Request Advanced Access** (enabled once §5 is satisfied) and fill the justification
+ screencast form. ⟦NOC⟧ Paste the ready per-permission justification paragraphs from `SUBMISSION.md` §2.

### 6.2 Data Use questionnaire

Answer the **Data Use Checkup / data-handling questions** and link the privacy policy [1][2]. Responses are
evaluated quickly (seconds) [1]. ⟦NOC⟧ `SUBMISSION.md` §4 has the ready answers: tokens encrypted at rest with
Fernet, Page tokens never persisted, deletion on disconnect, no resale/third-party sharing.

---

## 7. Record + attach the screencast

Meta requires a screen recording per permission that **demonstrates the full user experience** for that
permission, high-resolution (1080p+), ideally with English captions on non-obvious UI [1][2]. Record **one
continuous take, no cuts** (edited footage is rejected) (`SUBMISSION.md` §3).

The recording **must visibly show**:
1. The app and login.
2. The Facebook **OAuth consent screen listing the requested permissions** — pause ~2s so the reviewer can read
   `pages_manage_posts` + `instagram_content_publish` on it [2].
3. The connected state (Page + IG account resolved).
4. Composing a post, then clicking **Publish**.
5. The **published post live** on facebook.com and instagram.com (open the returned permalink).

⟦NOC⟧ Follow the shot-by-shot script in `SUBMISSION.md` §3, recorded against the live `noctus-social-wiring`
deployment with a **real sandbox** Page + linked IG Business account.

---

## 8. Provide test access, then submit

1. **Reviewer / testing instructions** — provide the public app URL, sandbox **test credentials**, and
   step-by-step reproduction, so a Meta analyst can exercise the flow without a role on your app [1][2].
   ⟦NOC⟧ Paste `SUBMISSION.md` §5 (includes the note that, pre-approval, the flow deliberately returns
   `422 meta_scope_pending_app_review` — tell the reviewer so they aren't surprised).
2. Confirm the **pre-submission checklist** (`SUBMISSION.md` §6): Live mode on, business verification done,
   privacy + deletion URLs live, app icon set, redirect URI allow-listed, demo reachable, sandbox ready,
   screencast recorded, only in-scope permissions requested, a responder lined up.
3. Accept the platform terms and click **Submit for Review** [1].
4. **Decision typically arrives within ~1 week** [1]. Multiple rounds are possible if Meta asks for
   clarification (`PROJECT.md` §2).
5. **Respond to any reviewer request within ~48h** — Meta closes submissions that go unanswered, forcing a
   resubmission (`PROJECT.md` §6, `SUBMISSION.md` §6).

---

## 9. Development mode → Live mode

- New apps start in **Development mode**. **Reads work in Development with no review**, but publishing/acting
  for real (non-role) users requires the app to be in **Live mode** *and* the relevant scopes approved for
  Advanced Access (`SUBMISSION.md` §0, §6) [9][11].
- Toggle **Development → Live** with the switch at the top of the App Dashboard (near the app name), after the
  required Basic settings (privacy policy, icon, category) are complete — Meta blocks Live if they're missing
  [1].
- ⟦NOC⟧ Production scopes require Live mode; if the app is still in Development, graduate it before/at
  submission (`SUBMISSION.md` §6, `PROJECT.md` §7 Q1).

> **Order note (verify in console):** in the current flow you generally complete Basic settings + business
> verification, log the successful API calls, then request Advanced Access; the app must be Live for the granted
> Advanced Access to apply to real users. If the console blocks a step until Live, flip to Live once Basic
> settings pass. This exact sequencing is a spot Meta reshuffles — follow the console's inline guidance.

---

## 10. (Optional / later) Lead Ads — extra permissions + webhook

Only if/when social-wiring ingests Facebook Lead Ads. This is a **separate submission** — do not bundle it with
the publish submission.

- **Permissions:** reading leads needs **`leads_retrieval`**, plus **`ads_management`** and **`pages_manage_ads`**
  [12][13]. `ads_management` and `leads_retrieval` are **Advanced-Access** permissions and require Business
  Verification [4].
- **Delivery:** real-time lead delivery uses **Webhooks for Lead Ads** (the `leadgen` field) — your app
  subscribes to the Page's `leadgen` webhook and then reads the lead via the Graph API with `leads_retrieval`
  [12][13].
- **Marketing API** must be added as a product (§2) [14].
- Submit these through the same **App Review → Permissions and Features** flow with their own justifications +
  screencast demonstrating a lead flowing in.

> ⟦NOC⟧ `meta.ads_management` (read campaigns + ad-insights) already ships in the seed
> (`meta.md` §5), but the full lead-ads intake + `leads_retrieval` submission is not yet an active project —
> treat as future work.

---

## 11. Common rejection reasons + how to avoid them

Grounded in Meta's submission/App-Review guidance [1][2] and our own submission notes (`SUBMISSION.md`):

- **Reviewer can't reproduce the flow.** Missing/expired test credentials, app not reachable, login broken →
  provide working sandbox creds + a live URL; verify you can log in yourself first [1][2].
- **Screencast doesn't show the permission in use** (or shows a cut/edited video). One continuous take; show the
  consent screen with the scopes visible, the publish action, and the live post [1] (`SUBMISSION.md` §3).
- **Vague justification.** "Be as specific as possible" per permission — who/what/why [1]. Use `SUBMISSION.md`
  §2 copy.
- **Business Verification incomplete.** Advanced Access is not granted without it [1][9][11]. Start early.
- **"Request Advanced Access" greyed out.** No successful API call recorded yet (or it 4xx'd, or hasn't
  registered — up to 2 days) [1][3].
- **Over-requesting scopes.** Requesting scopes the screencast doesn't demonstrate → extra scrutiny/rejection.
  Request the minimum set (`SUBMISSION.md` §0).
- **Privacy policy missing the Meta Platform disclosure / not reachable.** ⟦NOC⟧ ours already includes it and is
  live (`project_consent_legal_pages`), but re-verify the URL returns 200 before submitting.
- **Redirect URI mismatch / localhost.** The allow-listed OAuth redirect must exactly match the live app's
  production callback (`SUBMISSION.md` §6, `SETUP_META.md` A.3).
- **Wrong Instagram permission variant.** Requesting `instagram_business_content_publishing` (Instagram-Login
  API) when the app implements the Facebook-Login path (which uses `instagram_content_publish`), or vice-versa
  [2][10] (§0.1).

---

## 12. After approval (⟦NOC⟧ hand-off)

1. **Activation smoke** (`PROJECT.md` §6 Phase 3): on a sandbox tenant complete OAuth, confirm the new scopes
   appear in `resolve_oauth_scopes(...)` output, then publish one IG single + one IG carousel + one FB photo;
   capture the live URLs.
2. **State reconciliation:** verify `mc_posts.published_target` / `published_media_id` / `published_permalink` /
   `published_at` reflect the real Meta media id + permalink.
3. **Three-way sync:** update `KB § INTEGRATIONS/meta.md` §5 from "live behind Meta App Review" →
   "approved YYYY-MM-DD"; add a `feedback_meta_app_review_approved_<scope>` memory note.
4. **Keep the gate:** do NOT remove the `422 meta_scope_pending_app_review` surface — it stays as the defensive
   gate for future unapproved scopes.
5. **Ongoing Review:** apps with Advanced Access serving businesses you don't own are subject to Meta's
   **Ongoing Review** to retain access [2] — keep the app compliant after approval.

---

## Sources

Official Meta documentation (fetched):

1. App Review submission guide — <https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide>
2. App Review — Instagram Platform — <https://developers.facebook.com/docs/instagram-platform/app-review/>
4. Permissions Reference — <https://developers.facebook.com/docs/permissions/>
5. Data Deletion Request Callback — <https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback/>
6. Facebook Login for Business — <https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business>
8. Verify your business (Meta Business Help Center) — <https://www.facebook.com/business/help/2058515294227817> · docs upload — <https://www.facebook.com/business/help/159334372093366>
10. Instagram Platform overview (two login APIs) — <https://developers.facebook.com/docs/instagram-platform/overview/>
12. Retrieving Leads (Marketing API) — <https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/lead-ads/retrieving>
13. Webhooks for Lead Ads (`leadgen`) — <https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-leadgen/>
14. Lead Ads guide — <https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/lead-ads>

Reputable 2025/2026 tutorials (fetched via search, corroborating Standard-vs-Advanced + business verification):

3. Business Verification / 30-day API-call rule corroboration — Meta App Review commentary — <https://web-techservices.com/meta-app-review>
7. Documents required for Meta Business Verification — <https://www.adstellar.ai/blog/meta-business-verification>
9. What is Meta Advanced Access (Standard vs Advanced) — <https://singhamandeep.com/what-is-meta-advanced-access/>
11. Meta Ads API access levels (Standard = roles/test users; Advanced = real users at scale) — <https://www.adamigo.ai/blog/meta-ads-api-access-levels-for-agencies>

⟦NOC⟧ internal references (this repo):

- `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md` — adapter surface, scopes, publish methods.
- `projects/meta-app-review-publish-scopes/PROJECT.md` + `SUBMISSION.md` — the ready-to-file submission package (justification copy, screencast script, data-use answers, reviewer instructions, pre-flight checklist).
- `archive/projects/2026-05-16/03-social-wiring-absorption/reference/SETUP_META.md` — app creation, OAuth vs System User token, redirect URIs, common failures.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend/consent-routes-mandate.md` + `project_consent_legal_pages` memory — the `/consent/*` URLs and their Meta disclosure.

---

### Things I could NOT fully verify (do not treat as settled)

- **Exact current console labels / step order.** Meta reshuffles the dashboard and the App-Review wizard order
  frequently; navigate by meaning and trust the console's inline guidance (§0.1, §9).
- **Business Verification as an individual (no CNPJ).** Meta Business Verification expects a registered business
  entity; whether our pessoa-física controller can complete it, and with which documents, must be confirmed in
  Security Center for the account/country (§0, §4).
- **Whether the four supporting read scopes require Advanced Access for our specific app.** The Permissions
  Reference lists them at "Standard Access" [4], but that only covers app-role/test users; the real requirement
  depends on what the Dashboard flags for this app (§0.1, §6).
- **Instagram permission variant naming.** Confirm the Dashboard offers `instagram_content_publish` (classic
  Facebook-Login path our code uses) rather than only the newer `instagram_business_content_publishing` (§0.1).
- **The concrete App ID.** Not committed in-repo (secret); read it from the deployed env / App Dashboard.
