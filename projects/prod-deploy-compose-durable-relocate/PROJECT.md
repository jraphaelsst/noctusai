# prod-deploy-compose-durable-relocate — Project Document

- **Created:** 2026-05-25
- **Status:** 📋 Filed (follow-up) — surfaced during the 2026-05-25 full-fleet prod deploy
- **Owner:** joaoraphaelsst · architect
- **Priority:** HIGH — a deploy-local stopgap is currently load-bearing on the live VPS.

---

## 1. Context & Problem

During the 2026-05-25 release (bless `dev→main` + promote `main→prod` of 104 commits + redeploy the 3 live products), `noctus.dev.deploy_image` failed:

```
compose pull core failed: open /opt/noctus/noctusai/projects/production-deploy-migration/deploy/fleet/docker-compose.prod.yml: no such file or directory
```

**Root cause — the durable-config-anchored-to-`projects/` rule biting live prod.** The entire prod deploy tree (fleet + infra + caddy + tunnel composes) lives under `projects/production-deploy-migration/deploy/`. That project was **archived** (→ `archive/projects/2026-05-23/01-production-deploy-migration/deploy/…`) as part of the promoted backlog. The relocation:
1. broke the path that `deploy_image.py` / `vps.py` (`DEFAULT_COMPOSE` constant) and the **running containers' compose project** point at; and
2. moved the compose **2 dir-levels deeper**, so its `env_file: ../../../../.env` no longer resolves to the repo-root `.env`.

The **archive durable-refs gate** (`6eef00f7`) that would have refused this archive **postdates** the archive commit, so nothing caught it. `deploy_image`'s MCP tool does **not** expose a `compose_file` override, so the path can only be changed in code.

**Live fleet was never at risk** (Docker doesn't need the compose file until a container is recreated; `deploy_image`'s snapshot/rollback left the container untouched on the failure).

## 2. Stopgap currently in place (MUST be removed when this lands)

To unblock the deploy without a code change + MCP restart, the prod **fleet** compose was **restored as a deploy-local (untracked) file at the path the tooling expects**:

```
/opt/noctus/noctusai/projects/production-deploy-migration/deploy/fleet/docker-compose.prod.yml
```

(copied from the archive path; `env_file` resolves correctly at that 4-deep location; same `name: noctusai-products-prod` project as the running containers). The 3 live products (core, social-wiring, erp-imobiliario) were then redeployed cleanly. **This stopgap is load-bearing** — every `deploy_image` / `vps.*` op now depends on it. Remove it only after the durable relocate below is deployed.

## 3a. Seed-first analysis

Not a per-product concern — it's a single platform deploy-infra surface. The fix is one durable relocation + the tooling constants, not per-product code.

## 4. Scope

**In scope:**
1. **Relocate** the prod deploy tree out of `projects/`/`archive/` to a **durable repo path** — proposed `deploy/` at repo root (`deploy/fleet/docker-compose.prod.yml`, `deploy/services/…`, `deploy/caddy/…`, `deploy/tunnel/…`). Fix every relative path inside (esp. `env_file` depth) for the new location.
2. **Update the tooling constants** — `DEFAULT_COMPOSE` in BOTH `mcp/noctusai/tools/noctus/dev/deploy_image.py:50` AND `mcp/noctusai/tools/noctus/dev/vps.py:25` (+ any infra-compose constants in `vps.py`); grep `production-deploy-migration/deploy` across `mcp/` + `scripts/` and fix all (also `archive.py:120` doc string + `scripts/infra/build-and-push.sh:8` comment).
3. **Extend the durable-refs gate** so `noctus.dev.archive` ALSO scans `*.py` deploy-tooling constants (`DEFAULT_COMPOSE` and friends), not just docs/CI/composes — the gap that let this through. (Stage-4 codification of this incident.)
4. **Re-point the running compose projects** on the VPS to the durable file (per-product `up -d --force-recreate` from the new path — project name `noctusai-products-prod` is stable, so containers migrate cleanly), then **remove the §2 deploy-local stopgap**.
5. Release: commit→dev → bless → promote → `deploy_pull` (VPS gets `deploy/`) → **restart the MCP server** (so `deploy_image`/`vps` load the new `DEFAULT_COMPOSE`) → `deploy_image` per product from the new path → live-probe → rm stopgap.

**Out of scope:** bringing up the 7 never-deployed products (separate effort; needs edge/DNS/env/migrations).

## 5. Risks / notes
- Requires an **MCP server restart** (user action) for the tooling constants to take effect — call it out at execution time.
- The infra composes (services/caddy/tunnel) ALSO archived; they're running fine but will break on infra recreate — relocate them in the same pass.
- prod-backup (`952e8f20`) + `backup/predeploy-*` tag/tar cover rollback throughout.

## 6. Success criteria
- No `mcp/` / `scripts/` reference resolves into `projects/` or `archive/` for deploy config (grep-clean).
- `deploy_image <product>` + `noctus.vps.*` work from the durable path with the stopgap REMOVED.
- The durable-refs gate fails a hypothetical re-archive that would orphan a deploy constant (regression test).
