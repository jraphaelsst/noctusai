# RUNBOOK — cutover `monica` -> `nosnolimiar` ("Nós no Limiar") + old-org delete

Owner decisions 2026-11-02. Roadmap: `project-history/roadmaps/nosnolimiar-rename-2026-11.md`.
Every prod step is **owner-gated** (confirm=True). Downtime is a short maintenance window: no WhatsApp phone is
paired and there are 0 connections, so nothing is lost. Run the steps IN ORDER.

Names: schema `monica` -> `nosnolimiar` · host `monica.noctusai.com` (retired, no redirect) -> `nosnolimiar.noctusai.com`
· service/container/image `monica` -> `nosnolimiar` (`noctus-nosnolimiar`, `ghcr.io/jraphaelsst/noctus-nosnolimiar`)
· WAHA `waha-monica` -> `waha-nosnolimiar` · port 8020/8240 unchanged.

## Phase B — before the window (no prod change)

> **🔴 Sequencing: this branch lands on `dev` ONLY at the start of the window.** Once it is on `dev`, the next prod ship by *any* session blesses it, and `migrate_product core sha=<blessed>` applies **core 098**. That renames the catalog slug in place while the old `monica` container is still serving, which effectively opens the cutover window early. Enqueue it (`task_branch action=enqueue slug=nosnolimiar-rename`) immediately before B2, and only once the owner has scheduled the window. It was enqueued and then withdrawn on 2026-11-05 for exactly this reason. Its review is done: slice score logged, findings fixed through 9573e4bab.

| Step | Command | Rollback |
|---|---|---|
| B0 | `deploy/consent/nosnolimiar.prod.yml` committed in HEAD (tech-lead, after the owner types the phrase); then the wiring commit | n/a |
| B1 | CI: `workflow_dispatch build-and-push products=nosnolimiar` (bypasses build-scope); confirm `ghcr.io/jraphaelsst/noctus-nosnolimiar` exists and the VPS can pull it | leave the new package unused |
| B2 | `noctus.dev.release stage=bless` then `stage=promote confirm=True` | `prod-backup` |
| B3 | `noctus.dev.deploy_pull confirm=True` (updates the checkout only; starts nothing) | `prod-backup` |
| B4 | ✅ DONE 2026-11-05 14:49Z (new keys added, old kept; backups `*.bak-nnl-20261105-144929`). VPS `deploy/fleet/.env.fleet`: rename `WAHA_MONICA_API_KEY` / `WAHA_MONICA_HMAC_SECRET` / `WAHA_MONICA_DASHBOARD_PASSWORD` to `WAHA_NOSNOLIMIAR_*` (same values). VPS root `.env`: rename `MONICA_WAHA_WEBHOOK_HMAC_SECRET` -> `NOSNOLIMIAR_WAHA_WEBHOOK_HMAC_SECRET` (same value, must equal `WAHA_NOSNOLIMIAR_HMAC_SECRET`); `MONICA_WAHA_BASE_URL/SESSION` are set by compose, delete them; add `NOSNOLIMIAR_INBOX_REALTIME_IN_PROCESS` / `NOSNOLIMIAR_AGENT_KEY` only if the old ones were set. Keep the old keys until D3. | restore the old keys |
| B5 | ✅ DONE 2026-11-05 (`cloudflared tunnel route dns` via the cloudflared image + VPS `cert.pem`). Cloudflare DNS: CNAME `nosnolimiar` -> the tunnel (same target as `erp.`/`social.`); verify it exists | delete the record |
| B6 | Rollback point: pg backup/PITR marker, `prod-backup` tag, old image id (`noc.vps.inspect noctus-monica`), copy of the live `deploy/tunnel/config.yml` | n/a |

## Phase C — the window

| Step | Command | Rollback |
|---|---|---|
| C1 | Stop the old app: `noctus.vps.exec "docker stop noctus-monica" confirm=True` | `docker start noctus-monica` |
| C2 | Core catalog: `noctus.dev.migrate_product product=core confirm=True` (applies **core 098**: slug/nome/url_base/db_schema renamed in place; licenses and org-picker selections survive; the slug in the platform tables is renamed in every catalog-derived `product`/`product_slug`/`produto`/`owner_product` column of `public`+`agents` -- `scheduler_jobs`, `platform_templates`, `agents.agent_product_grants`, ... -- except the declared historical set; the migration fails if a non-historical column still holds `monica`) | `UPDATE public.products SET slug='monica', nome='Monica', url_base='https://monica.noctusai.com', db_schema='monica' WHERE slug='nosnolimiar'` **and** revert the slug in the derived tables: run `UPDATE <schema>.<table> SET <col>='monica' WHERE <col>='nosnolimiar'` for each of `public.scheduler_jobs.product`, `public.platform_templates.product`, `agents.agent_product_grants.product` (and any other non-historical column 098 touched: list them with the 098 candidate query -- `information_schema.columns` in `public`/`agents`, names `product|product_slug|produto|owner_product`, minus the historical list in 098) |
| C3 | Product schema: `noctus.dev.migrate_product product=nosnolimiar schema=monica confirm=True` (the ledger still lives in `monica.schema_migrations`; on a FRESH database, where `migrate_product` without `schema=monica` created `nosnolimiar` + its ledger before 001 created `monica`, 020 adopts that ledger-only schema: ledger rows merged into monica's, the empty schema dropped, then renamed; **020** renames the schema, re-points functions + RLS policies + acting-audit triggers, and SWAPS `monica` -> `nosnolimiar` in `pgrst.db_schemas`, all in one statement). The ledger-INSERT after 020 warns (the schema moved) — expected. Then: `noctus.dev.migrate_product product=nosnolimiar confirm=True` (no override: 020 is a no-op, it just records itself in the renamed ledger). Check: `noctus.dev.ensure_schema_exposure action=check`, a REST call against another product's schema (PostgREST still loads), `noctus.dev.verify_db_guards`. | `projects/rename-2026-11/rollback-020.sql` (reverse C2 FIRST) |
| C4 | Data move + org delete: run `cutover-dry-run.sql` (ends in ROLLBACK; read the NOTICEs -- one `inventory: allowed cascade ...` line per table the delete will cascade), then `cutover.sql`. Guards that abort BEFORE any change: NnL holds an active license on `nosnolimiar`; no `storage.objects` row is filed under MT's org id (Storage is NOT moved by this script -- move/re-key first). Section 6a is a catalog-derived inventory (every FK onto `organizations`, any ON DELETE action, multi-column keys, plus one hop through `org_memberships`) that aborts if a table outside the allowlist still holds MT rows (allowlist: pipeline_stages 13, licenses 2, org_memberships 1, platform_org_selections target 13 / home 4; notifications are MOVED). `cutover-dry-run.sql` is `cutover.sql` with only the first line and COMMIT->ROLLBACK changed (test `mcp/noctusai/tests/test_nosnolimiar_rename_on_replay.py` enforces it; regenerate after any edit). **Owner confirms first** (the org delete and the 5-row audit purge are irreversible) | none after COMMIT — restore from the B6 backup. The dry-run exists for this reason |
| C5 | Infra: `noctus.dev.ensure_product_url_roster confirm=True` (adds `PRODUCT_URL_NOSNOLIMIAR`, recreates core); `noctus.dev.refresh_build_scope` + commit the regenerated scope files; `noctus.dev.predeploy_check product=nosnolimiar` (the `db_guards` leg is red until C3 — that is why it runs here); `noctus.dev.waha_instance action=apply name=nosnolimiar confirm=True` | `waha_instance remove name=nosnolimiar` |
| C6 | App: `noctus.dev.deploy_image product=nosnolimiar confirm=True` | `up` the old `monica` service from the `prod-backup` compose with the old image |
| C7 | Tunnel: `noctus.dev.tunnel_config action=apply confirm=True` (new host on; `monica.noctusai.com` is in `retired:` so apply may drop it) | restore the saved `config.yml`, restart cloudflared |
| C8 | Verify: `noctus.dev.deploy_verify`; `noctus.dev.spa_smoke products=['nosnolimiar']`; `noctus.dev.sso_cors_smoke`; `noctus.dev.sso_smoke product=nosnolimiar`; `noctus.dev.latency_report product=nosnolimiar`; manual login as Mônica -> lands in "Nós no Limiar"; Financeiro lists the 30 categories; Contexto/Leads/Pacientes load; `monica.noctusai.com` no longer resolves to the app | see rollback below |

> **🔴 C4 BLOCKED — owner decision pending (2026-11-05).** Owner rule "one branding per org" (relayed by noctusai-3d): exactly ONE `social_wiring.marcas` row per org. `cutover.sql` step 3 moves EVERY `social_wiring.*` row from MT to NnL — incl. MT's marca `07798cf9…` ("Mônica Tangerino", pessoa_fisica) as a non-primary 2nd brand on NnL (which has its own primary `06c35543…`). That violates the rule. Do NOT run C4 as written. Owner picks: (A) keep the MT org — no delete; move users/licenses only, MT keeps its brand; (B) archive the MT marca (+ its cs_chat rows) and still delete the org; (C) other. Re-cut step 3 + the 6a allowlist + the post-check (NnL marca count == 1, total) to the choice, regenerate the dry-run, coordinate with 3d's marcas unique-per-org constraint, then re-show the dry-run NOTICEs.

**Full rollback (any time before C4 commits):** C7 restore tunnel -> C6 old service up -> `rollback-020.sql` -> reverse core 098 (C2 rollback) -> restore `.env` keys.
After C4 commits the org delete cannot be undone from SQL; restore from backup only.

## Phase D — cleanup

| Step | Command |
|---|---|
| D1 | `noctus.vps.exec "docker rm noctus-monica" confirm=True`; remove the old `waha-monica` container + its (empty) volume `noctus-waha-monica` (no phone was ever paired) |
| D2 | Remove stale VPS `.env` keys (`PRODUCT_URL_MONICA`, `MONICA_WAHA_*`) and `.env.fleet` `WAHA_MONICA_*`; keep the old GHCR package `noctus-monica` a few weeks as cold rollback |
| D3 | Archive the roadmap `nosnolimiar-rename-2026-11.md` |

## Notes

- `deploy/consent/monica.prod.yml` stays as the historical record of the original exposure.
- Sessions in flight at C2 become invalid; users log in again.
- Agents: no `monica-leads` definition or owner_product row exists in prod, so no agents migration is needed; the key in the code is now `nosnolimiar-leads` (ops/agents/README.md).
- Historical rows keep the old slug on purpose: `sso_token_redemptions.product='monica'` (13), `audit_logs.product_slug`.
