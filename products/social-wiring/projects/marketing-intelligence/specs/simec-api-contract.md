# SIMEC API — implemented contract (social-wiring backend, P1 slice S2)

Status: implemented on `feat/sw-simec-p1-backend` (2026-10-19). Build the FE SIMEC page (slice S3) against THIS file. Shapes below were extracted from the running endpoints (Fake source), not written from memory.

Code: `products/social-wiring/backend/app/modules/simec/` (router, service, sources, repository) · migration `284_simec.sql` · calculator `seed/lib/backend/noctusai_lib/domain/content_performance/` (pure; golden-tested against the SIMEC 1.0 workbooks).

## What this implements

- **Nothing hardcoded** (owner, 2026-10-19): windows + tolerances, indicators, panel lines, baseline look-back + minimum sample, alert thresholds (relative to the profile's own baseline), which metrics the source provides, review cadence and decision-validation period are all **config**. The seed ships defaults (`defaults/instagram.json`); an org layer and a per-profile layer override them. Every readout stores the resolved config, its version label and its sha256 fingerprint.
- **Instagram only.** TikTok is parked (owner, 2026-10-16). `platform` accepts only `"instagram"` today (anything else is a 422).
- **Pilot:** Mônica Tangerino's personal org (`indv_monica-tangerino`). No Instagram account is connected in any org yet, so the FE must handle the "no account" state first (see Empty states).

## Conventions

- Every route needs a session. No session returns a strict **401**. The org comes from the session (the selected org), never from a parameter.
- `{account_id}` is an `integration_accounts.id` with `provider="instagram"` in the session's org. Another org's account, a non-Instagram connection or a missing row returns **404**. A malformed `{account_id}` returns **400**.
- Config writes (`PUT`) require **owner/admin** in the selected org (trusted `noctus_users` row); anyone else gets **403**. Reads are open to every member of the org.
- Request bodies are **strict**: an unknown field is a **422**.
- Dates are `YYYY-MM-DD` (America/Sao_Paulo calendar). Timestamps are ISO-8601 UTC.
- **Rates are fractions** (`0.0868` = 8,68 %). Format as percent in the UI.
- **Counts can be floats** in readouts (`8504.0`); render as integers.
- Readouts are computed on demand (`POST`) and stored. A `GET` never recomputes.

### Cells: the three ways a number can be missing

Every metric, indicator and panel value is a **cell**, never a bare number:

```json
{ "value": 0.0868, "status": "ok" }                  // reading cell
{ "value": 0.0868, "n": 7, "status": "ok" }          // panel cell (n = sample size)
```

| `status` | Meaning | Render |
|---|---|---|
| `ok` | a real value (may be `0` — a proven zero) | the number |
| `ausente` | the platform CAN report this, but this post/day has no value (e.g. follows on a Reel, reach missing that day) | "—" |
| `sem_dados` | panel only: no valid reading in this window has the value | "—" + "sem dados" |
| `nao_disponivel` | the platform/source does NOT provide this metric at all (config `metrics.<key>.available=false`); never estimated | "não disponível" (with the metric's `note` from the config as tooltip) |

`value` is `null` for every status except `ok`. **Never coerce `null` to `0`.** Always show the panel's `n` next to a mean (the workbook rule: a mean is reported with its sample).

### Error envelope

Every error uses the product's envelope:

```json
{ "error": { "code": "UNAUTHORIZED", "message": "Token ausente" } }
{ "error": { "code": "NOT_FOUND", "message": "readout 0000… not found" } }
{ "error": { "code": "HTTP_ERROR", "message": "windows.7d: min_days 11 > max_days 10" } }
{ "error": { "code": "VALIDATION_ERROR", "message": "bogus: Campo não permitido",
             "details": { "errors": [{ "field": "bogus", "message": "Extra inputs are not permitted", "type": "extra_forbidden" }] } } }
```

| Status | `code` | Cause | User-facing message |
|---|---|---|---|
| 400 | `BAD_REQUEST` | malformed `account_id` | "Conta inválida." |
| 401 | `UNAUTHORIZED` | no/expired session | redirect to login |
| 403 | `FORBIDDEN` | config write by a non-admin | "A configuração do SIMEC é restrita a administradores." (use this copy; the backend message comes from the shared seed gate and reads "… restrito a administradores.") |
| 404 | `NOT_FOUND` | account/readout not in this org | "Conta não encontrada." / "Leitura não encontrada." |
| 422 | `HTTP_ERROR` | config overrides do not validate, or bad period/cadence | show `error.message` verbatim (it names the offending field) |
| 422 | `VALIDATION_ERROR` | body shape (unknown field, wrong type, unsupported `platform`) | show `error.message` |
| 503 | `INTERNAL_ERROR` | the server's metrics source is misconfigured | "SIMEC indisponível no momento." |

## Endpoints

### `GET /api/simec/accounts`

The org's Instagram connections (any status) and each one's latest readout.

```json
{
  "metrics_source": "instagram_snapshots",
  "accounts": [{
    "account_id": "uuid", "label": "monica", "username": "monicatangerino",
    "marca_id": "uuid|null", "status": "validated", "last_synced_at": "2026-10-19T08:30:00Z|null",
    "insights_scope_granted": true,
    "latest_readout": { "id": "uuid", "computed_at": "…Z", "period_start": "2026-09-20",
                        "period_end": "2026-10-19", "source": "instagram_snapshots" } | null
  }]
}
```

- `metrics_source`: `"instagram_snapshots"` (real data) or `"fake"` (demo data). **When it is `"fake"`, show a visible "Dados de demonstração" banner on every SIMEC screen.** A readout also carries its own `source`.
- `status != "validated"` or `insights_scope_granted: false` → show "Reconectar Instagram" (same CTA as the Instagram insights page).

### `GET /api/simec/config/defaults?platform=instagram`

The seed's recommended defaults, no org layer. Same shape as `GET /config` with `layers.org` and `layers.account` both `null`.

### `GET /api/simec/config?platform=instagram[&account_id=<uuid>]`

The **effective** config (defaults ⊕ org ⊕ profile when `account_id` is given) and each layer.

```json
{
  "platform": "instagram",
  "version": "instagram-defaults-1.0.0+org.v2+perfil.v1",
  "fingerprint": "64 hex chars",
  "config": { …full resolved config, see "Config shape"… },
  "layers": {
    "defaults": { "version": "instagram-defaults-1.0.0" },
    "org":     { "version": 2, "overrides": { "baseline": { "min_posts": 8 } },
                 "updated_at": "…", "updated_by": "uuid" } | null,
    "account": { "version": 1, "overrides": { … }, "updated_at": "…", "updated_by": "uuid" } | null
  }
}
```

### `PUT /api/simec/config/org` (owner/admin)

Body: `{ "platform": "instagram", "overrides": { …partial config… } }` (`platform` optional, default `"instagram"`).

- **Replaces** the org layer with `overrides` (it is not merged with the previous org layer; send the whole layer). `{}` resets the org layer to "no overrides".
- Validated against the layers below it **before** anything is written; invalid → 422, nothing stored.
- State after: the layer's `version` is +1, a history row is appended (`simec_config_historico`), and the response is the new effective config (same shape as `GET /config`, org view). Existing readouts are **not** recomputed; they keep the config they were computed with.

### `PUT /api/simec/accounts/{account_id}/config` (owner/admin)

Same body and semantics, for the profile layer (applied on top of the org layer). Response = effective config for that account.

### `POST /api/simec/accounts/{account_id}/readouts`

Computes and stores a readout now. Body (all optional; `{}` is valid):

```json
{ "period_start": "2026-09-01", "period_end": "2026-09-30", "cadence": "mensal" }
```

- `period_start`/`period_end` go together (both or neither). Omitted → the review period of `cadence` ending **today** (BRT): `semanal` = last 7 days, `mensal` = last 30 days (lengths come from config `cadence.reviews`). Unknown cadence, inverted period, only one bound, or a period longer than 366 days → 422.
- The **period selects content by publication date**. Baselines use the content published in the `baseline.lookback_days` BEFORE `period_start` (`history_start`), so new posts are compared with the profile's earlier posts, never with themselves.
- A post only has a reading for a window once a daily snapshot falls inside that window's tolerance (7d = days 7–10, 30d = days 30–35, 72h = days 3–4, `atual` = latest). Posts younger than a window simply have no reading in it; the panel's `n` shows this.
- Response **201** = the full readout (shape below). State after: the readout is the account's `latest_readout`.

### `GET /api/simec/accounts/{account_id}/readouts?limit=20`

`limit` 1–100. Newest first. Summaries only:

```json
{ "items": [{ "id": "uuid", "account_id": "uuid", "platform": "instagram", "source": "fake",
              "period_start": "2026-09-20", "period_end": "2026-10-19", "history_start": "2026-06-22",
              "config_version": "instagram-defaults-1.0.0", "config_fingerprint": "64 hex",
              "status_counts": { "ok": 25, "incompleto": 0, "data_invalida": 0, "fora_da_janela": 0,
                                 "duplicado": 0, "janela_desconhecida": 0 },
              "computed_by": "uuid|null", "computed_at": "…Z" }] }
```

### `GET /api/simec/accounts/{account_id}/readouts/latest`

`{ "readout": <full readout> }`, or **`{ "readout": null }` (200, not 404)** when none was computed yet.

### `GET /api/simec/readouts/{readout_id}`

The full readout. Another org's id → 404.

## Full readout shape

The summary fields above, plus:

```json
{
  "config": { …the resolved config used, see "Config shape"… },
  "panel": {
    "7d": {
      "conteudos_validos":           { "value": 7,      "n": 7, "status": "ok" },
      "visualizacoes_somadas":       { "value": 8504.0, "n": 7, "status": "ok" },
      "media_visualizacoes":         { "value": 1214.86,"n": 7, "status": "ok" },
      "media_alcance":               { "value": 868.14, "n": 7, "status": "ok" },
      "media_taxa_interacao":        { "value": 0.0868, "n": 7, "status": "ok" },
      "media_taxa_compartilhamento": { "value": 0.0106, "n": 7, "status": "ok" },
      "media_taxa_salvamento":       { "value": 0.0114, "n": 7, "status": "ok" },
      "media_taxa_seguidores":       { "value": 0.0014, "n": 5, "status": "ok" },
      "media_tempo_medio_duracao":   { "value": null,   "n": 0, "status": "nao_disponivel" },
      "media_taxa_pulo":             { "value": 0.395,  "n": 2, "status": "ok" },
      "media_views_3s":              { "value": null,   "n": 0, "status": "nao_disponivel" },
      "amostra_taxa_interacao":      { "value": 7,      "n": 7, "status": "ok" },
      "amostra_taxa_seguidores":     { "value": 5,      "n": 5, "status": "ok" }
    },
    "72h": { … }, "30d": { … }, "atual": { … }
  },
  "baselines": [{
    "window": "30d", "group": { "format": "Carrossel" }, "indicator": "reach",
    "n": 10, "mean": 1984.8, "median": 1970.0, "p25": 1748.0, "p75": 2192.0, "sufficient": true
  }],
  "alerts": {
    "fired": [{
      "rule": "alcance_fora_do_padrao", "indicator": "reach", "method": "outside_iqr", "threshold": 1.5,
      "content_id": "1789…", "window": "atual", "group": { "format": "Foto" },
      "value": 1000.0, "direction": "below", "deviation": -1.52,
      "baseline": { "n": 10, "median": 1970.0, "p25": 1785.0, "p75": 2303.0 }
    }],
    "not_evaluated": [{ "rule": "interacao_fora_do_padrao", "window": "7d", "group": { "format": "Foto" },
                        "reason": "baseline_insuficiente", "baseline_n": 2 }]
  },
  "readings": [{
    "content_id": "1789…", "window": "7d", "published_on": "2026-09-22", "collected_on": "2026-09-29",
    "format": "Carrossel", "topic": "first caption line (≤120 chars)", "status": "ok", "age_days": 7.0,
    "metrics":    { "views": { "value": 1215.0, "status": "ok" }, "follows": { "value": null, "status": "ausente" },
                    "duration_s": { "value": null, "status": "nao_disponivel" }, … },
    "indicators": { "taxa_interacao": { "value": 0.0841, "status": "ok" }, … },
    "source_ref": { "ig_media_id": "1789…", "snapshot_date": "2026-09-29", "snapshot_id": "uuid",
                    "permalink": "https://www.instagram.com/p/…", "unsupported_metrics": [] }
  }]
}
```

Notes for the UI:

- **Panel keys, labels and order come from the config**, not from the FE: iterate `config.panel` (object, in order; skip `enabled: false`), label = `config.panel[key].label`, look the cell up in `panel[window][key]`. Columns = `config.windows` in order (skip disabled). An org that adds an indicator gets a new row with no FE change.
- `readings` are the period's content × window rows (published in the period), sorted by `published_on`, `content_id`, `window`. Metric/indicator labels: `config.metrics[key].label` / `config.indicators[key].label`. Link a row to `source_ref.permalink`.
- Reading `status` (`ok` | `incompleto` | `data_invalida` | `fora_da_janela` | `duplicado` | `janela_desconhecida`): only `ok` rows feed the panel and alerts. With our own collection the non-`ok` states are rare (they exist for workbook parity and future manual imports); show them greyed with the status label.
- `baselines` are per window × format × indicator. `sufficient: false` means fewer than `config.baseline.min_posts` comparable posts: show the numbers but mark "amostra insuficiente".
- `alerts.fired`: `direction` `above`/`below`; `deviation` is relative to the median for `pct_from_median` (0.6 = 60 % above), or in IQR units beyond p25/p75 for `outside_iqr`. **An alert is a fact about the profile's own history, not a diagnosis** (SIMEC rule 3): word it as "acima/abaixo do padrão do perfil", never as a cause.
- `alerts.not_evaluated[].reason`: `baseline_insuficiente` | `sem_baseline` | `mediana_zero` | `iqr_zero`. Show these so the absence of an alert is never read as "everything is normal".
- `config_version` (e.g. `instagram-defaults-1.0.0+org.v2+perfil.v1`) and `source` should be visible on the readout (small print / info tooltip): every number names the config that produced it.

## Config shape (`config`, defaults and overrides)

Keyed collections are objects keyed by item key, so an override touches one item: `{ "windows": { "7d": { "max_days": 12 } } }`. A new key adds an item; `{ "enabled": false }` switches one off. Lists (`inputs`, `required_metrics`, `group_by`, `indicators` inside `baseline`, alert `windows`) are replaced whole. `platform` and `version` cannot be overridden.

```json
{
  "platform": "instagram", "version": "instagram-defaults-1.0.0", "description": "…",
  "required_metrics": ["views"],
  "metrics":    { "<key>": { "label": "Alcance", "unit": "count|seconds|fraction", "available": true, "note": "…|absent" } },
  "windows":    { "<key>": { "label": "7 dias", "min_days": 7, "max_days": 10, "enabled": true } },
  "indicators": { "<key>": { "label": "Interação / alcance", "op": "sum_all|ratio", "inputs": ["total_interacoes", "reach"], "unit": "ratio|count", "enabled": true } },
  "panel":      { "<key>": { "label": "Média de alcance", "aggregate": "count|sum|mean|sample", "source": "reach", "enabled": true } },
  "baseline":   { "lookback_days": 90, "min_posts": 5, "group_by": ["format"], "indicators": ["views", "reach", "taxa_interacao", …] },
  "alerts":     { "<key>": { "indicator": "taxa_interacao", "method": "pct_from_median|outside_iqr", "threshold": 0.5, "direction": "both|above|below", "windows": [], "enabled": true } },
  "cadence":    { "reviews": { "semanal": { "label": "Estratégia semanal", "every_days": 7 }, "mensal": { "label": "Revisão mensal", "every_days": 30 } },
                  "decision_validation_days": 28 }
}
```

Validation rules the server enforces (each → 422 with a message naming the field): unknown fields; `min_days > max_days`; an op/aggregate/method outside the lists above; a `ratio` without exactly 2 inputs; an input/source that is not a metric or an earlier enabled indicator; an alert whose indicator is not in `baseline.indicators`; `threshold <= 0`; `min_posts`/`lookback_days`/`every_days`/`decision_validation_days < 1`; a required metric marked unavailable; all windows disabled.

Instagram metric availability in the defaults: `duration_s` and `views_3s_rate` are `available: false` (the Graph API returns neither; `note` explains). Consequently `tempo_medio_duracao` and its panel line are always `nao_disponivel` until duration is sourced.

## Empty states (render each explicitly)

| Situation | Signal | UI |
|---|---|---|
| No Instagram connected in this org (today's reality) | `GET /accounts` → `accounts: []` | "Conecte o Instagram desta conta para usar o SIMEC" + link to the Instagram connection flow |
| Account connected but needs reconnect | `status != "validated"` or `insights_scope_granted: false` | "Reconectar Instagram" |
| No readout yet | `latest_readout: null` / `GET …/latest` → `{ "readout": null }` | "Nenhuma leitura ainda" + "Gerar leitura" button (POST) |
| Readout with no content in the period | every panel window `conteudos_validos.value == 0`, `readings: []` | "Nenhuma publicação no período" |
| Demo data | `metrics_source == "fake"` or readout `source == "fake"` | persistent "Dados de demonstração" banner |
| Metric the platform does not provide | cell `status: "nao_disponivel"` | "não disponível" + the metric's `note` |

## Not in this slice (named destinations)

- Scheduled weekly/monthly readouts + emailed reports → P2 S6; failure/incomplete-data alerts → P2 S7.
- Decision log / results control (`simec_decisoes`, `cadence.decision_validation_days` is already config) → later SIMEC slice.
- Unit check of `ig_reels_avg_watch_time` (ms) and `reels_skip_rate` (percent) against a real connected account → `NOC-REMEDIATE[simec-ig-units]` in `sources.py`.
- TikTok → parked (owner 2026-10-16); the seed already ships `defaults/tiktok.json` with views as the denominator.
