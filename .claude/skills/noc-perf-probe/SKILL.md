---
name: noc-perf-probe
description: Use when the owner wants performance analyzed or an improvement evaluated - "analyze performance of X", "how fast is this app", "before/after performance", "is it faster now", "waterfall", "duplicate requests", "perf probe", "profile this page". Scoped browser-side capture of a product or third-party app, templated and stored, then report or compare.
version: 1.0.0
---

# noc-perf-probe - scoped client-side performance analysis

Tool `noctus.dev.perf_probe` (CLI `--perf-probe`). Server half = `latency_report` (skill `noc-fast-responses`). Depth: `KB § PATTERNS/common/performance-analysis.md`.

1. **Fix the scope**: a live product slug, or the external host. Pick a label (`<date>-<what>`).
2. **Capture** (Chrome, owner logged in, paced; never burst a third-party app): `snippet kind=clear`; per route ONE full load, wait for network idle, run `snippet kind=append`; >= 5 loads per route; `snippet kind=read` in slices (output cap ~1 KB), save to a file, clear.
3. **Ingest**: `ingest scope label capture=<file>` (ids templated, only the summary stored). Third-party scope: `store=` OUTSIDE the repo (`_private-studies/...`); delete the raw file.
4. **Evaluate an improvement**: baseline label -> change -> after label -> `compare scope before after` (noise floor 15% AND 30 ms).
   **Analyze/discover**: `report scope label` -> slowest pages/endpoints, duplicates, serial chains, edge vs app bound, oversized; for products also over-budget vs `latency-budgets.json`.
5. Report verdict + top findings; `inconclusive` means capture more loads, never ok.

Guardrails: paths and query keys only; no raw ids stored; no third-party data in git; read-only on the app (navigation only - no clicks that write).
