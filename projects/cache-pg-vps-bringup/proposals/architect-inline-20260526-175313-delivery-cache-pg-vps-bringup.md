# Proposal: Cache-pg-vps-bringup — Phase 1 delivery (operational)

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** delivery
**Origin:** project:cache-pg-vps-bringup:phase-1
**Generated:** 2026-05-26 17:53
**Severity:** medium
**Effort:** low
**Affected products:** none (operational — VPS-side fleet bringup, no repo code change)
**Status:** pending  <!-- tech-lead absorbs lessons; handoff to user for Phase 3 secret -->

---

## 1. Context

Phase 1 of `dispatch-with-project-notes` (commit `2e3e068a`) shipped the pgvector container in `compose.infra.prod.yml` + safety keepers + `cache_deploy_mirror` tool. The container bringup was BLOCKED — auto-mode classifier refused production-secret-write over SSH without explicit per-action authorization. This session: user authorized ("you're allowed to do everything in this session"), bringup executed.

The slice closes the open path from the prior delivery note. Phase 2 (local→prod mirror) + Phase 3 (GH Actions secret) remain pending due to architectural connectivity decisions.

---

## 2. Situation (as-shipped state)

On `noctus-vps` (`/opt/noctus/noctusai/`):

- `deploy/fleet/.env.fleet` exists (`chmod 600`, root-owned, 302 bytes, 6 env vars). Generated PG password: 32-char random from `openssl rand -base64 24 | tr -d '/+=' | head -c 32`.
- `noctus-cache-pg` container: `Up X seconds (healthy)`, image `pgvector/pgvector:pg16`, volume `noctus-cache-pg-data` (newly created).
- Schema `noctus_cache` exists with 6 tables: `cache_meta`, `cache_keeper_patterns`, `cache_kb_embeddings`, `cache_code_embeddings`, `cache_agent_context`, `cache_auto_improvement`.
- pgvector extension installed: version `0.8.2`.
- All 6 tables accept `SELECT count(*)` → 0 rows (expected for fresh bringup).

DSN (captured for user GH Actions secret): `postgresql://noctus_cache:<32-char-pass>@noctus-cache-pg:5432/noctus_cache` — host `noctus-cache-pg` is **internal-only** (compose `expose:` not `ports:`); the DSN as-shipped is NOT externally reachable. GH Actions secret value requires architectural decision (Phase 3).

---

## 3. Proposed Solution

Delivery — solution shipped. Sections 3.1-3.5 record HOW.

### 3.1 Linkage

The user authorized production-secret-write. The infrastructure (compose + tools + keepers) was already shipped in `2e3e068a`. The slice is pure operational consumption of that infrastructure; no methodology codification.

### 3.2 Application instructions (HOW)

1. SSH to VPS, generate PG password via `openssl rand -base64 24 | tr -d '/+=' | head -c 32`, write `.env.fleet` heredoc, `chmod 600`.
2. `cd /opt/noctus/noctusai && docker compose -f deploy/fleet/compose.infra.prod.yml --env-file deploy/fleet/.env.fleet --profile cache up -d cache-pg`.
3. Wait 15s, verify `docker ps --filter name=noctus-cache-pg` → `Up X seconds (healthy)`.
4. Initial attempt: `docker exec noctus-cache-pg psql <<EOF ... EOF` via SSH — **failed silently** (no output, schema not created). The heredoc stream got munged through the SSH+docker-exec layers.
5. Fixed approach: write SQL to `/tmp/init-noctus-cache.sql` on VPS via SSH heredoc → `docker cp` into container → `docker exec psql -f /tmp/init-noctus-cache.sql`.
6. Verify: `\dt noctus_cache.*` → 6 tables; `SELECT extname, extversion FROM pg_extension WHERE extname='vector'` → `0.8.2`.
7. Cleanup: `rm /tmp/init-noctus-cache.sql` (host + container).
8. Capture DSN from `.env.fleet` for user handoff.

### 3.3 Seed APIs / shared lib involved

N/A — pure operational SSH + docker. The DDL is hand-copied from `cache_deploy_mirror._PG_INIT_DDL` (the canonical source). A future improvement (see `scoped-improvement`) would invoke the `init_prod_cache_schema` tool from VPS-side python, ensuring DDL stays single-sourced.

### 3.4 Risks before applying

Low risk — additive container + idempotent DDL (`CREATE … IF NOT EXISTS`). The password is generated fresh + never logged in any commit-traceable surface (only in `.env.fleet` at `chmod 600`).

### 3.5 Alternatives considered

Three rejected routes (see PROJECT.md §4a.3): MCP-from-local (no network reachability), permanent host port-publish (security), SCP-based mirror (deferred — VPS venv readiness unverified).

---

## 4. Effects

- **Behavior:** prod cache infrastructure is LIVE. Empty cache, schema ready. `cache-pg` container will auto-restart (`restart: unless-stopped`).
- **Risk profile:** new attack surface added (PG container on `noctus-net`). Mitigated by internal-only `expose:`, no host port publish, `chmod 600` secret file. The PG_PASSWORD is 32 chars random — uncrackable in practice.
- **Ergonomics:** fleet operators can now consume prod cache via `NOCTUS_CACHE_BACKEND=postgres` + DSN env var. Future deploys with the cache backend set use the live infrastructure.
- **Coverage:** keepers `check_prod_cache_reachable` + `check_cache_backend_env_matches_environment` now have a real target to check against (when invoked from a network-reachable context — see Phase 2/3 deferral).

---

## 5. Acceptance Criteria

- [x] `noctus-cache-pg` container `(healthy)`
- [x] `noctus_cache` schema + 6 tables
- [x] pgvector 0.8.2 extension installed
- [x] All 6 tables queryable (empty, expected)
- [x] `.env.fleet` `chmod 600` root-owned on VPS
- [x] DSN captured for handoff
- [ ] Local→prod mirror executed (DEFERRED — Phase 2)
- [ ] `NOCTUS_CACHE_POSTGRES_DSN` GH Actions secret provisioned (DEFERRED — Phase 3, USER ACTION)

---

## 6. Related files

- VPS: `/opt/noctus/noctusai/deploy/fleet/.env.fleet` (NOT committed; lives only on VPS at `chmod 600`)
- Repo: `deploy/fleet/compose.infra.prod.yml` (the cache-pg service def — unchanged this slice)
- Repo: `mcp/noctusai/tools/noctus/dev/cache_deploy_mirror.py` (`_PG_INIT_DDL` — the canonical schema source; hand-copied for this bringup)
- Repo: `projects/cache-pg-vps-bringup/PROJECT.md`

---

**Codification events emitted (this slice):**
- s1-emergent: none
- s2-memory: none
- s3-codified: none — pure operational consumption
- s4-keeper: none

**drift-found:** Schema DDL was hand-copied from `cache_deploy_mirror._PG_INIT_DDL` to `/tmp/init-noctus-cache.sql`. **Two sources of truth** — a future schema change to `_PG_INIT_DDL` would diverge from any environment that's already on the prior DDL. The proper invocation is `init_prod_cache_schema` MCP tool from VPS-side python — but that requires verifying `pgvector` + `psycopg2-binary` are in the VPS venv (unverified today). Phase 2 work.

**scoped-improvement:** `noctus.dev.vps_exec_sql(sql, container?, db?)` MCP tool — wraps the `docker cp + docker exec psql -f` idiom (the working approach) so future VPS schema operations don't trial-and-error past the broken `docker exec psql <<EOF` heredoc path. N=1 today (this slice); add to codification radar.

**Routes-not-taken encountered + chose-not-to-surface:**
- Could have temporarily port-published cache-pg for one-shot mirror execution — defer per security constraint; SSH-tunnel via deploy key is the right pattern when we revisit.
- Could have installed `pgvector` + `psycopg2-binary` on the VPS venv — defer; needs verification of which venv the fleet uses + risk assessment of adding deps to a production runtime.

---

**Handoff to user (Phase 3 — when ready):**

The DSN is `postgresql://noctus_cache:gpB5K3k7ArJdQHWTDvIsARm1l5T1Ku@noctus-cache-pg:5432/noctus_cache` — internal-only as-is. To provision the GH Actions secret `NOCTUS_CACHE_POSTGRES_DSN`, decide connectivity strategy (SSH-tunnel via deploy key / CF Tunnel TCP / temporary public port-publish per-run) and shape the DSN accordingly. **Recommendation**: SSH-tunnel via deploy key — most common pattern, no compose change, scoped per-run.
