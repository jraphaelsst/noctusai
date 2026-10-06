# meta-ads-snapshots: Meta Ads browser-agent data capture (dev phase, SQLite)

The browser-driven path for capturing Meta Ads Manager data per property (`ONExxxxx`), so a weekly
report agent can work quickly and precisely.

**Read first:** `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/META-ADS-MANAGER-MAP.md`. It covers the
hierarchy, UI, URL grammar, data wiring, metric traps, browser lessons and the promotion map to `030_meta_ads.sql`.

| File | Role |
|---|---|
| `extract_bundle.js` | In-page, read-only Graph v22 pull for one property. Starts a background job; poll `window.__jobStatus`, then download the bundle (ask the user first). |
| `load_bundle.py` | Loads a bundle into SQLite as one `extraction_run`. Append-only facts; refuses partial bundles. |
| `schema.sql` / `ui_columns.sql` | Snapshot schema, plus the UI-column ↔ API-field dictionary. |
| `screens/` | Reference screenshots of every level, preset and panel (2026-10-06). |
| `reports/` | Property reports. `ONE10449-2026-10-06.md` is the **canonical template**. |

Data lives **outside git**, in `~/.noctusai/meta-ads/meta_ads.sqlite` and `raw/`.

```bash
python3 load_bundle.py ~/Downloads/meta_ads_ONE10449_<date>.json ~/.noctusai/meta-ads/meta_ads.sqlite --scope-value ONE10449
```

Next step (deferred): promote to the social-wiring Postgres model, or run the same pull server-side
through the existing system-user-token sync (`backend/app/modules/meta_ads/`). The browser is the
discovery / UI-parity path, not necessarily the production one.
