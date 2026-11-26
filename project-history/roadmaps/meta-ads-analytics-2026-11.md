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
| **2** | **API code in the platform:** seed `MetaAdapter` gains ad-level insights with the retention fields (curve, 6 s, ThruPlay, quartiles), window breakdowns and ad set siblings, pinned to Graph v27 (seed default is still v21). social-wiring syncs **ad level daily** (today it syncs campaign level only), plus a KPI service mirroring `kpi_pack.py`. A `noctus.*` MCP tool exposes "property report data" to agents, so the skill calls the tool instead of the dev scripts (resolves the `NOC-REMEDIATE[promote-to-mcp-tool]` markers in `projects/meta-ads-snapshots/`) | 🔨 in progress (2026-11-26, slices below) | Skill v1 runs only on the tool; Fake + Real adapter + factory; tests; quota-aware (dev tier: 600 + 400 × active ads per hour) |
| **3** | **Campaigns UI redesign** in social-wiring: property-first navigation, KPI cards, retention curve, funnel, breakdowns, change timeline, recommendations; layout patterns from the imovelweb panel study | ⏳ after 2 | Owner signs off the mockup; every number on screen comes from the phase 2 service |

## Phase 2 — contract and slices (opened 2026-11-26)

**One engine, two consumers.** The seed owns fetch and KPI computation. The app and the MCP tool are
thin consumers, so the numbers are identical by construction.

| Slice | Owner | Content | Wave |
|---|---|---|---|
| S1 | integrations-engineer | `MetaAdapter.ad_insights` (ad, ad set or campaign level, retention fields, breakdowns, time range or preset, attribution windows) + pure `ads_kpis.py` (port of `kpi_pack.py`). Its `to_dict()` JSON shape **is the contract** for S2b and S3. Graph default set to v25 (behaviour-preserving: v21 is already served as v25) | 1 |
| S2a | backend-engineer | Hierarchy sync is stale: ad sets and ads were synced once on 2026-07-23 (270 of 646 ads). Fix the root cause so it refreshes daily, rate-limit-safe | 1 |
| S4 | tech-lead | Julia's qualified event renamed `JuliaQualifiedLead` (disjoint from the agency's `CRMLead`/`QualifiedLead`/`Lead`, enforced by a test) | 1 |
| S2b | backend-engineer | Daily ad-level insights for ads with recent delivery (re-pull the last 3 days while attribution windows settle) + retention storage + `GET /api/meta/ads/properties` and `/properties/{code}/report?since=&until=` built on `ads_kpis` | 2 |
| S3 | tooling-engineer | `noctus.sw.meta_ads_report(code, since, until, source='live'|'app')`: `live` = seed adapter now, `app` = the S2b endpoint. Same `ads_kpis` either way. The skill then calls the tool instead of the dev scripts | 2 |
| — | — | Future seed (owner, 2026-11-26): **retention × transcript.** Align each creative's curve and its hook/hold rates with its transcript blocks (timestamped words), so a drop at second N maps to what was said or shown at N. Not enough material yet; keep the curve per creative per day so the data exists when it's built | later |

## Findings 2026-11-26 (research, T1 where marked; details in the session reports)

- **Placements (T1, Meta Help Center):** adding placements does not raise cost. The budget is fixed and the
  auction picks the cheapest opportunities, minimising the average cost per result. Meta is gradually
  making **Advantage+ placements the default for the Leads objective, with manual selection removed**.
  Exclusions move to account-level controls. Judge placements by **CPL (qualified) per placement**,
  never by CPM alone (ONE10449: Stories 0 leads; ONE10341: Stories 94% of leads).
- **Learning (T1):** significant edits include targeting, creative, optimisation event, **adding a new
  ad**, **pausing 7+ days**, bid strategy and large budget changes. Learning ends at about 50 results in
  7 days. Duplicates are new objects (inferred: no T1 says they inherit learning). Engagement can carry
  over with "use existing post" or the duplicate-with-engagement checkbox.
- **Conversion leads (T1, Meta dev docs):** one CRM sends every stage (the raw lead included, ≥2–3
  stages) with `lead_event_source` and `event_source=crm`; ≥200 leads a month; daily upload; the
  optimised stage happens within 28 days and converts **1–40%**. Changing the pixel restarts training.
- **Our dataset today:** "Pixel - One Consultoria" (1672630926800214) is **owned by Senseys' business**,
  `is_crm=true`. In the last 30 days, its server events were `CRMLead` 475, `QualifiedLead` 255 and `Lead`
  80, all from one `lead_event_source`. One *Público One* ad set optimises on **`CRMLead`** (every lead), so
  there is no quality signal there. Julia's CAPI sender (wave 13) is built and correct but was **never
  activated**: no config row, 0 events, and **0 Julia contacts in prod** (490 Meta leads in the last 30 days).

### Julia → Meta activation plan (needs owner + Senseys; code side ready after S4)

1. **Julia go-live on Meta leads** (open owner items from 2026-11-13). Without contacts there are no
   signals.
2. **Decide who is "the CRM" for the dataset.** Meta expects one funnel. Either (a) Julia's stages go
   into the same dataset as a separate source (`lead_event_source=Julia`) and ad sets switch their
   optimisation event to `JuliaQualifiedLead`, or (b) Senseys' CRM forwards Julia's verdict as its
   `QualifiedLead` stage. Agree it with Senseys; they own the dataset.
3. **Permissions:** the system-user token must be allowed to send events to the Senseys-owned dataset
   (dataset shared to BM Gilson Tangerino with the right role). Verify with a `test_event_code` send,
   which needs owner approval.
4. **Config:** `julia_avaliacao_config.capi_ativo=true`, `capi_pixel_id=1672630926800214` (prod write,
   owner approval).
5. **Optimisation switch:** after about 7 days of Julia events, and at a qualified rate in the 1–40% band,
   switch ad sets to optimise on `JuliaQualifiedLead`. Expect 2–4 weeks of re-training.

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
