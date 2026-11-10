# Redis ACL lockdown — authenticated prod Redis on a private data network

> `noctus.dev.redis_acl` · `cli.py --redis-acl` · `deploy/fleet/compose.infra.prod.yml` (`redis-acl`) · `deploy/fleet/compose.redis-auth.prod.yml` · `mcp/noctusai/tests/test_redis_acl.py`

## 1. Why (security review F3, 2026-11-10)

Prod `noctus-redis` runs `redis-server --appendonly yes`: no `requirepass`, no ACL, on `noctus-net`, a network every container shares — n8n (`n8nio/n8n:latest`, public UI, built-in Redis node + Code node), WAHA, cloudflared, every product. It holds SSO sessions, rate-limit counters, quota, the chatbot buffer and is about to hold the **fleet breaker** (`noctus:breaker:fleet`: while present every product's background workers stop). A foothold anywhere on that network could SET the key (fleet-wide DoS) or DEL a trip (silently disarm a runaway breaker), and read every session.

The seed already supports credentials (`KB § PATTERNS/backend/redis-auth-seam.md`: `REDIS_USERNAME`/`REDIS_PASSWORD`, `REDIS_REQUIRE_AUTH`); this doc is the server side.

## 2. Topology

```
BEFORE                                         AFTER
noctus-net (shared, egress)                    noctus-net (shared, egress)
  core agents monica seed social-wiring          core agents monica seed social-wiring (+ tunnel, WAHA, n8n)
  cloudflared  waha  n8n                                |
  noctus-redis   (no auth)  <-- all reach it    noctus-data (--internal: no egress, no publish)
  redis (legacy services stack, no auth)          core agents monica seed social-wiring  +  noctus-redis-acl
```

- `noctus-redis-acl` (service `redis-acl`, profile-gated) is on **`noctus-data` only**. Products join both nets (they need `noctus-net` for the tunnel, WAHA, Supabase egress). n8n, WAHA, cloudflared never join `noctus-data`.
- The old `noctus-redis` stays up, untouched, until every product has moved (rollback target), then is retired.
- Redis is reached **only by container name over `noctus-data`**; nothing is published to the host. Ops reach it via `docker exec` on the host (the forced-command key / the toolkit's SSH).

## 3. ACL model (rendered by `noctus.dev.redis_acl`, never hand-written)

| User | Auth | Keys | Commands |
|---|---|---|---|
| `default` | **off** | — | — |
| `healthcheck` | nopass | none | `+ping` only (liveness reveals nothing) |
| `<service>` (one per live product: roster = compose services loading the root `.env` ∩ `build-scope.txt`) | derived password | the app key families below, `~<slug>:*` (own future namespace), `%RW~noctus:breaker:<slug>:*`, **`%R~noctus:breaker:fleet`** (read-only) | `+@all -@dangerous -@admin -@scripting +eval +evalsha +script\|load +script\|exists` (+`keys` for social-wiring only, declared exception) |
| `trip` (off-host watchdog forced command) | derived | `%RW~noctus:breaker:fleet` only | `SET GET EXISTS` (+ping/hello/auth). **Cannot DEL**: a stolen trip key can trip, never re-arm |
| `ops` (`noctus.dev.supabase_breaker`) | derived | `~noctus:breaker:*` | `GET MGET SET DEL RPUSH LRANGE LLEN EXISTS TTL PTTL SCAN` + `acl\|log`. The **only** identity that may DEL the fleet key or write the audit list |

App key families a product user may touch (each is a real code path, listed in `APP_KEY_FAMILIES`): `nai_session:*` (auth sessions) · `noctus:quota:*` · `rt:*` (SSE bus streams) · `llm:*` (LLM cache) · `LIMITS*` (slowapi/limits Lua counters) · `queue:conversation_*` + `conversation:memory:*` (chatbot) · `wa:dedup:*` · `wa:lid_phone:*` · `ratelimit:conversation:*` and `download:cache:*` (social-wiring).

Passwords: one master `REDIS_ACL_MASTER_SECRET` in the fleet `.env.fleet` on the VPS (names-only manifest `env.fleet.keys`); `password(user) = HMAC-SHA256(master, "noctus-redis-acl:v<gen>:<user>")`. `users.acl` carries **sha256 hashes only**; per-service env files (`redis-auth/env/<service>.env`, 0600) carry `REDIS_URL`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_REQUIRE_AUTH=true`. All under gitignored `deploy/fleet/redis-auth/`. Rotate by bumping `REDIS_ACL_GENERATION` (re-render, recreate Redis + products) or replacing the master. Verified behaviourally against a real `redis-server` (`TestLiveRedis`): refusals for unauthenticated/default, fleet-key write/DEL, peer-breaker keys, FLUSHALL/CONFIG/KEYS/SHUTDOWN/ACL/SORT/SCRIPT FLUSH/FUNCTION, unlisted keys; `LIMITS` Lua works under the caller's permissions.

### Limits, said plainly

- **Per-product isolation is bounded only for breaker keys.** The seed's key families are shared names across products (`nai_session:*`, `queue:conversation_*` ...), so a compromised product can read another's sessions. Closing that needs a prefix migration (`<slug>:` in front of every family, in the seam); each user already has `~<slug>:*` waiting. Out of scope here; the lockdown's gain is removing every *non-product* actor and protecting the breaker.
- **`SCAN` returns key names regardless of key patterns** (Redis ACLs do not filter it). Names leak, values do not.
- **Unbounded product-local keys:** erp-imobiliario's `@cached(key_prefix=…)` can't be bounded from code. It is asleep (no user). If woken it needs a `~erp:*` prefix and a render.
- `KEYS` (blocking) is used by social-wiring's download-cache sweep: `EXTRA_COMMANDS` grants it, `NOC-REMEDIATE[redis-keys-scan]` — switch it to `scan_iter` and drop the exception.
- ACL changes need a re-render + Redis restart (the aclfile is mounted read-only, loaded at start).

## 4. Rollout (guardian session, owner's live typed consent). Each step names its rollback.

**0. Read-only inventory (no change).** (a) `docker exec noctus-core printenv REDIS_URL` (redact) and the root `.env` `REDIS_URL`: **which Redis do the products really use** — `noctus-redis` (fleet infra) or the legacy services-stack `redis` alias? (b) `docker ps --filter name=redis`, `docker network inspect noctus-net` (who is attached). (c) n8n UI → Credentials: any Redis credential? Workflows using the Redis node? (d) `docker exec noctus-redis redis-server --version` (>=7.0 required for key-permission selectors). (e) `docker exec noctus-redis redis-cli DBSIZE` + `ZCARD queue:conversation_due` (chatbot backlog). Stop if (a) shows something unexpected.

**1. Secrets + net.** Add `REDIS_ACL_MASTER_SECRET=$(openssl rand -hex 32)` to the fleet `.env.fleet`; `docker network create --internal noctus-data`; on the VPS checkout `python mcp/noctusai/cli.py --redis-acl render --redis-acl-write`; `--redis-acl check` must say `in_sync`. Rollback: delete `deploy/fleet/redis-auth/`, `docker network rm noctus-data`, drop the env line. No runtime effect.

**2. ACL'd Redis alongside.** `docker compose -f compose.infra.prod.yml --profile redis-acl up -d redis-acl`. Verify: container healthy; `REDISCLI_AUTH=$(cat redis-auth/ops.pass) docker exec -e REDISCLI_AUTH noctus-redis-acl redis-cli --user ops --no-auth-warning ping`; unauthenticated `redis-cli -h noctus-redis-acl ping` from a throwaway container on `noctus-data` returns `NOAUTH`. Rollback: `docker compose -f compose.infra.prod.yml --profile redis-acl rm -sf redis-acl` (old Redis untouched; volume `redis_acl_data` kept).

**3. Roll products one at a time**, least critical first, `core` last (it serves SSO): `seed`, `monica`, `agents`, `social-wiring`, `core`. For each: `docker compose -f docker-compose.prod.yml -f compose.redis-auth.prod.yml up -d --no-deps <service>`. Verify per service: (i) `/api/health` 200 and container healthy; (ii) logs contain `Rate limiter using Redis backend` — a wrong password makes the limiter **fall back to in-memory with only a warning** (ping failure is swallowed; only a *missing* credential is fail-closed via `REDIS_REQUIRE_AUTH`), so this grep is the real check; (iii) an SSO login round trip for that product (session written to `nai_session:*`); (iv) a rate-limited route returns 429 on burst; (v) `ops` `ACL LOG` shows no `reason=command/key` denials for that user — a denial means a key family/command missing from `APP_KEY_FAMILIES` (fix the render, not the ACL by hand); (vi) `docker inspect <c> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c '^REDIS_USERNAME='` = 1 (the override is applied). Rollback per service: re-run the same `up -d --no-deps <service>` **without** the second `-f` (env_file + network drop away; it returns to the old Redis).

**4. Breaker switch-over (same window as step 3 for any product that already runs the breaker).** See §5. The breaker is unlanded today, so there are no breaker keys to migrate; land it **after** step 3 and nothing needs copying.

**5. Soak** (>= 24 h, one nightly job cycle). Watch `ACL LOG`, product logs for `WRONGPASS`/`NOPERM`/`breaker: cannot read the breaker keys from Redis`. Rollback: as step 3, per service.

**6. Make the override permanent before retiring the old Redis.** `deploy_image`/`deploy_pull`-driven recreates run `docker compose -f deploy/fleet/docker-compose.prod.yml` **only** — they drop the override and would silently return a product to the old Redis (unauthenticated, still up). Until the deploy tool passes the override (`deploy_image` takes one `compose_file`; either fold the override's per-service `env_file` + `networks` into `docker-compose.prod.yml`, or teach `_compose` a second `-f`), do not proceed. Verify with check (vi) after the next real deploy.

**7. Retire the unauthenticated Redises.** Stop `noctus-redis` (`docker compose -f compose.infra.prod.yml stop redis`; keep the `redis_data` volume 7 days), remove its service in a follow-up commit. The legacy services-stack `redis` (alias `redis`, `redis:latest`, no auth, `deploy/services/compose.services.yml`): n8n has no `QUEUE_BULL_REDIS_*`/`N8N_` Redis env and stores in SQLite, WAHA Core has no Redis env, both only `depends_on` it for start order. After step 0(c) confirms no n8n Redis credential, remove the `depends_on: redis` entries and the service (or move it to a private net). Rollback: `docker compose ... start redis` (data volume kept).

**Downtime.** Per product: one container recreate (~20-40 s, `start_period: 20s`); APIs of other products unaffected. The new Redis starts **empty**: every user of the moved product is logged out once (SSO sessions are not copied; the AOF then persists on the new volume), in-flight chatbot buffers and `conversation:memory:*` of that product are dropped (cut over with `ZCARD queue:conversation_due` at 0 — step 0(e)), rate-limit counters reset (harmless). A warm copy (RDB `SAVE` + load before first start) is possible but not scripted; the owner's call, not needed for correctness.

## 5. Same-window changes on the unlanded breaker branches

Both must pass credentials and target `noctus-redis-acl`, or they break the moment step 2 lands.

**`feat/supabase-request-telemetry` — the `breaker-trip.sh` forced command (deploy/watchdog/)** (the forced command; runs as the VPS deploy user). Change the default container and authenticate as `trip`, password from a root-owned file, **never argv**:
```bash
REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-redis-acl}"
TRIP_PASS_FILE="${NOCTUS_REDIS_TRIP_PASS_FILE:-/opt/noctus/noctusai/deploy/fleet/redis-auth/trip.pass}"
[[ -r "$TRIP_PASS_FILE" ]] || { echo '{"error":"trip credential unreadable"}' >&2; exit 3; }
export REDISCLI_AUTH; REDISCLI_AUTH="$(cat "$TRIP_PASS_FILE")"
rcli() { timeout 15 docker exec -e REDISCLI_AUTH "$REDIS_CONTAINER" redis-cli --no-auth-warning --user trip "$@" 2>/dev/null; }
out="$(rcli SET "$KEY" "$canon" NX)"            # was: docker exec "$REDIS_CONTAINER" redis-cli SET ...
exists="$(rcli EXISTS "$KEY")"                  # was: docker exec ... redis-cli EXISTS
```
(`docker exec -e REDISCLI_AUTH` with no value forwards the host env var, so the password is never on a command line.) The file is `0600` and owned by the deploy user; the forced-command key's `restrict` is unchanged. `trip` can SET/EXISTS the fleet key and nothing else; the script's validation + `NX` semantics stay as they are.

**`feat/supabase-breaker` — the `supabase_breaker` toolkit module**, class `VpsRedisOps`: default `container="noctus-redis-acl"`; `_cli` builds the remote command with the ops credential read **on the VPS** (never sent over SSH argv):
```python
cmd = ("REDISCLI_AUTH=\"$(cat /opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass)\" "
       f"docker exec -e REDISCLI_AUTH {shlex.quote(self._container)} redis-cli --no-auth-warning --user ops "
       + " ".join(shlex.quote(a) for a in args))
```
and extend the failure test to `"NOAUTH" in out or "WRONGPASS" in out or "NOPERM" in out`. `scan` (`--scan --pattern`), `get`, `set`, `del`, `rpush` are all inside the `ops` grant (`rearm` = `del` + `rpush noctus:breaker:audit`). Also update the `redis-cli` references in `supabase-request-breaker.md` / `prod-watchdog.md` (`noctus-redis` → `noctus-redis-acl`). Products need **no** code change: `make_breaker_store` goes through the seam, which reads `REDIS_USERNAME`/`REDIS_PASSWORD` (the per-service env file) and, with `REDIS_REQUIRE_AUTH=true`, refuses to connect unauthenticated.

## 6. Things this does not (and could not) verify

See the delivery note; chiefly: the live `REDIS_URL` each product resolves, n8n's stored credentials/workflows, WAHA's actual Redis use (config shows none), the actual `redis:7-alpine` patch version behind the tag (image should be digest-pinned: `sre-craft-canon.md` §6), and `deploy_image`'s two-file behaviour.

Composes with: `redis-auth-seam.md` (client side) · `containerization.md` · `dev-prod-parity.md` · `prod-watchdog.md` · `deploy-config-contract.md` · `product-lockfile-and-slug-drift.md` (derive, don't hand-keep).
