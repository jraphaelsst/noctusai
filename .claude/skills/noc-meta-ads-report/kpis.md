# Meta Ads KPI catalogue (noc-meta-ads-report)

Every KPI the report and the future in-app analytics compute, with its exact Insights formula.
Researched 2026-11-26 (noc-research; Meta developer docs = T1; benchmarks = T3/T4). Confidence is
stated per row. **Benchmarks:** no reliable Brazilian real-estate source exists, so the baseline is
**our own account's medians** (the lifetime per-objective numbers from earlier runs). External numbers
are context only.

Leads always = `actions[onsite_conversion.lead_grouped]`. Never use `lead` (it can double-count form +
pixel), and don't rely on `results`, which is absent for lead ads under the system-user token (verified
2026-11-26).

## 1. Delivery and cost

| KPI | Formula | Why | Notes |
|---|---|---|---|
| Spend · Impressions · Reach | `spend` · `impressions` · `reach` | base | Reach is estimated and **not additive** across ads or days |
| Frequency | `impressions / reach` | fatigue | Recompute it; never average it |
| CPM | `1000 × spend / impressions` | auction cost | Placement and age drive it more than creative does |
| Link CTR | `inline_link_clicks / impressions` | real intent | `ctr` (all clicks) is inflated by expanding the ad and opening the profile. Report it, but don't judge by it |
| Cost per link click | `cost_per_inline_link_click` | | `inline_link_clicks` uses a fixed 1-day-click window |
| Outbound CTR | `outbound_clicks_ctr` | site traffic | Only for traffic or site objectives |

## 2. Lead funnel

| KPI | Formula | Why | Notes |
|---|---|---|---|
| Form leads | `actions[onsite_conversion.lead_grouped]` | outcome | Per objective; never blend objectives |
| CPL | `spend / form leads` | core | Compare within **one attribution window** (§6) |
| Click → lead | `form leads / inline_link_clicks` | form friction | A drop here means the form (length, questions) is the problem |
| Form open → submit | `form leads / instant_experience_clicks_to_open` | form friction | ⚠️ unverified that this field counts form opens |
| CPQL (cost per qualified lead) · cost per visit | `spend / CRM-qualified` · `spend / visits` | real ROI on R$1–10M properties | Needs the CRM join (`leadgen` `lead_id` → social-wiring leads). **Not yet wired** |
| Speed to lead | first contact time − lead `created_time` | conversion driver | CRM side |

## 3. Video retention (per creative)

| KPI | Formula | Read it as | Benchmark |
|---|---|---|---|
| **Hook rate** | `actions[video_view]` (3 s) / `impressions` | stops the scroll | Billo H1-2026: average 25%, good ≥30% (T4, sales ads) |
| **Hold rate** | `video_thruplay_watched_actions / actions[video_view]` | holds attention | no reliable benchmark |
| 6 s / 3 s | `video_6_sec_watched_actions / video_view` | early hold | available (verified on v27) |
| **Retention curve** | `video_play_curve_actions[0].value` = 22 points, % of plays reaching each bucket: idx 0–14 = second 0–14; 15–17 = [15,20) [20,25) [25,30); 18–20 = [30,40) [40,50) [50,60); 21 = >60 s | where people leave | Report 1 s / 3 s / 5 s / 10 s / 14 s. The biggest drop is usually between 1 s and 3 s |
| Quartiles | `video_p25/p50/p75/p95/p100_watched_actions` | depth | Counts include plays that skipped ahead |
| Avg watch | `video_avg_time_watched_actions` (s) | | Includes replays within one impression |
| ~~2 s continuous~~ | `video_continuous_2_sec_watched_actions` | — | **Omitted by Graph** on our account (v22/v25/v27). Use curve index 2 |

`video_*` fields **cannot be combined with hourly breakdowns**, and quartiles don't support `region`.

## 4. Creative fatigue and quality

| Signal | Rule | Notes |
|---|---|---|
| Fatigue | Over the ad's own daily series: frequency ↑, link CTR ↓, CPM ↑, CPL ↑, each versus its first 7 days | Meta's `creative_fatigue` webhook (ad_account) reports LOW / MEDIUM / HIGH and could be a push alert in-app |
| Rankings | `quality_ranking`, `engagement_rate_ranking`, `conversion_rate_ranking` | `UNKNOWN` under ~500 impressions per ad. They still work on v27 |
| Learning | ad set `learning_stage_info` (status, attribution windows, last significant edit) | Every pause, new ad or targeting edit resets it. "50 events in 7 days" is unverified folklore |

## 5. Breakdowns

Always pull these: `age,gender` · `publisher_platform,platform_position` · `region` · `device_platform`
· `hourly_stats_aggregated_by_advertiser_time_zone` (no video fields; reach and frequency come back 0).
Pull them **twice**: lifetime and the **window** (`--window-since`), otherwise the "recent" tables
silently mix in old delivery.

## 6. Attribution

- Each ad set has its own setting (`learning_stage_info.attribution_windows` / `attribution_spec`). The UI
  and `value` use it.
- The extractor also requests `action_attribution_windows=["7d_click","1d_view"]`, so every action keeps
  `value_7d_click` / `value_1d_view`. When an ad set's setting changed, compare runs on `value_7d_click`.
- Meta changed result measurement on 2026-03-17. Never compare across that date.

## 7. API facts (verified 2026-11-26)

- Pin **v27.0**. Expired versions are silently served as the oldest live one (v22 → v25).
- Our app is on the **`development_access`** tier: `ads_insights` quota per account per hour =
  600 + 400 × active ads. Read the `x-fb-ads-insights-throttle` header. Throttling = error code 4/17/613.
- For big pulls, use async report runs (`POST /insights` → `report_run_id` → poll `async_status`).
- Days with zero delivery return no daily row (that's not missing data).
- Meta also hosts an **Ads MCP server** (`https://mcp.facebook.com/ads`, OAuth per user). It is useful
  for ad-hoc agent queries; our in-app path stays the system-user token + seed `MetaAdapter`.
