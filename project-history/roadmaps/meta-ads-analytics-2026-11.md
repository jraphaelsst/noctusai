# meta-ads-analytics-2026-11 — campaign analytics method → API tool → new campaigns UI

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`). Follow-on to
> [`meta-ads-console-2026-07.md`](meta-ads-console-2026-07.md), the read-only console in social-wiring on
> the System-User token. That roadmap built the plumbing; this one builds the **analysis method** and
> **redesigns the UI** around it. Promote into it, never fork it.

## Origin (2026-11-26, owner request)

The owner asked for:
1. A quality campaign-analysis tool with more metrics, incl. **retention and per-time retention**,
   researched online.
2. **No browser** if an API or MCP route exists, because the method will be consolidated into the app
   "after it's done and refined" to analyse our own campaigns.
3. Order: **skill first** (built during the analysis, validated on a second property), **then the API
   code**, **then the campaigns UI**. The UI is today "only fetched and thrown there". Its layout
   reference is the owner's imovelweb listings panel (`/panel/avisos`), studied for layout, effects,
   transitions, icons and widgets. We take the patterns, not the brand.

## Phases

| # | Phase | Status | Exit criteria |
|---|---|---|---|
| **1** | Skill `noc-meta-ads-report` + KPI catalogue + API extractor (dev-phase script) + `kpi_pack.py`; validated on ONE10449 run #3 and ONE10341 run #4 | ✅ 2026-11-26 (branch `feat/meta-ads-report-skill`) | Both reports produced from the pack; every gap the validation found fixed in code |
| **2** | **API code in the platform:** seed `MetaAdapter` gains ad-level insights with the retention fields (curve, 6 s, ThruPlay, quartiles), window breakdowns and ad set siblings, pinned to Graph v27 (seed default is still v21). social-wiring syncs **ad level daily** (today it syncs campaign level only), plus a KPI service mirroring `kpi_pack.py`. A `noctus.*` MCP tool exposes "property report data" to agents, so the skill calls the tool instead of the dev scripts (resolves the `NOC-REMEDIATE[promote-to-mcp-tool]` markers in `projects/meta-ads-snapshots/`) | ⏳ next | Skill v1 runs only on the tool; Fake + Real adapter + factory; tests; quota-aware (dev tier: 600 + 400 × active ads per hour) |
| **3** | **Campaigns UI redesign** in social-wiring: property-first navigation, KPI cards, retention curve, funnel, breakdowns, change timeline, recommendations; layout patterns from the imovelweb panel study | ⏳ after 2 | Owner signs off the mockup; every number on screen comes from the phase 2 service |

## Trigger conditions

| # | Trigger | Signal | Why |
|---|---|---|---|
| T1 | ✅ Phase 1 validated on 2 properties | two reports in `projects/meta-ads-snapshots/reports/` dated 2026-11-26 | method stable enough to code |
| T2 | Insights quota pressure | `x-fb-ads-insights-throttle` `acc_id_util_pct` > 50 or error 4/17/613 | apply for **standard/advanced access** (Full tier quota is 190000 + 400 × ads per hour) |
| T3 | CRM stage mapping confirmed | owner says which CRM stage is sent as `conversion_lead` | "qualified" becomes trustworthy; cost per qualified lead becomes a headline KPI |
| T4 | Owner wants push alerts | request | subscribe the `creative_fatigue` ad_account webhook |

## Decisions

- **API, not browser, and not Meta's hosted Ads MCP.** The hosted MCP (`mcp.facebook.com/ads`) is OAuth
  per user and suits ad-hoc agent queries. The in-app path is the System-User token the console already
  uses. The browser recipe stays as the UI-parity check.
- **Ad level is the unit.** Properties live in ad names, and ad sets are often shared pools.
- **No blended KPIs across objectives**, and **no cross-property placement rules** (see the 2026-11-26
  reports).
