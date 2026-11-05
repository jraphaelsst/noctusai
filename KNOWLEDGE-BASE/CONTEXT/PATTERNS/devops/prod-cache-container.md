# prod-cache-container — pgvector/pgvector:pg16 in the prod fleet

> **Scope**: prod-only backing service for the keeper-mirror cache backend.
> Dev uses local SQLite (zero-cost, per-user, regenerable). This doc covers
> the PROD container that remote agents hit. → `KB § PATTERNS/common/
> cache-backend-portability` for the full migration roadmap.

## Why pgvector/pgvector:pg16

| Alternative | Why rejected |
|---|---|
| `postgres:16` + manual extension | Requires `CREATE EXTENSION vector` as superuser on first boot — fragile, error-prone, adds an init-script seam. |
| `postgres:16-alpine` + extension | Same gap; Alpine image still needs the build toolchain or a pre-baked extension layer. |
| `pgvector/pgvector:pg16` | Extension pre-baked. `CREATE EXTENSION IF NOT EXISTS vector;` works on first connect with zero extra config. Single-image, no init-script dance. |
| Supabase managed postgres | Right shape for Phase 4 (see roadmap P4.1); over-provisioned for Phase 3 container-only. |

The image is pinned to `:pg16` (not `:latest`) to avoid a surprise Postgres major-version upgrade breaking on-disk data format.

## Profile gating

```
--profile cache    # brings up cache-pg only (no WAHA)
--profile full     # brings up cache-pg + WAHA + redis
```

No profile flag → only `redis` comes up (always-on). This means a VPS can be deployed incrementally: Redis first, WAHA when a WhatsApp number is provisioned, cache-pg when Phase 3 consumer wiring lands (roadmap P3.1–P3.4).

The `waha` service also gains a `full` profile in this commit so `--profile full` is coherent (all optional services up).

## Volume

```yaml
cache_pg_data:
  name: noctus-cache-pg-data
```

Named volume (not anonymous) so `noctus.vps.*` tools have a stable handle. Anonymous volumes get GC'd on `docker compose down --volumes`; a named volume survives. The noc VPS disk-monitor and sanitization runbook reference named volumes by exact name.

## Network reachability

`cache-pg` is on `noctus-net` with alias `noctus-cache-pg`. In-fleet consumers reach it at:

```
postgresql://<user>:<pass>@noctus-cache-pg:5432/<db>
```

No host port is published. The container is **NOT reachable from outside the noctus-net fabric**. This is intentional — keeper-mirror caches contain no user data, but Postgres on a public port is an attack surface even with auth.

If a direct VPS shell connection is needed for ad-hoc inspection:
```bash
docker exec -it noctus-cache-pg psql -U noctus_cache -d noctus_cache
```

## Credentials + .env.fleet

All credentials come from `.env.fleet` on the VPS (gitignored, secrets-bearing). Required vars:

| Var | Default | Notes |
|---|---|---|
| `NOCTUS_CACHE_PG_DB` | `noctus_cache` | DB name |
| `NOCTUS_CACHE_PG_USER` | `noctus_cache` | PG user |
| `NOCTUS_CACHE_PG_PASSWORD` | *required* | `?:` syntax → compose aborts if unset |

`NOCTUS_CACHE_PG_PASSWORD` uses Docker Compose's `${VAR:?error}` syntax — the compose `config` validation will fail fast (at deploy time, not at runtime) if the var is missing.

The DSN `NOCTUS_CACHE_POSTGRES_DSN` is documented but not consumed by the container itself; it is the env var that `PostgresCacheBackend` (roadmap P3.1) will read on the product side.

## Healthcheck

```yaml
test: ["CMD-SHELL", "pg_isready -U ${NOCTUS_CACHE_PG_USER:-noctus_cache} -d ${NOCTUS_CACHE_PG_DB:-noctus_cache}"]
interval: 30s
timeout: 5s
retries: 3
start_period: 30s
```

`start_period: 30s` gives Postgres time to initialise the data dir on a fresh volume before the health probe starts counting retries. Without this, the first `pg_isready` fires before `postgres` has written `pg_hba.conf` and the container enters an unhealthy restart loop.

## Backup

**Posture (stated 2026-11-05): no backup, by design — RPO unbounded, accepted because nothing here is irreplaceable.** Every row in this container is regenerable from git plus the embedding pipeline (no user data at stake), so a lost cache is a cold rebuild via the `--force` flag on each cache module followed by `cache_deploy_mirror`, not a data incident. The cold-rebuild RTO is not yet measured; the quarterly restore drill measures it. Fleet-wide RPO/RTO table, 3-2-1 and the drill procedure → `KB § PATTERNS/devops/sre-craft-canon.md` §5.

If that ever changes (for example the cache starts holding state that cannot be regenerated), the earlier sketch still applies — a nightly dump shipped **off-host**, never left on the VPS:

```
# sketch only — not installed; an on-host-only copy would not meet 3-2-1
0 3 * * * docker exec noctus-cache-pg pg_dump -U noctus_cache noctus_cache \
  | gzip > /backups/noctus_cache_$(date +%F).sql.gz
```

## Composes with

- `KB § PATTERNS/common/cache-auto-freshness.md` — the closed-loop propagation umbrella; remote backend hooks need extension at Phase 3.
- `KB § PATTERNS/common/cache-backend-portability` — full migration roadmap (T1–T5 triggers, Phase 1–5 slice table, decision log).
- `KB § PATTERNS/devops/containerization.md` — house container model; `cache-pg` follows the same expose-not-ports / noctus-net / named-volume discipline.
- `KB § PATTERNS/devops/container-sanitization.md` — `noctus-cache-pg-data` is a **data-bearing named volume**; sanitization runbook §3 requires tech-lead confirmation before removing it.
- `KB § 05-INFRASTRUCTURE.md` — prod fleet overview.
