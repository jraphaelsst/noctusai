# RUNBOOK — cutover `monica` -> `nosnolimiar` ("Nós no Limiar") + old-org delete

Owner decisions 2026-11-02. Roadmap: `project-history/roadmaps/nosnolimiar-rename-2026-11.md`.
Every prod step is **owner-gated** (confirm=True). Downtime is a short maintenance window: no WhatsApp phone is
paired and there are 0 connections, so nothing is lost. Run the steps IN ORDER.

Names: schema `monica` -> `nosnolimiar` · host `monica.noctusai.com` (retired, no redirect) -> `nosnolimiar.noctusai.com`
· service/container/image `monica` -> `nosnolimiar` (`noctus-nosnolimiar`, `ghcr.io/jraphaelsst/noctus-nosnolimiar`)
· WAHA `waha-monica` -> `waha-nosnolimiar` · port 8020/8240 unchanged.

## Phase B — before the window (no prod change)

| Step | Command | Rollback |
|---|---|---|
| B0 | `deploy/consent/nosnolimiar.prod.yml` committed in HEAD (tech-lead, after the owner types the phrase); then the wiring commit | n/a |
| B1 | CI: `workflow_dispatch build-and-push products=nosnolimiar` (bypasses build-scope); confirm `ghcr.io/jraphaelsst/noctus-nosnolimiar` exists and the VPS can pull it | leave the new package unused |
| B2 | `noctus.dev.release stage=bless` then `stage=promote confirm=True` | `prod-backup` |
| B3 | `noctus.dev.deploy_pull confirm=True` (updates the checkout only; starts nothing) | `prod-backup` |
| B4 | VPS `.env.fleet`: rename `WAHA_MONICA_API_KEY` / `WAHA_MONICA_HMAC_SECRET` / `WAHA_MONICA_DASHBOARD_PASSWORD` to `WAHA_NOSNOLIMIAR_*` (same values). VPS root `.env`: rename `MONICA_WAHA_WEBHOOK_HMAC_SECRET` -> `NOSNOLIMIAR_WAHA_WEBHOOK_HMAC_SECRET` (same value, must equal `WAHA_NOSNOLIMIAR_HMAC_SECRET`); `MONICA_WAHA_BASE_URL/SESSION` are set by compose, delete them; add `NOSNOLIMIAR_INBOX_REALTIME_IN_PROCESS` / `NOSNOLIMIAR_AGENT_KEY` only if the old ones were set. Keep the old keys until D3. | restore the old keys |
| B5 | Cloudflare DNS: CNAME `nosnolimiar` -> the tunnel (same target as `erp.`/`social.`); verify it exists | delete the record |
| B6 | Rollback point: pg backup/PITR marker, `prod-backup` tag, old image id (`noc.vps.inspect noctus-monica`), copy of the live `deploy/tunnel/config.yml` | n/a |

## Phase C — the window

| Step | Command | Rollback |
|---|---|---|
| C1 | Stop the old app: `noctus.vps.exec "docker stop noctus-monica" confirm=True` | `docker start noctus-monica` |
| C2 | Core catalog: `noctus.dev.migrate_product product=core confirm=True` (applies **core 095**: slug/nome/url_base/db_schema renamed in place; licenses and org-picker selections survive) | `UPDATE public.products SET slug='monica', nome='Monica', url_base='https://monica.noctusai.com', db_schema='monica' WHERE slug='nosnolimiar'` |
| C3 | Product schema: `noctus.dev.migrate_product product=nosnolimiar schema=monica confirm=True` (the ledger still lives in `monica.schema_migrations`; **020** renames the schema, re-points functions + RLS policies + acting-audit triggers, and SWAPS `monica` -> `nosnolimiar` in `pgrst.db_schemas`, all in one statement). The ledger-INSERT after 020 warns (the schema moved) — expected. Then: `noctus.dev.migrate_product product=nosnolimiar confirm=True` (no override: 020 is a no-op, it just records itself in the renamed ledger). Check: `noctus.dev.ensure_schema_exposure action=check`, a REST call against another product's schema (PostgREST still loads), `noctus.dev.verify_db_guards`. | `projects/rename-2026-11/rollback-020.sql` (reverse C2 FIRST) |
| C4 | Data move + org delete: run `cutover-dry-run.sql` (ends in ROLLBACK; read the NOTICEs), then `cutover.sql`. **Owner confirms first** (the org delete and the 5-row audit purge are irreversible) | none after COMMIT — restore from the B6 backup. The dry-run exists for this reason |
| C5 | Infra: `noctus.dev.ensure_product_url_roster confirm=True` (adds `PRODUCT_URL_NOSNOLIMIAR`, recreates core); `noctus.dev.refresh_build_scope` + commit the regenerated scope files; `noctus.dev.predeploy_check product=nosnolimiar` (the `db_guards` leg is red until C3 — that is why it runs here); `noctus.dev.waha_instance action=apply name=nosnolimiar confirm=True` | `waha_instance remove name=nosnolimiar` |
| C6 | App: `noctus.dev.deploy_image product=nosnolimiar confirm=True` | `up` the old `monica` service from the `prod-backup` compose with the old image |
| C7 | Tunnel: `noctus.dev.tunnel_config action=apply confirm=True` (new host on; `monica.noctusai.com` is in `retired:` so apply may drop it) | restore the saved `config.yml`, restart cloudflared |
| C8 | Verify: `noctus.dev.deploy_verify`; `noctus.dev.spa_smoke products=['nosnolimiar']`; `noctus.dev.sso_cors_smoke`; `noctus.dev.sso_smoke product=nosnolimiar`; `noctus.dev.latency_report product=nosnolimiar`; manual login as Mônica -> lands in "Nós no Limiar"; Financeiro lists the 30 categories; Contexto/Leads/Pacientes load; `monica.noctusai.com` no longer resolves to the app | see rollback below |

**Full rollback (any time before C4 commits):** C7 restore tunnel -> C6 old service up -> `rollback-020.sql` -> reverse core 095 (C2 rollback) -> restore `.env` keys.
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
