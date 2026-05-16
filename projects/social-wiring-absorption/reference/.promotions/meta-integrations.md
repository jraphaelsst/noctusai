---
slug: meta-integrations
origin:
  - products/youtube-crawler/backend/app/services/meta/
  - products/youtube-crawler/backend/app/routers/meta_router.py
  - products/youtube-crawler/backend/tests/services/test_meta_integration.py
  - docs/integrations/META_API_REFERENCE.md
intended_noc_destination: noctusai_lib/integrations/meta/
layer_rationale: |
  Six-layer model: integration adapter — belongs in
  `noctusai_lib.integrations.meta/`, sibling to the
  `google_calendar/` + `google_maps/` adapters. The package
  ships the canonical Protocol + Fake + Real(OAuth) + factory
  shape (same as drive_api / calendar) so any future product
  that wants Facebook + Instagram read access can wire it in
  with one factory call.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Any product wanting social
  presence reporting (Therapy practice's IG metrics, ERP client
  comms via FB page DMs, daily-life social digest) will use this.
  Q2 — Variance? None at Protocol level. Per-product variance
  lives in WHICH metrics each product asks for (default metric
  list lives in mappers.py constants — easy to override per
  consumer).
  Q3 — Existing seed coverage? None. This is the FIRST Meta-side
  surface in noc. No competing module to dedupe against.
  Q4 — Fake+Real? Yes — FakeMetaAdapter ships alongside.
  OAuth path is the "real" today (no service-account equivalent
  on Meta's side — service-accounts are not a Meta concept).
  Q5 — Migration cost? Low. Same shape as drive_api/. ~700 LoC
  total split across 6 files.
  Q6 — Premature lift risk? Low. The pattern (OAuth + page tokens
  + insights) is stable Graph behavior since v2.x; mirrors the
  whatsapp-scheduling reference repo's posture.
dependencies_on_other_additions:
  - drive-api-client     # same CredentialStore mechanism reused
  - google-integrations  # same factory shape it follows
promoted_on: not-yet
---

## Why this addition exists

User asked for FB + IG integration in the same posture as the Google
integrations ("port Meta into our environment to wire my Facebook and
Instagram accounts to the platform"). Scope clarified to **read-only
v1**, **TikTok deferred to a separate future project**, **own branch**.

The branch `feat/meta-integrations` ships:

1. A Meta Graph API adapter package (Protocol + Fake + OAuth + factory)
2. An OAuth bootstrap router (`/api/meta/{status,oauth/start,oauth/callback}`)
3. Seven chatbot tools that read FB Pages / FB posts / IG accounts /
   IG media + insights
4. 19 mocked tests covering mappers, error envelope parsing, OAuth
   token exchange, factory selection, Fake adapter
5. A full internal API reference doc (`docs/integrations/META_API_REFERENCE.md`)
6. .env.example fields + AGENT.md §3.11

## Integration notes for noc-side

When promoting:

1. **Move `meta/` → `noctusai_lib/integrations/meta/`.** Same shape
   as `google_calendar/` and `google_maps/`. Don't trim the Fake.

2. **Provider key.** The `META_PROVIDER = "meta"` constant in
   `oauth_adapter.py` is the CredentialStore key. If noc already
   has a per-org provider namespace convention (e.g.
   `social.meta` instead of just `meta`), rename at promotion time;
   it's a single grep.

3. **HTTP plumbing.** `_meta_api.py` is httpx-only with no SDK
   dependency. Lift verbatim. The `MetaGraphError` typed exception
   should stay alongside (consumers branch on `is_auth_error` /
   `is_rate_limited`).

4. **Token chain.** This adapter intentionally does NOT persist the
   per-Page tokens that `/me/accounts` returns — they're refetched
   fresh on every adapter construction. Cheap (one paged Graph call)
   and avoids token-rotation drift. If a future consumer wants to
   cache them, do so at the `noctusai_lib` layer with an explicit
   TTL, not at the consumer layer.

5. **Tool surface.** The 7 chatbot tools + their intake handlers are
   product-specific (the descriptions reference real-estate context).
   At promotion, generalize the tool DESCRIPTIONS to a neutral copy
   and keep the handlers in product code, OR factor them into a
   `noctusai_lib.chatbot.meta_tools` module that returns the tool
   manifests for any product's chatbot to register.

6. **Setup guide.** `docs/integrations/META_API_REFERENCE.md` is the
   single source of truth for "how do I create a Meta app and connect
   it?" When promoting, move that doc to
   `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md` and add it to
   `KNOWLEDGE-BASE/INDEX.md` via the standard pre-commit hook.

7. **App Review.** All consumers of the read scopes (`pages_show_list`,
   `pages_read_engagement`, `instagram_basic`, `instagram_manage_insights`)
   need Meta's App Review approval to leave dev mode. Document this
   prominently in the noc setup guide — current `META_API_REFERENCE.md`
   already calls it out in §1.

## Future work (NOT in this promotion)

- **Posting** — adding `pages_manage_posts` / `instagram_content_publish`
  scopes + create-post endpoints. Requires App Review per scope.
- **TikTok** — separate package `noctusai_lib.integrations.tiktok/`
  under its own branch / promotion. Same Protocol + Fake + OAuth
  shape; Content Posting API approval is the gating step.
- **Webhook subscriptions** — Meta supports realtime webhooks for
  Page updates, IG comments, etc. Out of v1; would land via
  `noctusai_lib.integrations.meta.webhooks/` mirroring the
  `noctusai_lib.integrations.whatsapp.webhooks/` shape.
- **Per-product metric customization** — the default metric lists
  in `mappers.py` are conservative. A `MetricBundle` value object
  could let consumers ask for additional metrics without touching
  the adapter.
