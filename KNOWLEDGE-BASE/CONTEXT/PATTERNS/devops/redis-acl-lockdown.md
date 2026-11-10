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
| `trip` (off-host watchdog forced command) | derived | `%RW~noctus:breaker:fleet` only | `SETNX GET EXISTS` (+ping/hello/auth). `SETNX` (not `SET`) cannot take EX/XX, so a stolen key can neither **expire nor overwrite** a trip, and has no DEL: it can trip, never re-arm |
| `probe` (read-only host probe, `host-probe.sh`; `--user probe`, password `redis-auth/probe.pass` when present) | derived | `%R~noctus:breaker:fleet` | `EXISTS` (+ping/hello/auth) only: it can learn that the fleet breaker is tripped, never write or delete (distinct from `trip`, which can SETNX) |
| `ops` (`noctus.dev.supabase_breaker`) | derived | `~noctus:breaker:*` | `GET MGET SET DEL RPUSH LTRIM LRANGE LLEN EXISTS TTL PTTL SMEMBERS SADD SREM SISMEMBER SCARD` (LTRIM keeps the audit cap enforced; SADD lists a hand-tripped key in the product's index) + `acl\|log` + `script\|kill function\|kill` (stop a runaway Lua script). **No `SCAN`/`KEYS`.** The only identity that may DEL the fleet key or write the audit list. `status` enumerates through each product's own index SET (below) |

App key families a product user may touch (each is a real code path, listed in `APP_KEY_FAMILIES`): `nai_session:*` (auth sessions) · `noctus:quota:*` · `rt:*` (SSE bus streams) · `llm:*` (LLM cache) · `LIMITS*` (slowapi/limits Lua counters) · `queue:conversation_*` + `conversation:memory:*` (chatbot) · `wa:dedup:*` · `wa:lid_phone:*` · `ratelimit:conversation:*` and `download:cache:*` (social-wiring).

Passwords: one master `REDIS_ACL_MASTER_SECRET` in the fleet `.env.fleet` on the VPS (names-only manifest `env.fleet.keys`); `password(user) = HMAC-SHA256(master, "noctus-redis-acl:v<gen>:<user>")`. `users.acl` carries **sha256 hashes only**; per-service env files (`redis-auth/env/<service>.env`, 0600) carry `REDIS_URL`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_REQUIRE_AUTH=true`. All under the gitignored `redis-auth/` directory beside the fleet compose files (generated on the VPS). Rotate by bumping `REDIS_ACL_GENERATION` (re-render, recreate Redis + products) or replacing the master. Verified behaviourally against a real `redis-server` (`TestLiveRedis`): refusals for unauthenticated/default, fleet-key write/DEL, peer-breaker keys, FLUSHALL/CONFIG/KEYS/SHUTDOWN/ACL/SORT/SCRIPT FLUSH/FUNCTION, unlisted keys; `LIMITS` Lua works under the caller's permissions.

**Breaker index shape (agreed with the breaker branch).** Each product keeps `noctus:breaker:<slug>:index`, a SET of its full breaker key names (`SADD` when it persists a trip, `SREM` on release). It lives under the product's own `%RW~noctus:breaker:<slug>:*`, so it needs no extra grant and one product cannot edit another's. `ops status` = `GET noctus:breaker:fleet` + `SMEMBERS noctus:breaker:<slug>:index` for each live slug + `MGET`. Source names always start `worker:`/`scheduler:`/`gate:`, so `index` cannot collide with a source.

### Limits, said plainly

- **Key names are bearer secrets: sessions are now keyed by `sha256(session_id)`** (`RedisSessionStore._key`; the cookie value is the session id, so a raw `nai_session:<id>` key made every SCAN / `ACL LOG` / dump line a working credential). Dual read: a legacy raw-keyed record is read, atomically `RENAME`d onto the hashed key (TTL kept) and used, so deploying the hash logs nobody out; `delete` clears both forms. Product users still hold `SCAN` (the seed's `flush_prefix` uses it): they see key *names*, which for sessions are now inert hashes. `ops` has no SCAN at all.
- **Cross-product session forging (pre-existing, NOT closed here).** The seed's key families are shared names, so a compromised product user can not only read but **write** `nai_session:<sha256(id)>` and forge a session another product will honour (the record carries org/user/scopes, no MAC). The lockdown removes every non-product actor and protects the breaker; it does not stop product-to-product forging. Fix = a per-product key prefix in the seam or a MAC over the record keyed per deployment: `NOC-REMEDIATE[redis-session-mac]` (marked in `redis_store.py`). Each user already holds `~<slug>:*` for the prefix route.
- **Unbounded product-local keys:** erp-imobiliario's `@cached(key_prefix=…)` can't be bounded from code. It is asleep (no user). If woken it needs a `~erp:*` prefix and a render.
- `KEYS` (blocking) is used by social-wiring's download-cache sweep: `EXTRA_COMMANDS` grants it, `NOC-REMEDIATE[redis-keys-scan]` — switch it to `scan_iter` and drop the exception.
- **Rate limiter now fails closed with auth required.** `resolve_limiter_storage_uri` re-raises any probe failure (WRONGPASS / NOPERM / unreachable) when `REDIS_REQUIRE_AUTH` is on, so a wrong password fails the boot instead of silently running a per-process limiter. Without the flag it still degrades with a warning.
- **EVAL freeze / memory:** products keep only `eval evalsha script|load script|exists`; `ops` holds `script|kill`. Redis runs `--maxmemory 512mb --maxmemory-policy volatile-lru` (only TTL'd keys evict, the breaker keys have none) under a compose `mem_limit: 768m`.
- **Image pin:** `redis-acl` runs `redis:7.4.6-alpine` by digest. CVE-2025-49844 (Lua use-after-free to RCE) and CVE-2025-46818 are fixed in 7.2.11 / 7.4.6 / 8.0.4 / 8.2.2; steps 0 and 2 refuse anything lower, and the product users can run EVAL, so this is not optional.
- **Passwords never in `docker inspect` if you want:** the seam also reads `REDIS_PASSWORD_FILE` (env wins when both are set; an unreadable file raises). The rendered env files use `REDIS_PASSWORD` today.
- **Master hygiene:** `REDIS_ACL_MASTER_SECRET` must be exactly 64 lowercase hex chars (`openssl rand -hex 32`); a `#` value (the shipped example's comment) or any other shape is refused, never adopted. `REDIS_ACL_GENERATION` is digits only; `REDIS_ACL_GENERATION_OVERRIDES=core=2,ops=3` rotates single users. Roster slugs `noctus`, `default`, `ops`, `trip`, `healthcheck` and every key-family head (`wa`, `rt`, `llm`, `queue`, ...) are reserved. Secret files are written 0600 through an O_EXCL|O_NOFOLLOW temp file + rename into 0700 directories.
- ACL changes need a re-render + Redis restart (the aclfile is mounted read-only, loaded at start).

## 4. Rollout (guardian session, owner's live typed consent). Each step names its rollback.

**Deploy tooling is a hard precondition, now in code.** `deploy_image` (deploy, pull AND rollback), `vps.recreate` and `ensure_product_url_roster` add `-f compose.redis-auth.prod.yml` to every compose call whenever that file exists beside the base compose file. For a service the override lists, a missing/empty generated env file, a not-running `noctus-redis-acl`, or an unanswerable probe REFUSES the call (status `error`, container untouched): a recreate can never quietly put a locked product back on the old Redis. Consequence for ordering: **render the env files and start `redis-acl` (steps 1-2) BEFORE the commit carrying the override reaches the VPS checkout**, or every tool recreate of those five products refuses until you do. The only bypass is `deploy_image(redis_auth="off")` (python/CLI, not an MCP flag, recorded in the payload).

**0. Read-only inventory (no change).** (a) `docker exec noctus-core printenv REDIS_URL` (redact) and the root `.env` `REDIS_URL`: **which Redis do the products really use**, `noctus-redis` (fleet infra) or the legacy services-stack `redis` alias? (b) `docker ps --filter name=redis`, `docker network inspect noctus-net` (who is attached). (c) n8n UI > Credentials: any Redis credential? Workflows using the Redis node? (d) **version gate:** `docker exec noctus-redis redis-server --version` is informational for the old Redis, but the NEW image must report `>= 7.4.6` (or >= 8.2.2): anything lower is REFUSED (Lua CVE-2025-49844 / CVE-2025-46818). (e) `docker exec noctus-redis redis-cli DBSIZE` + `ZCARD queue:conversation_due` (chatbot backlog). (f) **`legacy-permutas-celery`** (`deploy/legacy/compose.legacy.yml`: `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`, db index N): `docker exec legacy-permutas-celery printenv CELERY_BROKER_URL` (redact) + `docker exec legacy-permutas redis-cli` reachability: which Redis host does the broker name? Stop if anything is unexpected.

**1. Secrets + net.** Add `REDIS_ACL_MASTER_SECRET=$(openssl rand -hex 32)` to the fleet `.env.fleet`; `docker network create --internal noctus-data`; **verify `docker network inspect -f '{{.Internal}}' noctus-data` prints `true`** (a non-internal net would give Redis a default route; recreate it); on the VPS checkout `python mcp/noctusai/cli.py --redis-acl render --redis-acl-write`; `--redis-acl check` must say `in_sync`. Rollback: delete the generated `redis-auth/` directory, `docker network rm noctus-data`, drop the env line. No runtime effect.

**2. ACL'd Redis alongside.** `docker compose -f compose.infra.prod.yml --profile redis-acl up -d redis-acl`. Verify: (i) container healthy; (ii) **version:** `docker exec noctus-redis-acl redis-server --version` shows `v=7.4.6` or higher, otherwise `rm -sf redis-acl` and stop; (iii) `docker network inspect -f '{{.Internal}}' noctus-data` is `true` and `docker inspect noctus-redis-acl --format '{{json .NetworkSettings.Networks}}'` lists only `noctus-data`; (iv) `REDISCLI_AUTH=$(cat redis-auth/ops.pass) docker exec -e REDISCLI_AUTH noctus-redis-acl redis-cli --user ops --no-auth-warning ping`; an unauthenticated `redis-cli -h noctus-redis-acl ping` from a throwaway container on `noctus-data` returns `NOAUTH`. Rollback: `docker compose -f compose.infra.prod.yml --profile redis-acl rm -sf redis-acl` (old Redis untouched; volume `redis_acl_data` kept).

**3. Land the tooling + override on the VPS** (`deploy_pull` of this commit) **after** steps 1-2. Check: `deploy_image` dry-run for each of the five products shows no `error`; `ls redis-auth/env/` has one file per roster service. Nothing moves yet (recreates have not happened). Rollback: `git` back to the previous revision via `deploy_pull` to the prior sha; the override file disappears and so does the guard.

**4. Roll products one at a time**, least critical first, `core` last (it serves SSO): `seed`, `monica`, `agents`, `social-wiring`, `core`. Use `deploy_image` (re-deploys the same image; the override is added for you) or `vps.recreate`. Verify per service: (i) `/api/health` 200 and container healthy; (ii) logs contain `Rate limiter using Redis backend`; with `REDIS_REQUIRE_AUTH=true` a wrong password now fails the boot instead of degrading, so a healthy container is evidence; (iii) an SSO login round trip for that product (session written to `nai_session:<sha256>`); (iv) a rate-limited route returns 429 on a burst; (v) `ops` `ACL LOG` shows no `reason=command/key` denials for that user (a denial means a key family/command missing from `APP_KEY_FAMILIES`: fix the render, not the ACL by hand); (vi) `docker inspect <c> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c '^REDIS_USERNAME='` = 1. **Rollback per service:** with the guard in place a tool recreate re-adds the override, so roll back by hand: `docker compose -f docker-compose.prod.yml up -d --no-deps <svc>` (no second `-f`; the service returns to the old Redis, and its sessions on the new Redis are simply gone: users **log in again**). For a durable rollback also `mv compose.redis-auth.prod.yml` aside (otherwise the next tool deploy re-locks it).

**5. Breaker switch-over (same window as step 4 for any product that already runs the breaker).** See §5. The breaker is unlanded today, so there are no breaker keys to migrate; land it **after** step 4 and nothing needs copying.

**6. Soak** (>= 24 h, one nightly job cycle). Watch `ACL LOG`, product logs for `WRONGPASS`/`NOPERM`/`breaker: cannot read the breaker keys from Redis`. Rollback: as step 4.

**7. Scrub the old Redis of live credentials** (after `core` is cut over and soaked): every `nai_session:*` key on the OLD Redis is a bearer credential for a session that no longer exists on the new one, and is readable by anything on `noctus-net`. `docker exec noctus-redis redis-cli --scan --pattern 'nai_session:*' | xargs -r -n 200 docker exec -i noctus-redis redis-cli UNLINK` (a legacy raw-keyed record is a usable cookie; the hashed ones are inert). Rollback text, honestly: there is nothing to roll back to: **sessions start empty**; if you point a product back at the old Redis, its users log in again.

**8. Retire the unauthenticated Redises. BLOCKED until `legacy-permutas-celery` has a home.** It uses the shared Redis as a Celery broker (db index N, keys `celery`, `_kombu.*`, `unacked*`, `celery-task-meta-*`, plus pub/sub channels, which a default ACL user cannot use). Two acceptable options, choose after step 0(f): (a) **private net (preferred, no ACL guesswork):** keep the old Redis alive but off `noctus-net`: a new internal `noctus-legacy-data` net joined only by that Redis, `legacy` and `legacy-celery`; rollback = rejoin `noctus-net`. (b) **an ACL user** `legacy-permutas` with `~celery* ~_kombu.* ~unacked* ~celery-task-meta-* &*` and the product command set, tested against a real kombu worker first (kombu's exact command set is NOT verified here). Only then: stop `noctus-redis` for everything else (keep the `redis_data` volume 7 days; rollback `start`). The legacy services-stack `redis` (alias `redis`, `redis:latest`, no auth, `deploy/services/compose.services.yml`): n8n has no `QUEUE_BULL_REDIS_*` env and stores in SQLite, WAHA Core has no Redis env, both only `depends_on` it for start order; after step 0(c) confirms no n8n Redis credential, remove the `depends_on: redis` entries and the service (or move it to the private net in (a)).

**Downtime.** Per product: one container recreate (~20-40 s, `start_period: 20s`); APIs of other products unaffected. The new Redis starts **empty**: every user of the moved product is logged out once (sessions are not copied; the AOF then persists on the new volume), in-flight chatbot buffers and `conversation:memory:*` of that product are dropped (cut over with `ZCARD queue:conversation_due` at 0, step 0(e)), rate-limit counters reset (harmless). A warm copy (RDB `SAVE` + load before first start) is possible but not scripted; the owner's call, not needed for correctness.

## 5. Same-window changes on the unlanded breaker branches

Both must pass credentials and target `noctus-redis-acl`, or they break the moment step 2 lands.

**`feat/supabase-request-telemetry` — the `breaker-trip.sh` forced command (deploy/watchdog/)** (the forced command; runs as the VPS deploy user). Change the default container and authenticate as `trip`, password from a root-owned file, **never argv**:
```bash
REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-redis-acl}"
TRIP_PASS_FILE="${NOCTUS_REDIS_TRIP_PASS_FILE:-/opt/noctus/noctusai/deploy/fleet/redis-auth/trip.pass}"
[[ -r "$TRIP_PASS_FILE" ]] || { echo '{"error":"trip credential unreadable"}' >&2; exit 3; }
export REDISCLI_AUTH; REDISCLI_AUTH="$(cat "$TRIP_PASS_FILE")"
rcli() { timeout 15 docker exec -e REDISCLI_AUTH "$REDIS_CONTAINER" redis-cli --no-auth-warning --user trip "$@" 2>/dev/null; }
out="$(rcli SETNX "$KEY" "$canon")"             # was: docker exec "$REDIS_CONTAINER" redis-cli SET ... NX
exists="$(rcli EXISTS "$KEY")"                  # was: docker exec ... redis-cli EXISTS
# SETNX replies 1 (tripped now) | 0 (an earlier trip stands); the old `OK` / empty-nil mapping becomes 1 / 0.
```
(`docker exec -e REDISCLI_AUTH` with no value forwards the host env var, so the password is never on a command line.) The file is `0600` and owned by the deploy user; the forced-command key's `restrict` is unchanged. `trip` holds `SETNX`/`GET`/`EXISTS` on the fleet key and nothing else (no `SET`, so no EX/XX/overwrite, no DEL); the script's validation stays as it is and the reply mapping changes as noted.

**`feat/supabase-breaker` — the `supabase_breaker` toolkit module**, class `VpsRedisOps`: default `container="noctus-redis-acl"`; `_cli` builds the remote command with the ops credential read **on the VPS** (never sent over SSH argv):
```python
cmd = ("REDISCLI_AUTH=\"$(cat /opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass)\" "
       f"docker exec -e REDISCLI_AUTH {shlex.quote(self._container)} redis-cli --no-auth-warning --user ops "
       + " ".join(shlex.quote(a) for a in args))
```
and extend the failure test to `"NOAUTH" in out or "WRONGPASS" in out or "NOPERM" in out`. `ops` has **no `scan`**: replace `scan()` with `smembers` of each live slug's `noctus:breaker:<slug>:index` (slugs from `build-scope.txt`) plus the fleet key, and make the product-side store maintain that index (`SADD` in the same step that persists a trip, `SREM` on release); each product also keeps `noctus:breaker:<slug>:audit` (RPUSH + LTRIM) in the same namespace. `get`, `mget`, `set`, `del`, `rpush`, `smembers`, `srem` are inside the `ops` grant (`rearm` = `del` + `srem` from the index + `rpush noctus:breaker:audit`). Also update the `redis-cli` references in `supabase-request-breaker.md` / `prod-watchdog.md` (`noctus-redis` → `noctus-redis-acl`). Products need **no** code change: `make_breaker_store` goes through the seam, which reads `REDIS_USERNAME`/`REDIS_PASSWORD` (the per-service env file) and, with `REDIS_REQUIRE_AUTH=true`, refuses to connect unauthenticated.

## 6. Things this does not (and could not) verify

The live `REDIS_URL` each product resolves; n8n's stored credentials/workflows; WAHA's actual Redis use (config shows none); the `legacy-permutas-celery` broker host and kombu's exact command/channel needs (hence step 8 prefers a private net); the `redis-acl` container hardening (`user: redis`, `cap_drop ALL`, `read_only`) against the real image (no Docker daemon in the authoring environment; the digest and its 7.4.6 tag were read from the registry, the ACL behaviour tests ran on a local 7.0.12 `redis-server`, which lacks `client|setinfo`, a 7.2+ command that products receive through `+@all`); the compose override's behaviour on the VPS's compose version (verified locally: `env_file` appends, `networks` unions).

Composes with: `redis-auth-seam.md` (client side) · `containerization.md` · `dev-prod-parity.md` · `prod-watchdog.md` · `deploy-config-contract.md` · `product-lockfile-and-slug-drift.md` (derive, don't hand-keep).
