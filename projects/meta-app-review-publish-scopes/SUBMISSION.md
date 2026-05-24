# Meta App Review — Submission Package

> **Ready-to-file package** for the `meta-app-review-publish-scopes` project (🔒 BLOCKED-EXTERNAL).
> Drives the App Review submission that unblocks production publishing for the seed Meta adapter
> (`noctusai_lib.integrations.meta`) and its first consumer, `social-wiring/media_creation`.
>
> **How to use this file:** work top-to-bottom. §1 is what you paste into the App Dashboard "Permissions and
> Features" requests; §2 is the per-permission justification box; §3 is the screencast you record; §4 is the
> Data Use Checkup / privacy answers; §5 is what you hand the Meta reviewer; §6 is the pre-flight checklist
> you clear *before* clicking Submit. Every technical claim cites the file/symbol it's grounded in, so you
> can verify before you file.

---

## 0. What this submission actually requests (and what it does NOT)

The seed Meta adapter ships the full read **and** write surface. Reads work in Development mode with no review.
This submission requests **only the two write scopes the publish feature needs**, both gated behind App Review:

| # | Meta permission | Gates | Code path |
|---|---|---|---|
| 1 | **`pages_manage_posts`** | Publishing a post / photo to a Facebook Page | `MetaOAuthAdapter.publish_facebook_post` (`seed/lib/backend/noctusai_lib/integrations/meta/oauth_adapter.py:322`) → `POST /{page-id}/feed` or `/{page-id}/photos` |
| 2 | **`instagram_content_publish`** | Publishing an Instagram image or carousel | `MetaOAuthAdapter.publish_instagram_media` (`oauth_adapter.py:390`) + `publish_instagram_carousel` (`oauth_adapter.py:463`) → `POST /{ig-user}/media` → `/{ig-user}/media_publish` |

**Verified in code:** the gated-scope list is the adapter module docstring (`oauth_adapter.py:30-39`) and the
`MetaGraphError.requires_app_review` contract (`_meta_api.py:113-125`) — these two scopes (+ the ads scopes,
see below) are the only ones that raise `requires_app_review=True`.

**Explicitly OUT of scope for THIS submission** (per `projects/meta-app-review-publish-scopes/PROJECT.md` §4):
- `ads_read` / `ads_management` — gate the ads-management surface (`create_ad_campaign` etc., `oauth_adapter.py:570-876`). Tracked separately under `meta.ads_management`. Do **not** add them here; bundling them slows review.
- Video / Reels publish scopes — tracked under the sibling `meta-video-reels-publish`, sequenced after this lands.

**Supporting read scopes** — already in `META_KITCHEN_SINK_SCOPES` (`_meta_api.py:56-67`), requested at OAuth
time via `resolve_oauth_scopes(...)` (`_meta_api.py:373`), and **likely needing Advanced Access** alongside the
two write scopes so the publish flow can resolve its targets. List the ones below in the same submission if the
Dashboard shows them as "Standard Access only" (a Page-publishing app realistically needs Advanced Access on
the Page-list + IG-link reads to even *find* the destination to publish to):

| Read permission | Why the publish flow needs it | Code path |
|---|---|---|
| `pages_show_list` | Enumerate the Pages the connected user manages — the publish UI's Page picker. | `list_facebook_pages` → `GET /me/accounts` (`oauth_adapter.py:199`) |
| `pages_read_engagement` | Read back the published Page post's `permalink_url` to confirm + store the live link. | post-publish read-back (`oauth_adapter.py:366-374`) |
| `instagram_basic` | Resolve the IG Business account linked to each Page (the publish target id). | `list_instagram_accounts` (`oauth_adapter.py:272`) |
| `business_management` | Read assets owned by a Meta Business Portfolio — required for virtually every commercial customer whose Pages/IG accounts are BM-owned (user-OAuth tokens silently can't see BM assets otherwise). | adapter auth note (`oauth_adapter.py:6-9`) |

> **Reviewer-pragmatics note:** Meta's reviewer will test that the *two write scopes* work end-to-end. If your
> app is already in Live mode and reads function with Standard Access, you may only need to submit the two write
> scopes. If the Dashboard flags any of the four reads above as "needs Advanced Access," add them with the §2.5
> justifications. Request the minimum set that makes the screencast reproducible — over-requesting triggers
> extra scrutiny.

---

## 1. Permissions to request — paste into the App Dashboard

In **App Dashboard → App Review → Permissions and Features**, request **Advanced Access** for:

1. **`pages_manage_posts`**
2. **`instagram_content_publish`**

(and, only if flagged as Standard-Access-limited for your app:) `pages_show_list`, `pages_read_engagement`,
`instagram_basic`, `business_management`.

Each one opens a justification + screencast form. Use the §2 copy for the justification box and the §3 script
for the recording.

---

## 2. Per-permission use-case justifications (reviewer voice)

Paste one paragraph per permission into its "Tell us how you'll use this permission" box. Each is written in
the concrete who/what/why shape Meta reviewers expect, and references the actual feature.

### 2.1 `pages_manage_posts`

> Our app, **NoctusAI Social Wiring**, lets a business owner generate branded social-media posts (a marketing
> image plus caption and hashtags) inside our media-creation tool, review them, and publish them to the
> Facebook Page they manage. We use `pages_manage_posts` solely to publish that reviewed content to the
> business's own Page: a text/link post via `POST /{page-id}/feed`, or an image post via `POST /{page-id}/photos`
> with the generated caption. The user explicitly clicks "Publish" on a post they have just previewed; we never
> post on their behalf without that action. We do not boost, schedule against other Pages, or manage Pages the
> user does not administer. After publishing we read the post's permalink back to show the user the live link.

### 2.2 `instagram_content_publish`

> NoctusAI Social Wiring publishes the same business-owner-reviewed content to the **Instagram Business account**
> linked to the user's Facebook Page. We use `instagram_content_publish` to run Instagram's standard two-step
> Content Publishing flow: we create a media container (`POST /{ig-user}/media` with the generated image URL and
> caption) and then publish it (`POST /{ig-user}/media_publish`). For multi-image posts we create one child
> container per image, assemble a `CAROUSEL` parent container, then publish it — Instagram's documented carousel
> flow, bounded to 2–10 images. The user reviews and clicks "Publish" each time; we publish only to the IG
> Business account the user manages, never to third-party accounts, and we do not auto-post.

### 2.3 `pages_show_list` (if flagged)

> We use `pages_show_list` to show the user the list of Facebook Pages they manage so they can pick which Page
> to publish to. We call `GET /me/accounts` and render the Pages as a destination picker in the publish dialog.
> We do not use this to enumerate or store Pages the user does not actively select.

### 2.4 `pages_read_engagement` (if flagged)

> After a Page post is published, we use `pages_read_engagement` to read the post's `permalink_url` so we can
> show the user the live link to their published post and store it as the publication record. We read engagement
> data only for posts our app published, to confirm the publish succeeded.

### 2.5 `instagram_basic` + `business_management` (if flagged)

> We use `instagram_basic` to resolve the Instagram Business account connected to the user's selected Facebook
> Page — that account is the publish target for `instagram_content_publish`. We use `business_management` because
> most of our business customers' Pages and Instagram accounts are owned by a Meta Business Portfolio; without
> it the user's token cannot see Business-owned assets and the publish destination cannot be resolved. Both are
> used strictly to locate the user's own publishing destination, not to read or manage unrelated business assets.

---

## 3. Screencast script (the screen recording Meta requires)

Record a single continuous screen capture (≤ 3 minutes, no edits/cuts — Meta rejects cut footage). Narrate each
step out loud or with on-screen captions. The recording **must visibly show** the Facebook login, the OAuth
consent screen listing the requested permissions, the publish action in our UI, and the resulting post live on
Facebook/Instagram. Record against the live `noctus-social-wiring` deployment (tunnelled or VPS URL) with a
**real sandbox** Facebook Page + linked IG Business account.

**Steps:**

1. **Show the app & log in.** Open the Social Wiring app at its public URL. Log in as the test business user.
   *On screen: the app URL bar + the logged-in dashboard.*

2. **Start the Meta connection (OAuth).** Click "Connect Facebook / Instagram." This redirects to Facebook's
   OAuth consent screen. *On screen: the Facebook consent dialog must clearly list `pages_manage_posts` and
   `instagram_content_publish` (and any read scopes requested). Pause ~2s so the reviewer can read them.* Approve.

3. **Show the connected state.** Back in the app, show that the Page + IG Business account are connected (the
   destination picker now lists them). *On screen: the connection status / picker.* This is the
   `MetaConnectionStatus` surface (`oauth_adapter.py:146`, `auth_mode = "user_oauth"`).

4. **Compose a post.** In the media-creation UI, generate or open a post — show the rendered slide image(s) +
   the caption + hashtags. *On screen: the post preview the user is about to publish.*

5. **Publish to Facebook.** Pick the Facebook Page as the destination and click "Publish" (target
   `facebook_photo`). Show the success confirmation + the permalink returned by the app.
   *On screen: success state + the live permalink.*

6. **Show it live on Facebook.** Open the returned permalink in a new tab — show the published post live on the
   Facebook Page. *On screen: the post on facebook.com.*

7. **Publish to Instagram (single + carousel).** Back in the app, publish one Instagram single (target
   `instagram_single`) and one Instagram carousel of 3+ slides (target `instagram_carousel`). Show each success
   state.

8. **Show it live on Instagram.** Open the returned IG permalink(s) — show the published image and the carousel
   live on instagram.com. *On screen: the post(s) on instagram.com.*

9. **Narrate the value.** Close with one sentence: "The business owner reviewed the content and chose to
   publish it to their own Page and Instagram account — that's the only thing these two write permissions do."

> The publish UI maps to `PublishService.publish_post(...)` (`products/social-wiring/backend/app/modules/media_creation/services/publish_service.py:65`)
> with `target ∈ {facebook_photo, instagram_single, instagram_carousel}` and `destination_id` = the Page id (FB)
> or IG user id (IG). On success the response carries `media_id` + `permalink` — that's the link you open in
> steps 6 and 8.

---

## 4. Data handling / privacy answers (Data Use Checkup)

Answer these in the App Dashboard's data-use questionnaire and link your privacy policy.

- **What user data do we access?** The user's Facebook Page list (`pages_show_list`), the linked Instagram
  Business account id (`instagram_basic`), and a long-lived user access token for publishing. We do **not** read
  the user's personal profile beyond `id`/`name` (`me()`, `oauth_adapter.py:184`).

- **How are access tokens stored?** OAuth credentials are persisted through the seed credential store
  (`noctusai_lib.security.token_store.CredentialStore`, `seed/lib/backend/noctusai_lib/security/token_store/types.py:45`)
  and **encrypted at rest with Fernet** (AES-128-CBC + HMAC-SHA256, authenticated symmetric encryption) via
  `noctusai_lib.security.encrypted_tokens` (`encrypt`/`decrypt`, `encrypted_tokens.py:105-139`). The plaintext
  token exists only in process memory at the moment of a Graph call; it is never written to disk in plaintext.
  The encryption key is loaded out-of-band from the ciphertext (env / secret manager — `encrypted_tokens.py:32-45`),
  so a database-only compromise does not expose tokens.

- **Page tokens.** Page access tokens are **never persisted** — they are refetched from `/me/accounts` on each
  call and cached only in-memory per request (`oauth_adapter.py:17-20, 116`). This avoids token-rotation drift
  and means there is no Page-token-at-rest surface at all.

- **Retention.** We retain the encrypted user OAuth credential only while the connection is active. On
  disconnect / revocation we delete it via `CredentialStore.delete(...)` (`token_store/types.py:79`). Published
  posts' metadata (media id, permalink, timestamp) is stored in our `mc_posts` table as the publication record
  (`publish_service.py:131-146`); it contains no personal data beyond the public post link.

- **Deletion / data-deletion request.** A user can disconnect at any time, which deletes the stored credential.
  We honor Meta's Data Deletion Request callback / instructions URL (provide the URL in the Dashboard).

- **No resale / no third-party sharing.** We do not sell, rent, or share Meta user data with any third party.
  Tokens are used solely to publish the user's own reviewed content to the user's own Page/IG account. No data
  is used for advertising targeting or sold to data brokers.

- **No silent failure.** When a gated scope is not yet approved, the adapter raises `MetaGraphError` with
  `requires_app_review=True` (`_meta_api.py:113-125`) which the app surfaces as a `422 meta_scope_pending_app_review`
  (`publish_service.py:123-129`) — it never fakes a successful publish. (This is internal correctness signalling,
  not a data-use answer, but it confirms the app never silently mishandles a permission state.)

---

## 5. Reviewer / test-user instructions

Hand these to Meta as the "Instructions for testing" so a reviewer can reproduce the publish flow end-to-end.

1. **Test app URL:** `<fill in the live noctus-social-wiring URL — tunnelled or VPS>`.
2. **Test credentials:** `<fill in the sandbox business-user login email + password>` — a Meta-test-user / sandbox
   tenant whose Facebook Page (`<Page name/id>`) is linked to an Instagram Business account (`<IG handle>`).
3. **Reproduce the publish flow:**
   a. Log in with the test credentials.
   b. Click "Connect Facebook / Instagram" → approve the OAuth consent (it requests `pages_manage_posts` +
      `instagram_content_publish`).
   c. Open the pre-seeded sample post (or generate one) in the media-creation tool.
   d. Select the Facebook Page and click **Publish** → a post appears on the Page; the app shows the permalink.
   e. Select Instagram and **Publish** a single image, then a 3-slide carousel → both appear on the IG account.
4. **What to expect:** each publish returns a `media_id` + live `permalink`. The posts are visible on the
   sandbox Page/IG account. No personal data beyond the user's own Page/IG content is touched.
5. **Behavior before approval (so the reviewer isn't surprised):** until these scopes are approved on the app,
   the same flow returns `422 meta_scope_pending_app_review` — that is the deliberate gate, not a bug. With the
   scopes approved (or with a System User token that has them), the flow completes as above.

> Tip: bring up a fresh container + tunnel for the review window per `projects/.../PROJECT.md` §10 (Phase 3 notes)
> so the reviewer hits a clean, current build.

---

## 6. Pre-submission checklist

Clear every box before clicking **Submit for Review**. Each is from `PROJECT.md` §2 / §6 / §7 with what's needed.

- ☐ **Meta App is in Live mode** — production scopes require it. *What's needed:* toggle the app to Live in the
  Dashboard (App Settings). If still in Development, graduate it first (`PROJECT.md` §7 Q1).
- ☐ **Single platform Meta App confirmed** — one App ID for the whole fleet (the dual-auth design assumes a
  workspace-global System User Token). *What's needed:* confirm the App ID you're submitting (`PROJECT.md` §7 Q2).
- ☐ **Business verification complete** — Meta requires the developer business to be verified for Advanced Access
  to Page/IG write scopes. *What's needed:* complete Business Verification in Business Settings (legal name,
  documents) — this can itself take days, so start it early.
- ☐ **Privacy policy URL is public + reachable** — required field; must describe how Meta data is handled.
  *What's needed:* a live URL covering §4 above. If it doesn't exist for the publishing surface, file the
  prerequisite `meta-app-public-policies` first (`PROJECT.md` §2, §7 Q3, §8 soft-blocker).
- ☐ **Data Use / Data Deletion URL** — public URL or callback for data-deletion requests. *What's needed:* a
  live data-deletion instructions URL configured in the Dashboard.
- ☐ **App icon (1024×1024) + app name + category** set. *What's needed:* upload a square icon, set a clear app
  name and category in App Settings → Basic.
- ☐ **Valid OAuth redirect URI(s)** allow-listed — must match the live app's callback exactly (production URL,
  not localhost). *What's needed:* add the deployed redirect URI under Facebook Login → Settings (dev↔prod
  parity: the slim prod image serves a real domain, not `localhost`).
- ☐ **Live, reachable demo deployment** — the reviewer must be able to exercise `/publish`. *What's needed:* a
  running `noctus-social-wiring` container at a public URL (tunnel or VPS), current build (`PROJECT.md` §2, §10).
- ☐ **Sandbox tenant ready** — a Meta-test-user / sandbox business with a Facebook Page linked to an IG Business
  account, plus a pre-seeded sample post to publish. *What's needed:* set up the test user + assets and verify
  you can log in (you'll paste these into §5).
- ☐ **Screencast recorded** — single continuous capture per §3, ≤ 3 min, showing login → consent (scopes
  visible) → publish → live post on FB + IG. *What's needed:* the recording file, one per permission form (or a
  single recording referenced from each).
- ☐ **Justification copy ready** — §2 paragraphs pasted into each permission's form. *What's needed:* nothing
  beyond copy-paste; tailor the bracketed names.
- ☐ **Only the in-scope permissions requested** — `pages_manage_posts` + `instagram_content_publish` (+ flagged
  reads). *What's needed:* confirm you did NOT add `ads_*` or Reels scopes (those are separate projects, §0).
- ☐ **Responder lined up for reviewer follow-ups** — Meta closes submissions if clarifications go unanswered.
  *What's needed:* commit to responding within 48h (`PROJECT.md` §6 Phase 2).

---

## 7. After approval (hand-off to PROJECT.md Phase 3–4)

Not part of the submission, but the immediate next steps once Meta approves — so nothing is dropped:

1. **Activation smoke** (`PROJECT.md` §6 Phase 3): on a sandbox tenant, complete OAuth, confirm the new scopes
   appear in `resolve_oauth_scopes(...)` output (`_meta_api.py:373`), then publish one IG single + one IG
   carousel (3+ slides) + one FB photo. Capture the live URLs.
2. **State reconciliation:** verify `mc_posts.published_target` / `published_media_id` / `published_permalink` /
   `published_at` reflect the real Meta media id + permalink (`publish_service.py:131-146`).
3. **Three-way sync** (`PROJECT.md` §6 Phase 4): update `KB § INTEGRATIONS/meta.md` §5 row from
   "live behind Meta App Review" → "approved YYYY-MM-DD"; add the `feedback_meta_app_review_approved_<scope>`
   memory note.
4. **Keep the gate:** do NOT remove the `422 meta_scope_pending_app_review` surface — it stays as the defensive
   gate for future unapproved scopes (`PROJECT.md` §9).
