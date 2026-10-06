# Meta Ads Manager — interface, data-wiring & extraction map (browser-agent canon)

> **Read this BEFORE driving Ads Manager with a browser agent.** Everything here was learned the hard
> way on 2026-10-06 (account *One Consultoria Imobiliaria*, `act_873947475957808`, BM *Gilson Tangerino*
> `business_id=1083337316428366`). It exists so no agent has to re-discover it.
>
> Code + recipe: `products/social-wiring/projects/meta-ads-snapshots/` (`extract_bundle.js`,
> `load_bundle.py`, `schema.sql`, `ui_columns.sql`, `screens/`, `reports/`).
> First canonical report: `reports/ONE10449-2026-10-06.md`.
> Live SQLite (dev/learning phase, NOT in git): `~/.noctusai/meta-ads/meta_ads.sqlite`, raw bundles in `~/.noctusai/meta-ads/raw/`.
>
> **Sibling, already in prod:** the social-wiring *Meta Ads console* (`backend/app/modules/meta_ads/`,
> migration `030_meta_ads.sql`, roadmap `project-history/roadmaps/meta-ads-console-2026-07.md`) syncs the
> same account server-side with a **system-user token**. The browser path documented here is the
> UI-parity / discovery path; §8 maps every SQLite table onto the console's Postgres tables so the
> SQLite phase promotes instead of forking.

---

## 1. Object hierarchy (and the three naming systems)

| UI (pt-BR) | Graph API | Ads Manager internal (URLs, activity log `object_type`) | Owns |
|---|---|---|---|
| Conta de anúncios | `act_<id>` | account | currency, timezone |
| **Campanha** | campaign | **`CAMPAIGN_GROUP`** | objective (`OUTCOME_LEADS`, `LINK_CLICKS`…), buying type, CBO budget |
| **Conjunto de anúncios** | adset | **`CAMPAIGN`** | budget (ABO), schedule, optimization goal, targeting, placements, destination, attribution window |
| **Anúncio** | ad | **`ADGROUP`** | links ONE creative into ONE ad set; delivery status |
| **Criativo** | adcreative | — | media + copy + CTA; backs an FB post (`effective_object_story_id`) and/or IG media (`effective_instagram_media_id`) |

> 🔴 The internal names are shifted by one level. `SEARCH_BY_ADGROUP_NAME` filters **ads**;
> `object_type=CAMPAIGN` in the activity log is an **ad set**. Mis-reading this mis-attributes every event.

**Property ↔ Meta mapping (One's convention):** a property (`ONExxxxx`) is NOT a Meta object. It appears in:
- the **ad name** — always (`ONE10449`, `ONE10449 Tour`, `ONE10449 Larissa`…; suffix = creative variant);
- the **ad set name** — only when the property has a **dedicated** lead ad set (`ONE10449`).
- **never** the campaign name. Campaigns are strategy buckets (`[Senseys] [Campanha de Tráfego] [Perfil Instagram]`, `[SENSEYS] [ISOLADOS] [Formulário Instantâneo]`).

Two legs per property are typical:
- **Traffic leg** — one ad inside a **shared-pool** ad set that hosts one ad per property (R$ 20/day for all). Metrics of the ad set are NOT the property's; Meta reallocates budget between properties (ONE10449 got ~R$ 0 after 2026-09-25).
- **Lead leg** — a **dedicated** ad set per property in the instant-form campaign, several creative variants.

---

## 2. UI map (screens in `projects/meta-ads-snapshots/screens/`)

- **Top bar:** account selector (searchable; lists BMs → accounts), *Pontuação de oportunidade*, refresh, *Conferir e publicar* (⚠ write action — never click).
- **Saved views row:** *Todos os anúncios*, *Ações*, *Anúncios ativos*, *Tiveram veiculação*, *+ Ver mais*.
- **Filter box:** free text → suggestions *Nome da campanha / Nome do conjunto de anúncios / Nome do anúncio contém tudo de X*. Becomes a chip; persisted in URL `filter_set`.
- **Level tabs:** *Campanhas* / *Conjuntos de anúncios* / *Anúncios* (shortcut ⌥+1/2/3). The filter chip persists across tabs.
- **Toolbar:** *Criar*, *Duplicar*, *Editar*, *Teste A/B*, *Mais* (all write — avoid) · **Colunas: <preset>** · **Detalhamento** (breakdowns: Dia, Idade, Posicionamento, País, …) · reports/export · chart toggle.
- **Date picker:** presets (Hoje … *Máximo*) + custom + *Comparar*. Timezone shown: "Horário de São Paulo".
- **Row hover** (ad level): *Gráficos* · *Editar* · *Duplicar* · preview. *Gráficos* opens `/manage/ads/insights?selected_ad_ids=<id>` with a left tree of the hierarchy and a daily chart + *Histórico de atividade*.
- **Grid:** virtualized both axes (off-screen rows/columns are NOT in the DOM); numbers are locale-formatted (`R$ 1.586,23`, `53.033`); two-line cells (value + subtitle, e.g. "Leads (formulário)", "Diário").

Column presets observed: **Desempenho** (default), **Engajamento**, **Veiculação**, *Desempenho e cliques*, *Configuração*. Full column → API dictionary: `ui_columns.sql` (loaded into table `ui_column`).

---

## 3. URL grammar (deep-link instead of clicking)

```
https://adsmanager.facebook.com/adsmanager/manage/{campaigns|adsets|ads}
  ?act=873947475957808&business_id=1083337316428366
  &date=2023-09-06_2026-10-07%2Cmaximum            # <from>_<to>,<preset>   (default = last_30d!)
  &filter_set=SEARCH_BY_ADGROUP_NAME-STRING_SET%1ECONTAINS_ALL%1E[%2210449%22]
  &column_preset=ENGAGEMENT                         # confirmed: ENGAGEMENT, DELIVERY
  &columns=name%2Cdelivery%2Cresults%2C...          # explicit column list (most reliable)
  &attribution_windows=default
  &selected_ad_ids=<id>                             # with /manage/ads/insights → Gráficos panel
```

Filter fields: `SEARCH_BY_CAMPAIGN_GROUP_NAME` (campaign) · `SEARCH_BY_CAMPAIGN_NAME` (ad set — inferred from the naming shift, not yet observed) · `SEARCH_BY_ADGROUP_NAME` (ad). Separator `%1E`.

---

## 4. Data wiring (what feeds the UI)

| Purpose | Endpoint |
|---|---|
| Grid metrics | `adsmanager-graph.facebook.com/v22.0/act_<id>/am_tabular` (internal tabular insights; `column_fields`, `filtering`, `date_preset`, `level`) |
| Objects | standard Graph v22: `act_<id>`, `/<campaign|adset|ad|creative id>`, `act_<id>/adlabels`, `…/ad_custom_derived_metrics` |
| Batches | `adsmanager-graph.facebook.com/?_reqName=batchedCall` |
| UI chrome | `adsmanager.facebook.com/api/graphql/` (recommendations, tips, publish-challenge) |

The page holds a session token in **`window.__accessToken`**, so the documented public endpoints
(`act_<id>/ads`, `act_<id>/insights`, `act_<id>/activities`, `<post>`/`<ig_media>`) are callable from
inside the tab, **read-only**, returning exactly what the UI shows. That is the extraction method
(`extract_bundle.js`). Rules: never print/return the token; strip `paging` (its URLs embed it); GET only.

---

## 5. Metric semantics (the traps)

- **Resultados** = the objective's result, with a per-row indicator: `actions:leadgen.other` (Leads (formulário)), `profile_visit_view` (Visitas ao perfil do Instagram), `post_engagement`… Never sum across objectives.
- **Leads:** `actions:lead` can be **2×** the form count (form + pixel). Canonical = `results` / `onsite_conversion.lead_grouped`.
- **Attribution differs per ad set** (traffic: 1-day click; leads: 7d click / 1d view). Requesting `action_attribution_windows=['7d_click','1d_view']` returns per-window keys; the plain `value` (= the object's own setting = UI) **may be absent** (e.g. a view-only conversion under a click-only setting). Store all three.
- **Campaign-level rows are whole-campaign** even when the filter is by ad name. Property numbers live at ad level (or a dedicated ad set).
- **Reach** is not additive (days, ads). **Frequency** = impressions/reach — recompute, never average.
- **Budget** in Graph is minor units (`10000` = R$ 100,00). At ad level the UI shows the parent ad set's budget.
- **Daily insights omit zero-delivery days** (no row ≠ missing data). Daily sums reconcile exactly to lifetime.
- **Engagement has two sources that legitimately disagree:** ad-attributed `actions` (`post_reaction`, `comment`, `onsite_conversion.post_save`, `post` = shares) vs the organic post counters (IG `like_count`/`comments_count`, FB `reactions/comments/shares`).
- **`page_engagement` / `post_engagement`** are dominated by 3-s `video_view` — reach signal, not interest.
- **`video_play_actions`** counts autoplay starts; use p25 as "real views". ThruPlay can exceed p25 on long videos.
- **Quality / engagement / conversion rankings** = `UNKNOWN` under ~500 impressions.
- **Meta changed result measurement on 2026-03-17** (Ads Manager banner) — don't compare across it.

---

## 6. Browser-agent lessons (process)

1. Opening Ads Manager without `act=` lands on the **last-used account** (an empty `1754612478821496` here). Always deep-link with `act=`.
2. The filter box sometimes ignores coordinate clicks → `find` the combobox, click by ref, then type.
3. The *Colunas* menu **reorders itself** (recently-used first) → never click presets by coordinates; use `column_preset=`/`columns=` in the URL. Unknown preset enums **silently fall back** to Desempenho.
4. A navigation shows a *Carregando…* modal for 10–20 s; the screenshot tool may time out mid-load ("Script injection timed out") — wait and retry.
5. Resizing the window to 2560×1300 shows ~16 columns at once (best for screenshots); navigation can reset the size.
6. `javascript_tool` returns ~1 KB per call and **aborts evaluations at 45 s** → build data in `window.*`, run long jobs as a background promise and poll, export bulk data as a **file download (ask the user first)**.
7. The browser MCP blocks output containing query strings/cookies — Graph `paging.next` URLs trip it. Strip `paging`.
8. The *Gráficos* panel resets to *Últimos 30 dias* even when the grid is on *Máximo*.
9. Read-only discipline: never click *Conferir e publicar*, toggles, *Editar*, *Duplicar*, *Criar*. Switching column presets is safe (it only changes the user's view preference — restore *Desempenho* after).

---

## 7. Snapshot store (SQLite, dev phase)

`schema.sql` — append-only facts keyed by `extraction_run.run_id` (each weekly run = one "screenshot"):
`extraction_run` · dims `account / campaign / adset (is_shared_pool) / ad (property_code, variant) / creative` · `object_snapshot` (raw JSON per run → budget/status history) · facts `insight` (lifetime|day) · `insight_action` (every action_type × family × window) · `insight_breakdown` · `post_engagement` · `activity` (dedup across runs) · `ui_column` · views `v_ad_lifetime`, `v_action_pivot`, `v_latest_run`.

Weekly loop: `extract_bundle.js` (CODE=…) → download (ask) → `python load_bundle.py <bundle> ~/.noctusai/meta-ads/meta_ads.sqlite --scope-value <CODE>` → report vs previous run (template: report §9).

---

## 8. Promotion map → social-wiring Postgres (`030_meta_ads.sql`)

| SQLite | social-wiring | Notes |
|---|---|---|
| `account` | `ads_accounts` | `act_id`; money already `_cents` there |
| `campaign` / `adset` / `ad` | `ads_objects` (`level`, `parent_id`) | `property_code`, `variant`, `is_shared_pool` have no home yet → add columns or derive in a view |
| `creative` | `ads_objects.creative_id`, `creative_thumbnail_url` | copy/CTA/story ids only in `raw` |
| `insight` (granularity=day) | `ads_insight_snapshots` (`date`, `breakdown_key` NULL) | money → cents; lifetime rows have no equivalent (recompute) |
| `insight_action` | `ads_insight_snapshots.actions` jsonb | per-window values need a jsonb shape decision |
| `insight_breakdown` | `ads_insight_snapshots` with `breakdown_key` | |
| `activity` | `ads_activity_events` (`event_key`) | |
| `object_snapshot` | `ads_objects.raw` (latest only) | history is SQLite-only today |
| `post_engagement`, `ui_column`, `extraction_run` | — | net-new |
