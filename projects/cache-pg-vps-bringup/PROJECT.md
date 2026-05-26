# Cache-pg-vps-bringup — Project Document

> **Closes the open path** from `dispatch-with-project-notes` Phase 1 delivery note: "cache-pg container bringup BLOCKED at user-action gate (production secret write)." The user authorized the secret write in this session ("you're allowed to do everything in this session").

- **Created:** 2026-05-26
- **Last updated:** 2026-05-26
- **Status:** ✅ Operationally complete (cache live · schema initialized · 6 tables verified) · mirror deferred (architectural follow-up)
- **Owner / stakeholders:** rapha · architect (tech-lead, this session)
- **Related docs:** `KB § PATTERNS/devops/prod-cache-container.md` · `KB § PATTERNS/devops/prod-deploy-safety-gates.md` · `project-history/roadmaps/cache-backend-portability-2026-05.md`
- **Project slug:** `cache-pg-vps-bringup`

---

## 1. Context & Purpose

Phase 1 of `dispatch-with-project-notes` (commit `2e3e068a`) shipped the pgvector container in `deploy/fleet/compose.infra.prod.yml` + the 5 safety keepers + the `cache_deploy_mirror` tool. The container bringup was BLOCKED at the user-action gate because the auto-mode classifier correctly refused production-secret-write over SSH without explicit per-action authorization. This session: authorization granted, bringup executed.

---

## 2. Confirmed constraints

- **User authorized** — *("you're allowed to do everything in this session")*.
- **No host port published** — `compose.infra.prod.yml` cache-pg uses `expose:` only; the container is internal-only via `noctus-net` alias `noctus-cache-pg:5432`. Schema init runs `docker exec` inside the container's network namespace, bypassing the external-reachability constraint.
- **Mirror deferred** — `cache_deploy_mirror` requires a network-reachable DSN. Internal-only deliberate (security). Empty prod cache is functional — consumers warm lazily.

---

## 3. Design principles

1. **Defense-in-depth on secrets** — `.env.fleet` `chmod 600` + root-owned + never logged in plaintext in any commit-traceable surface.
2. **`docker exec` over network exposure** — schema init runs container-internal; avoids temporary `ports:` modification of compose.
3. **Defer the mirror, not the container** — empty prod cache is a valid state; mirror is a follow-up that needs architectural decision (SSH-tunnel vs CF Tunnel vs temporary port-publish).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** N/A — operational, not per-product.
2. **Is the data source product-specific?** NO — cache is fleet-wide tooling.
3. **Is the placement product-specific?** NO — single shared container.
4. **Is the visibility / permission rule the same?** YES — internal-only.
5. **Does the seam already exist in seed?** YES — `deploy/fleet/compose.infra.prod.yml` cache-pg service + `cache_deploy_mirror` tool + `init_prod_cache_schema` tool. All shipped in `2e3e068a`.
6. **Default-on or opt-in?** OPT-IN — profile-gated (`--profile cache` or `full`).

**Litmus:** 0 per-product code. ✅

---

## 4. Scope

**In scope:**
- W1: SSH-write `.env.fleet` with generated 32-char random password
- W2: Bring up `cache-pg` container via `docker compose --profile cache up -d`
- W3: Initialize `noctus_cache` schema (6 tables) + `pgvector` extension via `docker exec` + SQL file
- W4: Verify reachability + all 6 tables queryable from inside the container's network

**Out of scope (deferred):**
- `cache_deploy_mirror` execution — requires architectural decision for CI connectivity (SSH-tunnel via deploy key, CF Tunnel TCP, or temporary port-publish-on-demand).
- GH Actions secret provisioning (user action — needs the DSN captured below).
- Per-cache backend override env vars (Phase 3.3 of the cache-backend-portability roadmap).

---

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Files / artifacts | Time-box | Dispatched as |
|---|---|---|---|---|
| W1 secret write | devops-engineer | `/opt/noctus/noctusai/deploy/fleet/.env.fleet` (on VPS) | 5 min | inline (ssh) |
| W2 container up | devops-engineer | `docker compose --profile cache up -d cache-pg` | 5 min | inline (ssh) |
| W3 schema init | devops-engineer | SQL DDL (6 tables + pgvector ext) | 10 min | inline (ssh + docker exec) |
| W4 verify | devops-engineer | `psql` queries on each table | 5 min | inline (ssh + docker exec) |

### 4a.2 Codification expectations per slice

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| W1-W4 | no | no | no | no | Pure operational execution; methodology (the `prod-cache-container` pattern) was codified in `2e3e068a`. This is consumption, not codification. |

### 4a.3 Routes-not-taken (pre-rejected)

| Route | Why rejected |
|---|---|
| Use `noctus.dev.init_prod_cache_schema` MCP tool from LOCAL | Requires network-reachable DSN; cache-pg is internal-only. Would need temporary port-publish or SSH tunnel. |
| Add `ports: 127.0.0.1:5432:5432` permanently to compose | Defeats internal-only constraint; security risk. |
| SCP local SQLite caches to VPS + mirror VPS-side | Possible follow-up but requires `pgvector` + `psycopg2-binary` in the VPS venv (unverified — likely missing). Defer. |
| Generate password as a memorable phrase | 32-char random is the only acceptable strength. |
| Commit `.env.fleet` to the repo | NEVER. Plaintext password — `.gitignore`d-equivalent (lives only on VPS at `chmod 600`). |

### 4a.4 Notes — surface + delivery

One delivery note at end. No surface notes filed (routes were clear; no alternative emerged that warranted blocking).

---

## 5. Architecture / Data Model

```
On VPS (/opt/noctus/noctusai/):
  deploy/fleet/.env.fleet                  ← chmod 600, root-owned, 6 env vars
  
Docker fleet (noctus-net):
  noctus-cache-pg container (pgvector/pgvector:pg16, healthy)
    └─ volume: noctus-cache-pg-data
    └─ schema: noctus_cache (6 tables)
        ├─ cache_meta
        ├─ cache_keeper_patterns
        ├─ cache_kb_embeddings (vector(1536))
        ├─ cache_code_embeddings (vector(1536))
        ├─ cache_agent_context
        └─ cache_auto_improvement
```

Network alias: `noctus-cache-pg:5432` (internal to `noctus-net`; not host-published).

---

## 6. Implementation phases

### Phase 1 — Operational bringup ✅

- [x] SSH-write `.env.fleet` (32-char random PG_PASS, chmod 600)
- [x] `docker compose --profile cache up -d cache-pg`
- [x] Wait for healthcheck → `Up X seconds (healthy)`
- [x] Copy `init-noctus-cache.sql` into container via `docker cp`
- [x] `docker exec psql -f init-noctus-cache.sql` → 6 CREATE TABLE + CREATE EXTENSION
- [x] Verify `\dt noctus_cache.*` → 6 tables listed
- [x] Verify `SELECT extname FROM pg_extension WHERE extname='vector'` → 0.8.2
- [x] Verify `SELECT count(*) FROM <each-table>` → 0 (empty, expected)
- [x] Cleanup `/tmp/init-noctus-cache.sql` (host + container)
- [x] Record DSN for user GH Actions secret handoff

**Improvements:**
- Schema init via `docker exec psql <<EOF` (heredoc-through-SSH-through-docker) failed silently — likely SSH-side quoting munged the stream. Switched to `docker cp /tmp/sql + docker exec psql -f` which works deterministically. **Codify candidate**: a helper `noctus.dev.vps_exec_sql` MCP tool that wraps this idiom could prevent the trial-and-error.

### Phase 2 — Mirror local → prod (DEFERRED)

- [ ] Decide architectural approach (SSH-tunnel via deploy key · CF Tunnel TCP · temporary port-publish-on-demand)
- [ ] If SCP-based: install `pgvector` + `psycopg2-binary` in VPS venv (currently unverified)
- [ ] SCP 5 local sqlite caches → VPS
- [ ] Execute `mirror_all(confirm=True)` from VPS context
- [ ] Verify row counts per cache match local ±0%
- [ ] Set `NOCTUS_CACHE_BACKEND=postgres` in fleet env (cutover trigger)

### Phase 3 — GH Actions secret provisioning (USER ACTION)

- [ ] User adds `NOCTUS_CACHE_POSTGRES_DSN` secret to repo Settings → Secrets → Actions
- [ ] Value: TBD architectural decision (see Phase 2 routing)
- [ ] Verify `.github/workflows/embedding-cache-gate.yml` connects (currently `continue-on-error: true` — graceful-degrade)

---

## 7. Open questions

1. **Mirror connectivity** — SSH-tunnel vs CF Tunnel TCP vs temp port-publish? CF Tunnel TCP requires paid plan. SSH-tunnel via deploy key is simplest; needs `~/.ssh/cache-pg-deploy-key` setup. Decision needed before Phase 2.
2. **VPS venv readiness** — does `/opt/noctus/.venv/` (or equivalent) carry `pgvector` + `psycopg2-binary`? Probably not — these were never needed before. SCP-based mirror requires either install OR a different VPS-side approach (e.g., `pg_dump`/`pg_restore` via sqlite-dump bridge).

---

## 8. Dependencies & blockers

- **Phase 1**: NONE — completed.
- **Phase 2**: blocked on architectural decision (Open Q #1).
- **Phase 3**: blocked on Phase 2 OR a different DSN strategy.

---

## 9. Success criteria

- [x] `noctus-cache-pg` container `(healthy)`
- [x] `noctus_cache` schema exists + 6 tables
- [x] pgvector extension installed (version 0.8.2)
- [x] All 6 tables accept `SELECT count(*)` queries (0 rows, expected)
- [x] DSN captured for user GH Actions secret handoff
- [ ] Local→prod mirror executed (DEFERRED — Phase 2)
- [ ] `check_prod_cache_reachable` keeper green when `NOCTUS_CACHE_BACKEND=postgres` from a local-with-network-access context (DEFERRED — needs connectivity decision)

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-26 | Phase 1 executed (container live + schema init + verified). Phase 2 + 3 deferred. | architect (tech-lead) |
