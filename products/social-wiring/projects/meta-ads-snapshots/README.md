# meta-ads-snapshots: Meta Ads browser-agent data capture (dev phase, SQLite)

The browser-driven path for capturing Meta Ads Manager data per property (`ONExxxxx`), so a weekly
report agent can work quickly and precisely.

**Procedure:** skill `noc-meta-ads-report` (`.claude/skills/noc-meta-ads-report/`, with the KPI catalogue in `kpis.md`).
**Read first:** `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/META-ADS-MANAGER-MAP.md`. It covers the
hierarchy, UI, URL grammar, data wiring, metric traps, browser lessons and the promotion map to `030_meta_ads.sql`.

| File | Role |
|---|---|
| `extract_api.py` | **Default (2026-11-26).** Same bundle via the Graph API (v27) and the system-user token from `.env`; adds the retention curve, 6-second views, window breakdowns (`--window-since`) and ad set siblings (shared-pool check). No browser. |
| `kpi_pack.py` | Every KPI a report needs, as markdown tables: per objective, per ad, retention, daily, window funnel, breakdowns, activity, ad set configuration and pool. |
| `extract_bundle.js` | In-page, read-only Graph v22 pull for one property. Starts a background job; poll `window.__jobStatus`, then download the bundle (ask the user first). |
| `load_bundle.py` | Loads a bundle into SQLite as one `extraction_run`. Append-only facts; refuses partial bundles. |
| `schema.sql` / `ui_columns.sql` | Snapshot schema, plus the UI-column ↔ API-field dictionary. |
| `screens/` | Reference screenshots of every level, preset and panel (2026-10-06). |
| `reports/` | Property reports. `ONE10449-2026-10-06.md` is the **canonical template**; `ONE10449-2026-10-14.md` is the first **weekly run-over-run** update (run #2 vs #1). |

Data lives **outside git**, in `~/.noctusai/meta-ads/meta_ads.sqlite` and `raw/`.

```bash
python3 load_bundle.py ~/Downloads/meta_ads_ONE10449_<date>.json ~/.noctusai/meta-ads/meta_ads.sqlite --scope-value ONE10449
```

Next step (deferred): promote to the social-wiring Postgres model, or run the same pull server-side
through the existing system-user-token sync (`backend/app/modules/meta_ads/`). The browser is the
discovery / UI-parity path, not necessarily the production one.
