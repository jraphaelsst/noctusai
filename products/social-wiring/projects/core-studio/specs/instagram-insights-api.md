# Instagram insights API — implemented contract (social-wiring backend)

Status: implemented on `feat/sw-instagram-insights-be` (2026-10-06). Build the
frontend against THIS file. Deviations from the scratch contract are listed
at the end.

Owner decisions this implements:

- Instagram authenticates via **Instagram Business Login** (`integration_accounts.provider = "instagram"`), not Facebook Login.
- **Every post, every day**, every metric Meta serves for the media type.
- Grid **newest first**; a post opens a modal with its insights over time, most relevant metric first.

## Conventions

- Every route needs a session (no session gives a strict **401**). The org comes from the session, never from a parameter.
- `{account_id}` is an `integration_accounts.id` with `provider="instagram"` in the session's org. These cases return **404**:
  - another org's account
  - a `provider="meta"` row
  - a missing row
- A malformed `{account_id}` returns **400**.
- Optional `?marca_id=<uuid>` on every route pins the account to a marca. A mismatch returns **404**.
- GET routes read **our stored data**. They never call Graph. Data appears after the first sync, from the daily job or `POST …/sync`.
- **`null` means Meta did not serve the metric** (unsupported for that media type, hidden likes, or no sync yet). It is never coerced to `0`. Render it as "—", not "0".
- Dates are `YYYY-MM-DD` in the America/Sao_Paulo calendar. Timestamps are ISO-8601 UTC.
- Metric `format`:
  - `"int"`: a count
  - `"duration_ms"`: milliseconds
  - `"percent"`: 0–100

## Endpoints

### `GET /api/instagram/accounts/{account_id}/profile`

```json
{
  "account_id": "uuid", "marca_id": "uuid|null", "ig_user_id": "1784…|null",
  "username": "acme|null", "name": "Acme|null", "profile_picture_url": "url|null",
  "followers_count": 1500, "follows_count": 12, "media_count": 230,
  "biography": "…|null", "website": "…|null",
  "last_synced_at": "2026-10-06T08:30:00+00:00|null",
  "insights_scope_granted": true
}
```

The data comes from the last sync. Before the first sync, only `username` (the label from OAuth time) is set and everything else is `null`. When `insights_scope_granted` is `false`, the account must reconnect: show a "Reconectar Instagram" CTA.

### `GET /api/instagram/accounts/{account_id}/profile/trend?days=30`

`days` is 1–730 (default 30). Points are returned in ascending date order, one per day the job ran.

```json
{
  "points": [{ "date": "2026-10-06", "followers_count": 1500, "reach": 900, "views": 2000,
               "accounts_engaged": 80, "total_interactions": 120, "likes": 90, "comments": 10,
               "shares": 5, "saves": 15, "replies": null, "reposts": null,
               "profile_links_taps": 3, "follows_and_unfollows": 7,
               "follows_count": 12, "media_count": 230 }],
  "metrics": [{ "key": "followers_count", "label": "Seguidores", "format": "int", "priority": 1 }, …]
}
```

- `followers_count`, `follows_count` and `media_count` are the values at capture time.
- Every other metric is the IG User insights `total_value` for the **previous** BRT day. The day-D row covers the window D-1 00:00 to D 00:00. Meta says data can lag by up to 48h.
- The metric order is: followers_count, reach, views, accounts_engaged, total_interactions, likes, comments, shares, saves, replies, reposts, profile_links_taps, follows_and_unfollows, follows_count, media_count.

### `GET /api/instagram/accounts/{account_id}/media?cursor=&limit=24`

`limit` is 1–100 (default 24). Results are ordered **`timestamp DESC, id DESC`** with server-side keyset pagination.
- Pass back the opaque `next_cursor`. `null` means this is the last page.
- An invalid cursor returns **400**.

```json
{
  "items": [MediaItem],
  "next_cursor": "opaque|null"
}
```

`MediaItem`:

```json
{
  "id": "17895…",                      // IG media id (use it in the history URL)
  "media_type": "IMAGE|VIDEO|CAROUSEL_ALBUM|null",
  "media_product_type": "FEED|REELS|STORY|AD|null",
  "caption": "…|null", "permalink": "https://www.instagram.com/p/…|null",
  "thumbnail_url": "url|null",          // VIDEO only (Meta); for IMAGE use media_url
  "media_url": "url|null",              // omitted by Meta for copyrighted media
  "timestamp": "2026-10-05T12:00:00+00:00",
  "like_count": 42,                     // null when the owner hides like counts
  "comments_count": 3,
  "latest": { "views": 500, "reach": 300, "saved": null, … } ,   // last snapshot, or null before the first one
  "latest_snapshot_date": "2026-10-06|null",
  "synced_at": "2026-10-06T08:30:00+00:00"
}
```

Live Stories are included while they are live, with `media_product_type="STORY"`. They stay in the catalog afterwards, and their history stops once Meta stops serving story insights (24h).

### `GET /api/instagram/accounts/{account_id}/media/{media_id}/insights/history?days=90`

`days` is 1–730 (default 90). An unknown media id returns **404**.

```json
{
  "media": MediaItem,
  "points": [{ "date": "2026-10-05", "views": 480, "reach": 290, "ig_reels_avg_watch_time": 4200, "likes": null, … }],
  "metrics": [{ "key": "views", "label": "Visualizações", "format": "int", "priority": 1 }, …]
}
```

- `metrics` lists exactly the metrics requested for this media type, ordered by `priority` (1 = most relevant). Each point has `date` plus one key per metric.
- Use `metrics[*]` both for the KPI row (latest point) and for the chart's metric selector.

### `POST /api/instagram/accounts/{account_id}/sync?force=false`

This runs today's catalog and snapshot capture immediately. It is the same code as the daily job, so it can take a while on large accounts (one Graph call per post).

**200** response:

```json
{ "status": "done|partial|skipped", "snapshot_date": "2026-10-06",
  "media_synced": 230, "stories_synced": 2, "snapshots_written": 229,
  "profile_snapshot_written": true, "media_failed": 1, "media_skipped": 0,
  "errors": ["M123: [10] Not enough viewers"] }
```

Statuses:

| `status` | Meaning |
|---|---|
| `skipped` | Today was already done, or another run started less than 2h ago. Pass `force=true` to re-run. Re-runs overwrite the day's rows and never duplicate them. |
| `partial` | Some posts failed. The details are in `errors`, and those posts keep their previous `latest`. |

Other responses:

| Response | Meaning |
|---|---|
| **409** `{requires_reconnect: true, missing_scopes: ["instagram_business_manage_insights"], error}` | The account was connected before the insights scope existed, or the scope was unticked on consent. |
| **409** `{requires_reconnect: true, error}` | The account is not `validated`, or no token is stored. |
| **200** `{requires_app_review: true, error}` | Graph permission error, using the shared Meta mapping. |
| **502** `{error, code, fbtrace_id}` | Any other Graph error, such as an expired token (code 190). |

## Metrics per media type and priority

The list of metrics per media type is Meta knowledge and lives in the seed, in `noctusai_lib.integrations.meta.instagram_insights.IG_MEDIA_METRICS_BY_PRODUCT_TYPE`. Labels and priorities are product-side, in `app/modules/instagram/metrics.py`.

| Priority | REELS | FEED (image / carousel) | STORY |
|---|---|---|---|
| 1 | views — Visualizações | views | views |
| 2 | reach — Contas alcançadas | reach | reach |
| 3 | ig_reels_avg_watch_time — Tempo médio assistido (ms) | total_interactions — Interações | replies — Respostas |
| 4 | total_interactions | likes — Curtidas | navigation — Navegação |
| 5 | likes | comments — Comentários | total_interactions |
| 6 | comments | shares — Compartilhamentos | shares |
| 7 | shares | saved — Salvamentos | profile_visits — Visitas ao perfil |
| 8 | saved | profile_visits | follows — Novos seguidores |
| 9 | reels_skip_rate — Taxa de pulo (3s) (%) | follows | profile_activity — Ações no perfil |
| 10 | ig_reels_video_view_total_time — Tempo total assistido (ms) | profile_activity | reposts — Republicações |
| 11 | reposts | reposts | facebook_views — Visualizações no Facebook |
| 12 | facebook_views | facebook_views | |
| 13 | crossposted_views — Visualizações (cross-post) | | |

Rationale for the order:
- All types start with distribution (views, reach).
- **Reels** next show retention (average watch time), the main ranking signal, then engagement.
- **Feed** next shows engagement, then profile conversion.
- **Stories** next show story-native responses (replies, navigation).
- Cross-post counters always come last.

When Graph doesn't return `media_product_type`, the product type is inferred: `VIDEO` maps to REELS, anything else to FEED. The stored value stays `null`.

## Sources (Meta, Instagram API with Instagram Login)

- Media insights: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
- User insights: https://developers.facebook.com/docs/instagram-platform/api-reference/instagram-user/insights
- Media fields: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media
- /me fields: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/get-started
- Media/stories edges: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/
- Access levels / App Review: https://developers.facebook.com/docs/instagram-platform/overview/

## Deviations from the scratch contract (`ig-insights-contract.md`)

1. **`profile_views` is dropped from the trend.** Meta's current Instagram-Login user-insights metric list has no `profile_views` (or `follower_count`/`website_clicks`). Follower growth comes from the daily `followers_count`. The trend adds the other served account metrics: likes, comments, shares, saves, replies, reposts, profile_links_taps, follows_and_unfollows, follows_count, media_count.
2. **Trend `metrics[]` entries also carry `format` and `priority`**, the same shape as the history `metrics[]`.
3. **Extra fields:**
   - Profile: `account_id`, `marca_id`, `ig_user_id`, `insights_scope_granted`
   - MediaItem: `latest_snapshot_date`
   - Sync: `snapshot_date`, `stories_synced`, `profile_snapshot_written`, `media_failed`, `media_skipped`, `errors`
4. **`?days=` on history** (default 90) and **`?force=` on sync**.
5. **`status` values** for sync are `done | partial | skipped`, plus the 409 and 200 structured responses above.
6. **MediaItem `like_count`/`comments_count` are nullable** (Meta omits like counts when the owner hides them).
