# deploy-config-pilot-consume — Project Document

> Follow-up wave split out of `seed-deploy-config-contract` at its close (2026-05-23).
> The contract (primitive + boot guard + keeper + pre-deploy gate + doc) **shipped**;
> this is the **pilot adoption** wave. Symbol-first per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-23
- **Status:** ⏳ **OPEN — blocked on a user decision** (which keys are prod-required per pilot).
- **Owner:** joaoraphaelsst@gmail.com · architect
- **Parent (shipped):** `seed-deploy-config-contract` (ledger slug; primitive `noctusai_lib.config.deploy_config`, guard in `create_product_app`, keeper `check_derives_from_dev_only_artifact`, pre-deploy `prod_config_parity`).

## 1 · Goal

Have the **pilot products opt into** the deploy-config contract by passing
`required_prod_config=[...]` (their actual prod-required keys) to
`create_product_app`, so a missing prod value **fails the boot loudly** instead
of silently serving a dev default. The seam is back-compat (default `None` =
no-op), so this is pure adoption — no seed change.

## 3a · Seed-first analysis

Already seed-first: the primitive + guard live in `noctusai_lib` / the factory.
This wave is per-pilot **wiring** (the one legitimate per-product step — passing
each product's own required-key list), not per-product logic. Per-pilot code = the
key list only.

## 6 · Phases

- **P1 ⏳ (blocked on decision)** — pilots **erp · therapy · social-wiring** (pilot-products-first): for each, enumerate the env keys that MUST be set in prod (e.g. `PRODUCT_URL_<SLUG>`, provider API keys, `APP_BASE_URL`) and pass them as `required_prod_config=[...]`. Verify dev stays a no-op (`is_deploy_context()` False locally) + the boot fails loudly when a key is unset in a prod-shaped env.
- **P2 ⏳** — non-pilots extend in a later gated wave (pilot-products-first cadence).

## 7 · Open question (the decision blocking P1)

**Which keys are prod-required per pilot?** This is a per-product judgment (what
must NEVER fall to a dev default in prod). Recommendation: start minimal —
`PRODUCT_URL_<SLUG>` for every product + each product's outbound-integration keys
that have no safe canonical default (the ones whose absence is a silent misroute,
not a graceful degrade). Architect to propose a per-pilot list → user confirms →
adopt. Do NOT guess the lists; a wrong `required_prod_config` either blocks a
legitimate boot or misses a real gap.

## 11 · Change log

- 2026-05-23 — filed as the pilot-adoption follow-up at `seed-deploy-config-contract` close. Contract shipped + green; adoption blocked on the per-pilot key decision (§7).
