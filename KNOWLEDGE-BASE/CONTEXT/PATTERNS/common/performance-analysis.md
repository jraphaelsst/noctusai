# Performance analysis — the client view (`noctus.dev.perf_probe`) + the server view (`latency_report`)

Owner ask 2026-10-22: a scoped, repeatable way to analyze performance, to **evaluate** an improvement to an app and to **discover/analyze** new apps. Performance has two halves; neither alone is the truth.

## The two halves
| View | Tool | Sees | Blind to |
|---|---|---|---|
| Server | `noctus.dev.latency_report` (`--latency-report <slug>`) | p50/p95 per ROUTE TEMPLATE from `req_timing` log lines vs `deploy/fleet/latency-budgets.json` | network/edge time, waterfalls, duplicate calls, what the user waited for |
| Client | `noctus.dev.perf_probe` (`--perf-probe ACTION`) | what a browser lived through: page data-ready, serial chains, duplicates, edge-vs-app time, payload size | server internals; works on ANY app incl. third-party |

`Server-Timing: app;dur=` (seed `RequestTimingMiddleware`) joins them: per endpoint, `network = duration - app`. Edge-bound (network >> app) is fixed by fewer/shorter round trips; app-bound by the handlers rule (`request-path-latency.md`).

## SCOPE
The unit everywhere: a **product slug** in the live catalog (`active-scope.txt`/`build-scope.txt`) or an **external host** (`app.vendor.io`; must equal the capture's host). Optional `pages=[glob]` / `endpoints=[glob]` narrow report/compare further. Product scopes are also classified against the budgets (client view assumes GET: shell/read classes; verdict `ok | over_budget | inconclusive`, thin data is never ok).

## Capture procedure (paced)
1. Chrome, logged in as the owner (never type credentials). `perf_probe action=snippet kind=clear` once.
2. Per route: ONE full navigation (a full load resets the Resource Timing buffer), wait for network idle, run `snippet kind=append` (accumulates in `localStorage['__noc_perf']`). Repeat each route >= 5 times across loads (budget `min_samples`) for p95 to mean anything. Pace: never burst a third-party app.
3. Read it out with `snippet kind=read offset size` pages (browser JS output is capped ~1 KB; concatenate the `s` parts), save to a file, then `clear`.
4. `perf_probe action=ingest scope=<x> label=<yyyy-mm-dd-what> capture=<file>` — ids are templated (`{id}` for uuid/numeric/hex/opaque), ONLY the summary is stored; delete the raw file.

## Use A — EVALUATE an improvement
capture baseline label (`...-before`) -> make the change (+ deploy) -> capture the same routes (`...-after`) -> `compare scope before after`. Rows are `improved | regressed | unchanged | new | gone`; a change counts only if it exceeds BOTH 15% and 30 ms (noise floor; `min_pct`/`min_ms`). Pair with `latency_report` after deploy for the server half.

## Use B — DISCOVER / ANALYZE an app (ours or third-party)
capture -> `report scope label` -> findings drive the backlog: slowest pages (data-ready), slowest endpoints (p95), duplicate calls (same template >1 per load), deep serial chains (waterfall: depth >= 3), edge-bound vs app-bound, oversized payloads (>= 100 KB p50), non-2xx. For reverse-engineering (S1) it also yields the app's real endpoint inventory and how chatty it is.

## Privacy rules
- Capture records **paths + query KEYS + timings only** — never query values, bodies, headers, cookies.
- Ids are templated before anything is stored; the raw capture is not kept.
- Store: `<repo>/.noc-perf/<scope>/<label>.json`, **gitignored**. Third-party data never enters git: pass `store=<dir outside the repo>` (vendor studies live in `_private-studies/`, also gitignored). Overwriting a label refuses unless `overwrite=true`.

## Invocations
```
venv/bin/python mcp/noctusai/cli.py --perf-probe snippet --pp-kind append|read|clear [--pp-offset N --pp-size N]
... --perf-probe ingest  --pp-scope orbity --pp-label 2026-10-22-before --pp-capture cap.json [--pp-store DIR] [--pp-overwrite]
... --perf-probe report  --pp-scope orbity --pp-label 2026-10-22-before [--pp-pages '/clientes*'] [--pp-endpoints '/api/x*']
... --perf-probe compare --pp-scope orbity --pp-before L1 --pp-after L2
... --perf-probe list    [--pp-scope S]
```
Exit code 0 only for `ok` / `improved` / `unchanged`.

Cross-links: skill `noc-perf-probe` · skill `noc-fast-responses` · `KB § PATTERNS/backend/request-path-latency.md` · `KB § PATTERNS/common/app-reverse-engineering.md`.
