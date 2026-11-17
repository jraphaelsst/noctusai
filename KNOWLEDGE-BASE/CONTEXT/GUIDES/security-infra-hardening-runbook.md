# Security infra hardening — apply runbook (re-derived 2026-11-15)

> **Self-contained.** Apply runbook for the repo changes shipped by `feat/sec-infra-hardening-v2` (re-derived on a
> fresh `origin/dev` from the audit of 2026-10-19; the stale branch `feat/sec-infra-hardening` was dropped).
> **Nothing here was applied to prod by the author.** Roles: **OWNER** = pastes secrets / clicks in GitHub or Cloudflare;
> **STEWARD** = the release steward (MCP tools + `vps_exec confirm=True`). Secrets never enter chat or a tool result.

## What this change did

Rule (owner, 2026-11-15): **the build produces the correct state; checkers are safety nets.** So nothing here asks a human for a
secret that can be derived, and merging blocks no deploy (test `test_merging_requires_no_new_secret_anywhere`).

| Intent | How the build produces it |
|---|---|
| Private GHCR | ONE human-made secret: a classic PAT (`read:packages`). `noctus.dev.ghcr_access install` writes it, logs the VPS in, verifies, and only then hands over the flip URLs. User derived from the image namespace. The `ghcr_login` predeploy leg is a net: public packages need no login, private ones require it (measured by an anonymous pull probe, not a flag). |
| Redis passwords (services, legacy) | DERIVED from the existing `REDIS_ACL_MASTER_SECRET` by `noctus.dev.redis_acl render --write` into the gitignored `redis-auth/` directory beside each compose (services: one password file; legacy: password file (also gets both Celery URLs)). Compose reads them with `env_file ... required: false`; no `:?`. |
| `WAHA_DASHBOARD_USERNAME` | Not a secret: committed default `noc-admin`, overridable. (Recreate changes the dashboard login from the previous default.) |
| Image pins | Postgres, pgvector, n8n, services Redis, cloudflared, infra Redis are pinned to the digests prod is RUNNING (read 2026-11-15) => no-op recreates. Construction: `noctus.dev.image_pin` (check / pin / bump) resolves + writes digests; Dependabot `docker-compose` blocks (`refresh_dependabot_coverage`) keep them moving; keeper `check_supply_chain_pin` is the net. |
| WAHA hostname | **Unchanged** (`waha.noctusai.com` still routed). Hook URL is internal (independent). Owner decision below. |
| Legacy isolation | `legacy-net` + dedicated `legacy-redis`; tunnel bridges both (§ 5). |
| SHA-pinned Actions | Already on dev; keeper only (§ 6). |

## Global order

0. **Only human step:** install the GHCR token (§ 1). Everything else is tools run by the steward.
1. § 1 `ghcr_access install` -> 2. owner flips packages private -> 3. `redis_acl render --write` on the VPS (§ 4) -> 4. image rollouts (§ 2, no-ops) -> 5. § 5 legacy -> 6. § 6.

## 1 - GHCR images private (the only human step)

1. OWNER: GitHub -> Settings -> Developer settings -> **Personal access tokens (classic)** -> scope `read:packages` only, 90-day expiry.
   Fine-grained PATs cannot read GHCR (the tool refuses them). Put it in a local env var; never paste it in chat:
   `export GHCR_READ_TOKEN=...` in the shell that launches the MCP server, or pipe it to the CLI.
2. STEWARD: `noctus.dev.ghcr_access action=status` (read-only; shows per-package visibility + VPS login), then
   `noctus.dev.ghcr_access action=install confirm=True`
   (CLI: `printf %s "$GHCR_READ_TOKEN" | python mcp/noctusai/cli.py --ghcr-access install --ghcr-access-confirm --ghcr-access-token-stdin`).
   It writes `GHCR_READ_TOKEN` to the VPS `.env.fleet` (0600, over ssh stdin), runs `docker login ghcr.io` there as the derived
   namespace user, verifies the login is recorded + an authenticated manifest request, and **only then** returns the settings URLs.
3. OWNER: open each returned URL -> Danger zone -> **Change visibility -> Private** (GitHub has no API for this). Confirm *Manage Actions
   access* lists `jraphaelsst/noctusai` with **Write** so `build-and-push.yml` keeps pushing.
4. STEWARD verify: `ghcr_access action=status` shows packages private + `vps_logged_in`; `predeploy_check <p>` leg `ghcr_login` ok;
   from a laptop `docker logout ghcr.io; docker pull ghcr.io/jraphaelsst/noctus-core:latest` fails.

Rollback: re-run install with a fresh token; last resort set the package public (UI), against policy, record it.

## 2 - Image pins are no-ops

Pinned to what runs now, so `up -d` recreates the same image. Preflight (read-only) if desired:
`docker inspect <container> --format '{{.Image}}'` equals the pin for `noctus-tunnel`, `noctus-redis`, `noctus-services-postgres-1`,
`noctus-cache-pg`, n8n and the services Redis. Later upgrades are deliberate: `noctus.dev.image_pin action=bump image=<name> tag=<tag>
write=True` (or merge the Dependabot docker-compose PR), then recreate. `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` is the n8n 2.x default made explicit.

## 3 - WAHA public hostname: OWNER DECISION (not changed in this slice)

`waha.noctusai.com` is still routed because the owner's WAHA MCP connector uses it (`WAHA_BASE_URL=https://waha.noctusai.com`).
The dashboard + REST API on the open internet is the audit finding; options:

- **Recommended: keep the hostname, put Cloudflare Access in front.** A service-token Access policy on `waha.noctusai.com`; the connector
  sends `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers; browsers go through Access login. No connector URL change.
  Check first whether `tunnel_config` / `cloudflare_dns` can manage Access: they cannot today (they manage ingress + CNAMEs only), so
  creating the Access app + token is a Cloudflare Zero Trust dashboard step for the owner, then the connector gets the two header env vars.
- Fallback: SSH port-forward, hostname retired: `ssh -L 3000:<waha-container-ip>:3000 noctus-vps`, `WAHA_BASE_URL=http://localhost:3000`;
  then move `waha.noctusai.com` into `ingress.yml` `retired:` and `tunnel_config apply confirm=True`, delete the CNAME.

Consumers in the repo already use the internal name (`http://waha:3000`); the WAHA -> n8n hook is `http://n8n:5678/webhook/webhook`.

## 4 - Redis passwords (derived, nothing to type)

Master = the existing `REDIS_ACL_MASTER_SECRET` in the VPS `.env.fleet`. STEWARD on the VPS checkout:
`python mcp/noctusai/cli.py --redis-acl render --redis-acl-write` (adds `--redis-acl-services` only for the fleet ACL cutover; see
`KB § PATTERNS/devops/redis-acl-lockdown.md`). It writes the services Redis password and the legacy password + Celery URLs. Then
`docker compose --env-file .env.services -f compose.services.yml up -d redis`; confirm unauthenticated `redis-cli ping` -> `NOAUTH`.
A stack that has not been rendered starts exactly as before (no password), so nothing fails in between. Derived client list for the services
Redis = none (test `test_services_redis_has_no_unauthenticated_clients`). Rotation: bump `REDIS_ACL_GENERATION_OVERRIDES` (`services-redis=2`).

## 5 - Legacy on its own network + own Redis

1. STEWARD: `docker network create legacy-net`; `docker network connect legacy-net noctus-tunnel`.
2. STEWARD: render (§ 4), check the old queue is idle (`celery -A backend inspect active`).
3. STEWARD: `cd deploy/legacy && docker compose -f compose.legacy.yml --env-file .env up -d` (~30 s legacy downtime).
4. Verify `https://legacy.noctusai.com/` 200; `docker exec noctus-core getent hosts legacy` empty.
5. OWNER (optional): Cloudflare Access on `legacy.noctusai.com` `/admin*`.

Rollback: `docker network connect noctus-net legacy-permutas legacy-permutas-celery`, restore old `.env` broker URLs.

## 6 · CI

Already SHA-pinned on dev; this change adds the gate. New Action or version bump: Dependabot's github-actions block opens SHA-pinned bumps; a hand-added Action is pinned from `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (dereference annotated tags) and written `@<40-hex>  # <tag>`; the keeper `check_supply_chain_pin` / the CI test refuse anything else. Repo settings (OWNER decides; the free plan refuses branch protection / secret scanning with
HTTP 403 — Pro is the owner's call): `gh api -X PUT repos/jraphaelsst/noctusai/actions/permissions -F enabled=true -f allowed_actions=selected -F sha_pinning_required=true`
then the `selected-actions` allowlist (`actions/*`, `docker/*`, `aquasecurity/trivy-action@*`, `gitleaks/gitleaks-action@*`, `github/codeql-action/*`),
in that order, only after the workflows on dev are green.
