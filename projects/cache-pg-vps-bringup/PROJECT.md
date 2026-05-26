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

### 7a. Resolved: VPS environment audit (2026-05-26 evening)

Confirmed via `ssh noctus-vps`:
- **No `/opt/noctus/.venv/`** exists. System python is `/usr/bin/python3`.
- **No `psycopg2` or `pgvector` Python packages** on system python.
- **Port `5432` is free** on the VPS host (`ss -tln` shows nothing listening; no other PG container publishes the port; legacy-permutas and fleet services live on 8xxx/3000/6379/5678).
- **`noctus-cache-pg:5432` is reachable only inside the `noctus-net` docker network** — host can `docker exec`, container-internal alias works, but the VPS host's own python can't `connect()` directly without a route.

These facts shape the recommendations below — Option F.2 is the lowest-friction sequence.

### 7b. Recommended sequence (Phase 2 → Phase 3)

The two open paths from the prior delivery note are connected: Phase 2 needs short-term local→prod connectivity (one-shot mirror); Phase 3 needs sustainable CI-runner→prod connectivity. The trade-off table covers all six concrete routes:

| # | Route | What changes | Phase 2 fit | Phase 3 fit | Effort | Pros | Cons |
|---|---|---|---|---|---|---|---|
| A | **SSH-tunnel via GH Actions deploy key + host-loopback publish** | Add `ports: ["127.0.0.1:5432:5432"]` to cache-pg compose. Provision deploy key. GH Actions uses `ssh-action` to forward `-L 5432:127.0.0.1:5432 noctus-vps`. | Works (after compose change) | **STRONG FIT** | medium | Standard CI pattern · scoped per-run · no public exposure · works for Phase 2 too | Compose change (1 line) · deploy-key provisioning · key rotation discipline |
| B | **Cloudflare Tunnel TCP** | Run `cloudflared tunnel` with a TCP route to cache-pg. GH Actions uses `cloudflared access tcp`. | Works | Works | high | Managed · no port exposure · no SSH keys | **Paid CF plan required for TCP** · vendor lock-in · additional component to operate |
| C | **Profile-gated temp port-publish** | Add a `cache-debug` compose profile with `ports: ["127.0.0.1:5432:5432"]`. Operator runs `up --profile cache,cache-debug` for one-off ops; takes back down. | Works | Awkward (CI must orchestrate compose up/down) | low | Surgical · scoped per-operation · no permanent host port | Two states for the compose; CI scripting overhead; operator must remember to take down |
| D | **VPS-side mirror via `vps_exec_sql` + SQL generation** | Read local SQLite → generate `INSERT … VALUES …` SQL → stream via `noctus.vps.exec_sql`. NO connectivity change. | Works (with per-cache SQL generators) | N/A (one-way local→prod, not query-shaped) | medium-high | NO compose change · uses the new tool · no connectivity infra | 5 cache schemas to generate; pgvector BLOB encoding is non-trivial; doesn't reuse `cache_deploy_mirror` |
| E | **Sidecar container on `noctus-net`** | Build a `python:3.13-slim + pip install -e mcp/noctusai` image; run inside `noctus-net` so it resolves `noctus-cache-pg:5432` natively. | Works | Awkward (CI invokes container build) | medium | Reuses `cache_deploy_mirror` as-is · no host pkg install | Image build/maintenance · cold-start latency in CI |
| F | **VPS-side python venv at `/opt/noctus/.venv/`** | `python3 -m venv /opt/noctus/.venv && pip install -r mcp/noctusai/requirements.txt` on VPS. Run `cache_deploy_mirror` via VPS-side `python cli.py`. Cache-pg port reached via either (F.1) docker bridge IP, (F.2) host-loopback publish, or (F.3) docker network from within a sidecar. | Works | Works (combined with A or C) | low-medium | One-time setup · reuses tool · self-contained on VPS | Adds python deps to VPS host (low impact — venv-isolated); needs the network route decision |

### 7c. Recommended sequence — pick this

**Phase 2 (mirror NOW, one-shot)** — **Route F.2** (VPS-side venv + host-loopback publish):

1. One-line compose change: add `ports: ["127.0.0.1:5432:5432"]` to cache-pg (host-loopback only, NOT public — security posture preserved).
2. Recreate the container: `docker compose --profile cache up -d --force-recreate cache-pg`.
3. SSH to VPS: `python3 -m venv /opt/noctus/.venv` (one-time).
4. Activate + `pip install psycopg2-binary pgvector` (one-time).
5. From local: SCP the 5 local SQLite caches to `noctus-vps:/opt/noctus/cache-snapshots/`.
6. SSH to VPS: run `/opt/noctus/.venv/bin/python /opt/noctus/noctusai/mcp/noctusai/cli.py --cache-deploy-mirror --confirm` against `localhost:5432` DSN.
7. Verify row counts via `noctus.vps.exec_sql` (e.g., `SELECT count(*) FROM noctus_cache.cache_keeper_patterns`).

Why F.2: smallest compose change · reuses `cache_deploy_mirror` as-is · sets up the infra Phase 3 will also use · keeps cache-pg internal (host-loopback ≠ public).

**Phase 3 (CI sustainable)** — **Route A** (GH Actions deploy key + the same host-loopback publish from Phase 2):

1. Generate a deploy key: `ssh-keygen -t ed25519 -f /tmp/cache-deploy-key -N ''`.
2. Add public half to `noctus-vps:~/.ssh/authorized_keys` with `command="echo 'tunnel-only'",restrict,permitopen="127.0.0.1:5432"` (defense-in-depth — the key can ONLY open the local-loopback PG port).
3. Set GH repo secrets: `NOCTUS_VPS_DEPLOY_KEY` (private half) + `NOCTUS_CACHE_POSTGRES_DSN` = `postgresql://noctus_cache:<PG_PASS>@localhost:5432/noctus_cache`.
4. Update `.github/workflows/embedding-cache-gate.yml` to use `webfactory/ssh-agent` + `ssh -L 5432:127.0.0.1:5432 -fN noctus-vps` before the embedding-gate step.

Why A: scoped per-run · standard pattern · the `command="…",permitopen=…` directive in `authorized_keys` makes the key safe even if leaked (it can only forward the PG port). Same compose change as Phase 2 — no double infrastructure.

### 7d. Routes-not-taken (recorded per dispatch-with-PROJECT-and-notes §4a.3 convention)

| Route | Why not |
|---|---|
| **B (CF Tunnel TCP)** | Requires paid CF plan. Reconsider only if SSH-tunnel pattern becomes untenable. |
| **C (profile-gated port-publish on demand)** | CI orchestration overhead exceeds the value of "no permanent host port" — `127.0.0.1:5432` is already host-loopback only. |
| **D (vps_exec_sql + SQL generation)** | Pgvector BLOB encoding (sqlite-vec → pgvector vector(N) via `struct.unpack`) is already implemented in `cache_deploy_mirror`. Re-implementing in pure SQL-generation duplicates logic without benefit. |
| **E (sidecar container)** | Image build/maintenance + cold-start latency in CI > value vs. F.2's one-time venv. |
| **F.1 (docker bridge IP)** | Bridge IP changes on `docker network` recreate. Not durable. |
| **F.3 (sidecar on noctus-net)** | Subset of E; same trade-offs. |

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
| 2026-05-26 | §7 expanded — VPS env audit recorded + 6-route trade-off table + recommended sequence (Phase 2 = Route F.2 · Phase 3 = Route A). Awaits user go/no-go before execution. | architect (tech-lead) |
| 2026-05-26 | User accepted recommendation. **Phase 2 PARTIAL**: compose change (host-loopback `127.0.0.1:5432:5432`) landed on VPS + dev; cache-pg recreated + healthy + port published; SSH tunnel + psycopg2 connection end-to-end verified; refinement applied (mirror runs from LOCAL via tunnel — same compose change, no VPS venv install needed); **keeper-patterns mirror SUCCESS (132 rows live in prod cache)**. Fixed-in-flight: `cache_deploy_mirror._TABLE_MAP` had plural `agent_contexts` / `auto_improvements`; actual schemas are singular. 4 caches (agent-context · auto-improvement · kb-embeddings · code-embeddings) BLOCKED on deeper schema drift between `cache_deploy_mirror`'s assumed shape and real local SQLite. Surface note filed: `proposals/architect-inline-20260526-183103-surface-cache-deploy-mirror-schema-drift.md` (Routes X/Y/Z for tech-lead). Phase 3 prep proceeds. | architect (tech-lead) |
