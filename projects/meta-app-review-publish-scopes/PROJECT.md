# meta-app-review-publish-scopes — Project Document

> **Filed 2026-05-20** as the **§2.13a class-1 external-blocker** follow-up to `media-creator-w2-4` close-out. User explicitly authorized filing despite the no-defer-mid-flight rule because the blocker is genuinely external (Meta operational/policy) — not "needs a user decision". Self-contained (durable-docs rule). Symbol-first authoring per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 🔒 **BLOCKED-EXTERNAL** — waiting on Meta App Review approval. No code work blocked; this project tracks the operational submission + post-approval activation.
- **Owner / stakeholders:** USER (joaoraphaelsst) · architect
- **Related docs:**
  - `KB § INTEGRATIONS/meta.md` § publish methods (the live code that needs the scopes)
  - `KB § INTEGRATIONS/oauth-patterns.md` § Meta token-chain + auth-mode matrix
  - `seed/lib/backend/noctusai_lib/integrations/meta/oauth_adapter.py` — the live adapter that raises `MetaGraphError.requires_app_review=True` until the scope lands
  - `products/social-wiring/backend/app/modules/media_creation/services/publish_service.py` — first consumer; surfaces 422 `meta_scope_pending_app_review` request-time
- **Project slug:** `meta-app-review-publish-scopes` (root `projects/` — cross-product platform-infra: every product that mounts the Meta adapter benefits)

---

## 1. Context & Purpose

The Meta seed (`noctusai_lib.integrations.meta`) ships the publish surface end-to-end — `publish_facebook_post` / `publish_instagram_media` / `publish_instagram_carousel` on Protocol + Fake + Real(OAuth). The first consumer is `social-wiring/media_creation/services/publish_service.py` (`POST /api/media-creation/posts/{id}/publish`). Tests are green on the Fake path.

**The external blocker.** Production calls require Meta App Review approval for two write scopes:
1. `pages_manage_posts` — gates Facebook Page feed / photo publish.
2. `instagram_content_publish` — gates Instagram media + carousel publish.

Until these are approved on our Meta App, the live adapter raises `MetaGraphError.requires_app_review=True` on every publish call, which the consumer surfaces as **422 `meta_scope_pending_app_review`** to the FE. Loud, deterministic, never silent — but no IG/FB post lands.

**This project tracks the App Review submission + the post-approval activation drill.** No code work is required to *begin* — the adapter is ready.

---

## 2. Confirmed constraints (external + operational)

- **No code path needed.** The Protocol/Fake/Real/factory + consumer endpoint are live. App Review is purely an operational submission.
- **Meta App Review SLA**: 5-7 business days typical, longer on first submission for a new app or for sensitive scopes. Multiple submission rounds possible if Meta asks for screencast / use-case clarifications.
- **Submission needs a working demo** — Meta reviewers will exercise the publish flow against a sandbox / sample user. The `noctus-social-wiring` container with the `/publish` endpoint + a tunnelled URL satisfies this.
- **Per-app scope** — the approval attaches to the Meta App ID, not to a tenant. Once approved, every tenant whose user-OAuth flows through this App benefits.
- **Privacy policy + Data Use policy required** — Meta requires a public URL for both. If we don't have these for the publishing surface, that's a prerequisite (and arguably the *real* class-1 blocker for filing).

---

## 3. Design principles

1. **No code preemption.** Adapter ships ready; nothing to write.
2. **Activation = a configuration flip + a smoke**. Once the scope is approved on the Meta App side, the next real-token user (system-user or per-tenant OAuth) automatically gets it — the same code path the Fake exercises today.
3. **Post-approval smoke is mandatory.** Verify against a real sandbox IG/Page that one of each (single, carousel, FB photo) lands. Capture the published URL → publication-state row reconciliation.

---

## 4. Scope

**In scope:**
- Author / collect the App Review submission package (use-case copy, screencast, privacy/data-use links).
- Submit through the Meta App Dashboard (`developers.facebook.com/apps/<our-app>/app-review/`).
- Iterate on reviewer requests until approved.
- Post-approval activation smoke: one IG single + one IG carousel + one FB photo published end-to-end on a sandbox tenant.
- Update `KB § INTEGRATIONS/meta.md` §5 row from "live behind Meta App Review" → "approved YYYY-MM-DD" with the approval date.

**Out of scope:**
- Any seed/consumer code change. (If a reviewer asks for code change — re-scope and file a sibling project.)
- Ads-write scopes (`ads_management`) — covered by `meta.ads_management` separately.
- Video / Reels publish scopes — covered by `meta-video-reels-publish` (sibling, sequenced after this lands).

---

## 6. Implementation phases

### Phase 1 — Submission package assembly
- [ ] Confirm Meta App ID + which app environment (Live vs Development).
- [ ] Confirm privacy policy URL + data-use disclosure URL exist; if not, file `meta-app-public-policies` as a prerequisite.
- [ ] Author a use-case narrative per scope (≤ 1 paragraph each: who, what, why we need write access — "we publish branded carousel posts on behalf of tenant-owned IG/FB Pages who have consented to the Meta OAuth scope during onboarding").
- [ ] Record a screencast (≤ 3 min) showing the consumer flow: tenant connects → generates a post → reviews → publishes → sees the post live on IG/FB.

### Phase 2 — Submit + iterate
- [ ] Submit through Meta App Review dashboard.
- [ ] Respond to any reviewer requests within 48h (delay risks the submission being closed and needing re-submission).
- [ ] Track submission state in §11 below.

### Phase 3 — Post-approval activation smoke
- [ ] On a sandbox tenant, complete the OAuth flow → confirm the new scopes are in the granted-scope list (use `noctusai_lib.integrations.meta.resolve_oauth_scopes`).
- [ ] Run one IG single publish · one IG carousel (3+ slides) · one FB photo. Capture published URLs.
- [ ] Verify `mc_posts.published_target` / `published_media_id` / `published_permalink` / `published_at` reflect the publish.

### Phase 4 — Three-way sync
- [ ] `KB § INTEGRATIONS/meta.md` §5 row updated with approval date.
- [ ] Memory note: `feedback_meta_app_review_approved_<scope>` capturing the approval date + any reviewer notes worth carrying forward.
- [ ] CLAUDE.md — no change expected (the App-Review-gated wording in §2 stays correct as a general principle for *future* write scopes).

---

## 7. Open questions

1. **Do we have a Live Meta App yet, or are we still on the Development app?** Recommendation: required to be Live before submission for production scope. If Development, the prerequisite is to graduate the app to Live.
2. **Single Meta App for the whole platform, or per-product?** Recommendation: single platform app (already the assumption embedded in the dual-auth design — System User Token is workspace-global). Confirm.
3. **Privacy policy + data-use docs already exist?** Recommendation: if not, prerequisite project `meta-app-public-policies` is filed first.

---

## 8. Dependencies & blockers

- **Hard blocker:** Meta App Review approval timeline (5+ business days per round, multiple rounds possible).
- **Soft blocker:** Public privacy + data-use policy URLs.
- **No code blocker** — the adapter is shipped + tested.

---

## 9. Success criteria

- Meta App Review approval received for both `pages_manage_posts` and `instagram_content_publish`.
- One real publish per surface (IG single / IG carousel / FB photo) lands end-to-end on a sandbox tenant.
- `mc_posts` publication state row reflects the real Meta media id + permalink.
- `KB § INTEGRATIONS/meta.md` §5 reflects the approval.
- The 422 `meta_scope_pending_app_review` shape stays as a defensive surface for *future* unapproved scopes — never removed.

---

## 10. How to use this plan

This is a tracking / operational project, not a dispatch-an-engineer project. The user / architect drives the submission directly. No worktree needed; no `engineer-default` dispatch needed. Phase 3 (activation smoke) WILL benefit from a fresh `noctus-social-wiring` container + a real sandbox IG/FB Page.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed per user's explicit request as a class-1 external-blocker follow-up to `media-creator-w2-4` close-out. The seed publish surface is live but unusable in production until Meta approves the write scopes. | Architect |
