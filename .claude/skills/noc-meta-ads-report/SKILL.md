---
name: noc-meta-ads-report
description: Use when the owner wants a Meta Ads campaign, ad set or property analysed — triggers "analyse the ONExxxxx campaign", "how is ONExxxxx doing", "meta ads report", "campaign report", "weekly ads report", "relatório de campanha", "analisar campanha", "como está o anúncio do ONE…", "ad performance", "retention / hook rate of our ads", "compare this run with the last one". API-first (system-user token, no browser) → SQLite snapshot store → KPI pack (funnel, cost, video retention curve, breakdowns, change history) → run-over-run report with a scorecard of past recommendations.
version: 0.3.0
---

# noc-meta-ads-report — per-property Meta Ads report

One property (`ONExxxxx`) per run. Each run is an append-only "screenshot" in the SQLite store, so every
report compares itself with the previous one and grades the last report's recommendations.

**Read first:** `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/META-ADS-MANAGER-MAP.md` (hierarchy and
metric traps) and `kpis.md` in this folder (every formula). Code is in
`products/social-wiring/projects/meta-ads-snapshots/`. The live store is
`~/.noctusai/meta-ads/meta_ads.sqlite` (outside git).

## Workflow

0. **Resolve the scope.** The property code lives in the **ad name**, not the campaign name. A campaign
   or ad set can be a shared pool for several properties, so ad level is the unit. Account:
   `act_873947475957808` (One Consultoria) unless the owner names another. Find prior runs:
   `sqlite3 <db> "select run_id, fetched_at from extraction_run where scope_value='<CODE>'"`, and read
   the latest `reports/<CODE>-*.md` §7, which holds the recommendations you will grade.

1. **Pick the window.** The window is the period the owner cares about now: the current burst of
   delivery, or the day after the last run. Find it from the daily series if unsure. Never let a window
   span two different ad set configurations without saying so.

2. **Extract (API, read-only, about 2 min).**
   `python3 extract_api.py <CODE> ~/.noctusai/meta-ads/raw/meta_ads_<CODE>_<date>.json --env <primary>/.env --window-since <YYYY-MM-DD>`
   It must print `errors: []`. On throttling (code 4/17/613) it backs off and retries. Our app is on the
   development tier, so don't run several properties in parallel. Each `ads` count must match what Ads
   Manager shows. The extractor keeps exact `\bONE<digits>\b` matches only.

3. **Load (back up first).** `cp <db> <db>.bak-<date>`, then
   `python3 load_bundle.py <bundle> <db> --scope-value <CODE>`. The loader refuses bundles that contain
   errors. Never load a partial bundle.

4. **Compute.** `python3 kpi_pack.py <db> <CODE>` (the window defaults to the one stored in step 2). It
   outputs: lifetime by objective · per ad (Δ vs the previous run) · retention · daily series ·
   per-objective window funnel · window placement and age · activity since the last run · ad set
   configuration. **Every number in the report comes from this output.** If you need a number the pack
   doesn't produce, add it to `kpi_pack.py` (that is a refinement; log it in step 7) rather than
   improvising SQL.

5. **Diagnose.** Answer these questions in order. Each one maps to a pack table.
   1. What changed since the last run (activity, configuration)? Did anything reset learning?
   2. Per objective: spend → impressions → link clicks → leads. Which step leaks (CPM, link CTR,
      click → lead)?
   3. Retention: hook (1 s / 3 s), hold, and where the curve drops. Is the problem attention or the call
      to action?
   4. Who is the spend going to (placement, age × gender, window only)? Are there buckets with CPM 2× or
      more and 0 leads?
   5. Fatigue: frequency trend and CTR decay per ad (daily series).
   6. Grade every recommendation from the last report: done, partly done or not done, and what effect it
      had.
   7. **Pool:** is each ad set exclusive to the property or shared (the pack's `Pool` column)? If shared,
      ad set numbers belong to the pool, and the property's spend depends on winning the CBO auction.
   8. **"Qualified" leads** (`conversion_leads` result) are CRM events sent back to Meta. If they are ≥90%
      of form leads, the CRM is sending an early stage. Say so; don't call them qualified.
   Tie every claim to a number and state sample size. At n < ~5 leads, lead conclusions are hypotheses;
   retention and CTR conclusions rest on impressions and are firmer.

6. **Write** `reports/<CODE>-<YYYY-MM-DD>.md` with the template sections in order: 1 Summary
   (lifetime vs since last) · 2 Structure / what changed · 3 Timeline (BRT; say "operator" or "Meta", no
   personal names) · 4 Investment and outcomes per ad · 5 Video retention · 6 Audience and placement
   (window) · 7 Scorecard + recommendations + next report date · 8 Data caveats. Write it in English for
   the repo; the owner gets a short summary in chat. Lifetime rollups are always **per objective**.
   **Before saving, re-check every number in §1 and §7 against the pack output.** In run #3 a
   hand-computed CPL included another objective's lead and was off by R$ 28.

7. **Refine (every run).** Anything that surprised you (a missing field, a wrong default, a trap) goes
   into the code, `kpis.md`, the canon doc's §5, or this file's *Lessons*, in the same branch. A lesson
   that stays only in the chat is lost.

## Guardrails

- **Read-only.** GET requests only. Never change campaigns. Recommendations are for the owner to apply.
- **Token hygiene.** The token comes from `.env`. It is never printed, never written to the bundle (the
  extractor asserts this), and never put in a URL that gets logged.
- **Attribution.** If an ad set's attribution setting differs from the last run's, say so in §2 and
  compare on `value_7d_click`.
- **No blended CPL** across objectives (form leads vs profile visits vs clicks).
- **No cross-property rules.** Stories gave ONE10449 0 leads and ONE10341 94% of its leads. Judge every
  placement, age or creative rule per property, from that property's own data.
- **Personal data.** Lead contents (names, phones) never go in reports. Counts only.

## Lessons (append-only, newest last)

- 2026-10-06/14 (browser runs #1–2): property code is in the AD name · `actions:lead` can double-count ·
  rankings are `UNKNOWN` under ~500 impressions · daily rows skip zero-delivery days. See the canon doc §5–6.
- 2026-11-26 (run #3, first API run): the system-user token works (no browser) · `results` is absent for
  lead ads and the 2 s continuous field is omitted, so leads come from `lead_grouped` and 2 s views from
  the curve · v22 is silently served as v25, so pin v27 · `CONTAIN '10449'` can over-match, so filter with
  `\bONE<digits>\b` · lifetime breakdowns mislabel a recent window, so pull `--window-since` too · a
  traffic ad in the window inflated link CTR 6×, so the window funnel must be per objective.
- 2026-11-26 (ONE10341 run #4, validation): the procedure ran unchanged from extract to load, and the pack
  surfaced 4 more gaps, now fixed in code: a wrong column (`object_snapshot.level`), identical ad names
  across campaigns (labelled with campaign and id), CBO budgets live on the campaign, and ad set
  exclusivity (`adset.ads{name,effective_status}` → `Pool`) · `conversion_leads` = Meta's "Leads
  qualificados" (CRM events), now reported as qualified and cost per qualified, with a 96%-of-leads sanity
  check · a first run shows activity since the window.
