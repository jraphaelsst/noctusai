# nosnolimiar-rename-2026-11 — rename the live product `monica` to `nosnolimiar` ("Nós no Limiar") and consolidate its org

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: owner decision 2026-11-02 — the clinic CRM/ERP is the product of the company Nós no Limiar, not of Mônica the person.
> Decision: **rename the slug, schema, host, container, image and WAHA instance in one coordinated cutover; move the app and its data to the existing org "Nós no Limiar" and delete the personal org "Mônica Tangerino".**
> The `consent_ref` of `deploy/consent/nosnolimiar.prod.yml` points at milestone **M0** below.

## Origin

`monica` went live 2026-10-27 (`project-history/roadmaps/monica-v1-2026-10.md`). The product is the clinic's CRM/ERP; the company is Nós no Limiar and Mônica is its founder. The slug, host, schema and org all named the person. Recon (2026-11-02, prod read-only) found: both orgs already hold an active `monica` license; almost no app data exists (30 `fin_categories` rows, all in the personal org); deleting the personal org would cascade-delete Mônica's own user profile unless her home org is re-pointed first; `public.audit_logs` (5 rows) blocks the org delete unless purged under the sanctioned GUC carve-out; and a schema rename silently breaks RLS (`current_org_id_for('monica')` literal), the acting-audit triggers (TG_ARGV schema arg) and the SECURITY DEFINER functions. This is the first live slug + schema rename; the precedent roadmap `product-slug-rename-2026-08.md` never started.

## Milestones

- **M0: owner consent to publish nosnolimiar** — owner, 2026-11-02 ✅ 2026-11-02
- **M1: repo rename merged to dev** — directory, code, compose/ingress/CI wiring, generated artifacts, core 120, product 022, cutover scripts. Blocked on M0 for the wiring commit (`check_prod_exposure_consent`).
- **M2: image built and promoted** — GHCR `noctus-nosnolimiar` built and pullable; `release` bless + promote; `deploy_pull`.
- **M3: cutover window done** — `RUNBOOK.md` phases B and C (core 120, 022, `cutover.sql`, deploy, tunnel).
- **M4: verified live** — `deploy_verify`, `spa_smoke`, `sso_cors_smoke`, `sso_smoke`, manual login lands in Nós no Limiar with 30 categories.
- **M5: cleanup** — old container/image/WAHA volume, stale `.env`/`.env.fleet` keys, roadmap archived.

## Trigger conditions

All phases are sequential on the owner's go; no deferred triggers. Phase C is run only with the owner present (every prod step is confirm-gated).

## Phase 1 — repo rename (this branch; re-cut 2026-11-11 as `feat/nosnolimiar-rename-v3` on dev `b5b08c50f` — v2 was 703 commits behind)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | `git mv products/monica products/nosnolimiar`; app identifiers, env names (`NOSNOLIMIAR_*`), agent key `nosnolimiar-leads`, UI branding "Nós no Limiar" | `products/nosnolimiar/**` | shipped (branch) | backend pytest 100, vitest, vite build |
| P1.2 | Platform wiring: `start.sh`, root compose, prod compose service/image/container, ingress (new host + `retired: monica.noctusai.com`), tunnel template, WAHA instance `waha-nosnolimiar` (+ rendered compose, `env.fleet.keys`), scope files, CI matrix, dependabot | `deploy/**`, `.github/**` | shipped except consent-gated surfaces | `tunnel_config check`, `waha_instance render`, keepers |
| P1.3 | Core 120 (catalog row renamed in place) and product 022 (schema rename + RLS/trigger/function/exposure re-pointing, catalog-derived, convergence guard) | `products/core/backend/migrations/120_*.sql`, `products/nosnolimiar/backend/migrations/022_*.sql` | shipped (branch) | `migration_replay`; prod dry-run |
| P1.4 | `verify_db_guards` probe + `compliance.py` path | `mcp/noctusai/tools/noctus/dev/` | shipped | `verify_db_guards` after 022 |
| P1.5 | Data move + org delete + rollback scripts + runbook | `products/nosnolimiar/projects/rename-2026-11/` | shipped | `cutover-dry-run.sql` on prod (ROLLBACK) |
| P1.6 | KB landscape/INDEX/integrations, LGPD entry, seed docstrings/fixtures | `KNOWLEDGE-BASE/**`, `seed/**` | shipped | `kb_sync verify` |

## Phase 2 — cutover (DEFERRED — owner present, M2 done)

See `products/nosnolimiar/projects/rename-2026-11/RUNBOOK.md` (ordered, with rollback per step).

## Anti-goals

- ❌ No redirect from `monica.noctusai.com` (owner: retired outright).
- ❌ No edits to applied migrations 001–021, `migrations-applied.json` hashes, `deploy/consent/monica.prod.yml`, `monica-v1-2026-10.md` (history).
- ❌ No rename of references to Mônica the person (agent packages, brand kits, handles).
- ❌ No authoring of `deploy/consent/nosnolimiar.prod.yml` by an agent.

## Open questions

- **Q1**: Cloudflare DNS CNAME `nosnolimiar` — exists? (check in B5).
- **Q2**: Does the VPS pull the new private GHCR package without extra auth? (B1).
- **Q3**: The patient area ("Entre sessões" app) is PAUSED 2026-11-02; its name is to be defined (spec docs updated).

## Decision log

- 2026-11-11: owner dropped the "Julia prod-verified" hold ("drop the julia hold"). The C4 option-B confirmation at the GO still stands.

- 2026-11-11: v2 retired, rename re-applied on current dev (v3). Renumbered: core 098 -> **120**, product 020 -> **022** (monica 020 `finance_rev2` / 021 `finance_service_only` landed on dev since v2 and are applied in prod under the old schema name, so they stay frozen and run BEFORE the rename). Owner 2026-11-08: finish the rename before any absorption (therapy-platform, community) into the product.
- 2026-11-05: C4 re-cut to option B (one branding per org): MT's marca + Studio chat are deleted, never moved to NnL.

- 2026-11-02: product slug/name `nosnolimiar` / "Nós no Limiar"; host `nosnolimiar.noctusai.com`; `monica.noctusai.com` retired without redirect.
- 2026-11-02: app and data move to org "Nós no Limiar" (`fa80a1e0-…`); org "Mônica Tangerino" (`ad6ec2e2-…`) deleted; her user and ownership kept.
- 2026-11-02: WAHA renamed now (`waha-nosnolimiar`, `*_NOSNOLIMIAR_*`) because no phone is paired and there are 0 connections.
- 2026-11-02: no agents migration — prod has no `monica-leads` definition; only the code key changes.
- 2026-11-02: the schema-rename migration is the one sanctioned dynamic-policy DO block (test exemption documented in `test_migration_007_org_picker_rollout.py`).

## Retrospective

(Fill at M4.)

## Composes with

`project-history/roadmaps/monica-v1-2026-10.md` · `project-history/roadmaps/product-slug-rename-2026-08.md` · `KB § PATTERNS/devops/prod-exposure-consent.md` · `KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md` · `KB § PATTERNS/architect/product-working-scope.md`.
