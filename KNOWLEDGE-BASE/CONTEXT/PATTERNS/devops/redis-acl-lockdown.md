# Redis ACL lockdown — authenticated prod Redis on a private data network

> `noctus.dev.redis_acl` · `cli.py --redis-acl` · `deploy/fleet/compose.infra.prod.yml` (`redis-acl`, `breaker-redis`) · `mcp/noctusai/tests/test_redis_acl.py`

## 1. Why (security review F3, 2026-11-10)

Prod `noctus-redis` runs `redis-server --appendonly yes`: no `requirepass`, no ACL, on `noctus-net`, a network every container shares — n8n (`n8nio/n8n:latest`, public UI, built-in Redis node + Code node), WAHA, cloudflared, every product. It holds SSO sessions, rate-limit counters, quota, the chatbot buffer and is about to hold the **fleet breaker** (`noctus:breaker:fleet`: while present every product's background workers stop). A foothold anywhere on that network could SET the key (fleet-wide DoS) or DEL a trip (silently disarm a runaway breaker), and read every session.

The seed already supports credentials (`KB § PATTERNS/backend/redis-auth-seam.md`: `REDIS_USERNAME`/`REDIS_PASSWORD`, `REDIS_REQUIRE_AUTH`, `REDIS_PASSWORD_FILE`); this doc is the server side.

## 2. Topology

```
BEFORE                                         AFTER
noctus-net (shared, egress)                    noctus-net (shared, egress)
  core agents monica seed social-wiring          core agents monica seed social-wiring (+ tunnel, WAHA, n8n)
  cloudflared  waha  n8n                                |
  noctus-redis   (no auth)  <-- all reach it    noctus-data (--internal: no egress, no publish)
  redis (legacy services stack, no auth)          the five products  +  noctus-redis-acl (app data)
                                                                      +  noctus-breaker-redis (breaker keys ONLY)
```

- **Two instances, on purpose (round 3).** `noctus-redis-acl` holds app data (`volatile-lru`, 512mb, EVAL allowed for `limits`). `noctus-breaker-redis` holds **only** `noctus:breaker:*` (`--maxmemory 64mb noeviction`, AOF on, **no scripting for any user**). With one shared instance a runaway that fills memory made `SETNX noctus:breaker:fleet` fail with OOM exactly during the runaway, and a hung Lua script on the app instance froze the breaker too. They share nothing now.
- Both are on **`noctus-data` only** (profile-gated `redis-acl`); products join both nets; n8n, WAHA, cloudflared never join `noctus-data`. The old `noctus-redis` stays up, untouched, until the end (rollback target).
- Redis is reached **only by container name over `noctus-data`**; nothing is published. Ops reach it via `docker exec` on the host.
- Memory sizing: app `maxmemory 512mb` / `mem_limit 1g`, breaker `64mb` / `192m` — a `BGREWRITEAOF` fork can copy-on-write up to the whole dataset, so a tight limit would OOM-kill Redis exactly when it is busiest. **Alert** on `used_memory` > 80% of `maxmemory` (or container memory > 80% of `mem_limit`, interim signal `noctus.vps.stats`) for BOTH instances: `NOC-REMEDIATE[redis-memory-alert]` (compose comment) — the probe user deliberately has no `INFO`.

## 3. ACL model (rendered by `noctus.dev.redis_acl`, never hand-written)

**App Redis (`noctus-redis-acl`, `users.acl`)**

| User | Keys | Commands |
|---|---|---|
| `default` | — | **off** |
| `healthcheck` (nopass) | none | `+ping` only |
| `<service>` (one per live product: compose services loading the root `.env` ∩ `build-scope.txt`) | the app key families below + `~<slug>:*` (own future namespace). **No breaker keys.** | `+@all -@dangerous -@admin -@scripting +eval +evalsha +script\|load +script\|exists` (+`keys` for social-wiring only, declared exception) |
| `ops` | none | `acl\|log`, `acl\|whoami`, `ping` (verification after a cutover; zero key access) |

**Breaker Redis (`noctus-breaker-redis`, `breaker-users.acl`)** — no user has any scripting command.

| User | Keys | Commands |
|---|---|---|
| `default` / `healthcheck` | as above | off / `+ping` |
| `<service>` (its own breaker password, distinct from its app password) | **RW** `noctus:breaker:<slug>:{worker:*,scheduler:*,gate:*,audit,index}`; **read-only** `noctus:breaker:<slug>:rearm:*` and `noctus:breaker:fleet` | `GET MGET SET DEL EXISTS TTL PTTL SADD SREM SMEMBERS SISMEMBER SCARD RPUSH LTRIM LRANGE LLEN PING` |
| `trip` (off-host watchdog forced command) | `%RW~noctus:breaker:fleet` only | `SETNX GET EXISTS`. `SETNX` (not `SET`) cannot take EX/XX: a stolen key can neither **expire nor overwrite** a trip, and has no DEL: it can trip, never re-arm |
| `probe` (read-only host probe) | `%R~noctus:breaker:fleet` | `EXISTS` (+ping/hello/auth) only |
| `ops` (`noctus.dev.supabase_breaker`) | `~noctus:breaker:*` | `GET MGET SET DEL RPUSH LTRIM LRANGE LLEN EXISTS TTL PTTL SMEMBERS SADD SREM SISMEMBER SCARD` + `acl\|log`. **No `SCAN`/`KEYS`.** The **only** identity that writes `rearm:*` markers, DELs the fleet key or writes the global audit list |

App key families a product may touch (`APP_KEY_FAMILIES`, each traced to code): `nai_session:*` · `noctus:quota:*` · `rt:*` · `llm:*` · `LIMITS*` · `queue:conversation_*` + `conversation:memory:*` · `wa:dedup:*` · `wa:lid_phone:*` · `ratelimit:conversation:*` · `download:cache:*`.

**Breaker index shape (agreed with the breaker branch).** Each product keeps `noctus:breaker:<slug>:index`, a SET of its full breaker key names (`SADD` when it persists a trip, `SREM` on release) and `noctus:breaker:<slug>:audit` (RPUSH + LTRIM), all inside its own namespace. `ops status` = `GET noctus:breaker:fleet` + `SMEMBERS` of each live slug's index + `MGET`. Source names always start `worker:`/`scheduler:`/`gate:`, so `index`/`audit`/`rearm:` cannot collide with a source.

**Passwords.** One master `REDIS_ACL_MASTER_SECRET` in the fleet `.env.fleet` on the VPS (names-only manifest `env.fleet.keys`); `password(user) = HMAC-SHA256(master, "noctus-redis-acl:v<gen>:<user>")`. Both aclfiles carry **sha256 hashes only**. Everything generated (aclfiles, per-service env files, `ops.pass`/`ops-app.pass`/`trip.pass`/`probe.pass`, and the override) lives on the VPS in the gitignored `redis-auth/` directory beside the fleet compose files and the gitignored `compose.redis-auth.prod.yml`; **nothing generated is committed** (round 3: a committed override armed the deploy guard on a routine promote before the rollout steps had run).

The master must be exactly 64 lowercase hex chars (`openssl rand -hex 32`); a `#` value (the shipped example's comment) or any other shape is refused, never adopted. `REDIS_ACL_GENERATION` is digits only; `REDIS_ACL_GENERATION_OVERRIDES=core=2,ops=3` rotates single users. Roster slugs `noctus`, `default`, `ops`, `trip`, `probe`, `healthcheck` and every key-family head (`wa`, `rt`, `llm`, `queue`, ...) are reserved. Secret files are written 0600 through an O_EXCL|O_NOFOLLOW temp file + rename into 0700 directories.

**Per-service environment** (rendered into `redis-auth/env/<service>.env`; the only names the breaker branch needs):

| App connection (seam, unchanged) | Breaker connection (new) |
|---|---|
| `REDIS_URL=redis://noctus-redis-acl:6379/0` | `NOCTUS_BREAKER_REDIS_URL=redis://noctus-breaker-redis:6379/0` |
| `REDIS_USERNAME=<slug>` | `NOCTUS_BREAKER_REDIS_USERNAME=<slug>` |
| `REDIS_PASSWORD=<derived>` | `NOCTUS_BREAKER_REDIS_PASSWORD=<derived, distinct>` |
| `REDIS_REQUIRE_AUTH=true` | (the breaker passes the credentials to `make_redis_client` explicitly) |

### Limits, said plainly

- **Key names are bearer secrets: sessions are keyed by `sha256(session_id)`** (`RedisSessionStore._key`; the cookie value is the session id). Dual read for the deploy window: a legacy raw-keyed record is `RENAME`d onto the hashed key (TTL kept). **Only a legacy-shaped id (`^[A-Za-z0-9_-]{43}$`, `token_urlsafe(32)`) may adopt, and `delete` only touches a legacy key for such an id** — a 64-hex key HASH is a *key name*, not a session id, and the first version of the dual read let a presented hash `H` RENAME the victim's `nai_session:H` onto `sha256(H)`: the attacker got the session and the victim was logged out. So the hashed key names are inert **only because of that guard**. `dep.py` also 401s any cookie that is not that shape before touching the store. `NOC-REMEDIATE[session-dual-read-sunset]` (in `redis_store.py`) removes the dual read after one full session TTL (24 h). `ops` has no SCAN; product users keep it (the seed's `flush_prefix` uses it) and see key names (hashes for sessions).
- **Cross-product session forging (pre-existing, NOT closed here).** The key families are shared names, so a compromised product's Redis user can not only read but **write** `nai_session:<sha256(id)>` and forge a session another product will honour (no MAC). The lockdown removes every non-product actor and, with the dedicated breaker instance, makes breaker integrity independent of app data; it does not stop product-to-product forging. Fix = a per-product key prefix in the seam or a MAC over the record: `NOC-REMEDIATE[redis-session-mac]` (`redis_store.py`). Each user already holds `~<slug>:*` for the prefix route.
- **Unbounded product-local keys:** erp-imobiliario's `@cached(key_prefix=…)` can't be bounded from code. It is asleep (no user). If woken it needs a `~erp:*` prefix and a render.
- `KEYS` (blocking) is used by social-wiring's download-cache sweep: `EXTRA_COMMANDS` grants it, `NOC-REMEDIATE[redis-keys-scan]` — switch it to `scan_iter` and drop the exception.
- **Rate limiter fails closed with auth required.** `resolve_limiter_storage_uri` re-raises any probe failure (WRONGPASS / NOPERM / unreachable) when `REDIS_REQUIRE_AUTH` is on, so a wrong password fails the boot instead of silently running a per-process limiter.
- **The boot crash-loop is intended.** With `REDIS_REQUIRE_AUTH=true` and no resolvable credentials the seam raises `RedisAuthRequired` at construction: the container exits, restarts and shows `Restarting` / failing health. That is the fail-closed outcome (a bare recreate that lost its env file cannot come up unauthenticated), and `deploy_image` rolls back on it. Do not "fix" it by clearing the flag.
- **EVAL freeze.** On the app instance products may run `eval evalsha script|load script|exists` (`limits` needs them). A script that has **written** and then loops forever is **unkillable**: `SCRIPT KILL` refuses once the script wrote, and nobody holds `SHUTDOWN`. Recovery is a restart: `noctus.vps.restart noctus-redis-acl` (the AOF replays; sessions survive). The breaker no longer shares that blast radius: its instance has no scripting for any user.
- **Image pin:** both instances run `redis:7.4.6-alpine` by digest. CVE-2025-49844 (Lua use-after-free to RCE) and CVE-2025-46818 are fixed in 7.2.11 / 7.4.6 / 8.0.4 / 8.2.2; steps 0 and 2 refuse anything lower, and the app product users can run EVAL.
- **`REDIS_PASSWORD_FILE`** is supported by the seam (env wins when both are set; an unreadable file raises). The rendered env files use `REDIS_PASSWORD` today.
- **Audit off-host, and products can erase their own trail.** `noctus:breaker:audit` and the per-product audit lists live only on the VPS breaker Redis: mirror them to a sink an attacker or a disk loss cannot reach. Also, a product user can `DEL`/`LTRIM`/`SREM` its OWN `audit` and `index` keys (they sit in its RW namespace), so a compromised product can wipe its own trail. Both recorded under `NOC-REMEDIATE[breaker-audit-offhost]` (`redis_acl.py`) with the Redis 7 selector idea: per-selector command lists so products hold only `+rpush +lrange +llen` on `audit` and ops alone trims the cap. Not built.
- ACL changes need a re-render + restart of that Redis (aclfiles are mounted read-only, loaded at start).

## 4. Rollout (guardian session, owner's live typed consent). Each step names its rollback.

**The guard is inert until you arm it.** `deploy_image` (deploy, pull AND rollback), `vps.recreate` and `ensure_product_url_roster` add `-f compose.redis-auth.prod.yml` to every compose call **whenever that file exists beside the base compose file**. The file is **host-local and gitignored**: `render --services <svc,...>` writes it, so a promote of this commit changes nothing, and every cutover is a deliberate re-render. While it exists: every listed service's generated env file must exist (a missing one refuses the call), and for a listed product both Redis containers must be running, else the call REFUSES (status `error`, container untouched). **Durable cutover marker:** `render --services` also writes `redis-auth/cutover.services` (one service per line); only an explicit `--services ''` clears it. While it lists services, the guard REFUSES when the override is missing or does not list them all (a deleted/clobbered override can no longer silently return a cut-over service to the old Redis), and `--redis-acl check` reports the same mismatch. The only bypass is `deploy_image(redis_auth="off")` (python/CLI, not an MCP flag); it is returned in the payload (`redis_auth.mode`, `files`, `skipped_files`, `recorded`) and writes a ledger finding every time. **Every** `deploy_image` payload (success included) carries `redis_auth`.

**0. Read-only inventory (no change).** (a) `docker exec noctus-core printenv REDIS_URL` (redact) and the root `.env` `REDIS_URL`: **which Redis do the products really use**, `noctus-redis` (fleet infra) or the legacy services-stack `redis` alias? (b) `docker ps --filter name=redis`, `docker network inspect noctus-net` (who is attached). (c) n8n UI > Credentials: any Redis credential? Workflows using the Redis node? (d) **version gate:** the NEW images must report `>= 7.4.6` (or >= 8.2.2): anything lower is REFUSED (Lua CVE-2025-49844 / CVE-2025-46818). (e) `docker exec noctus-redis redis-cli DBSIZE` + `ZCARD queue:conversation_due` (chatbot backlog). (f) **`legacy-permutas-celery`** (`deploy/legacy/compose.legacy.yml`: `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`, db index N): `docker exec legacy-permutas-celery printenv CELERY_BROKER_URL` (redact): which Redis host does the broker name? Stop if anything is unexpected.

**1. Secrets + net.** Add `REDIS_ACL_MASTER_SECRET=$(openssl rand -hex 32)` to the fleet `.env.fleet`; `docker network create --internal noctus-data`; **verify `docker network inspect -f '{{.Internal}}' noctus-data` prints `true`** (recreate it otherwise); on the VPS checkout `python mcp/noctusai/cli.py --redis-acl render --redis-acl-write` (no `--services`: aclfiles, env files and pass files only; `--redis-acl check` says `no_override`). **Ownership:** `ops.pass` and `ops-app.pass` stay root-owned 0600; `chown <forced-command-user> redis-auth/trip.pass` (the user the `breaker-trip.sh` forced command runs as) and `chown <host-probe-user> redis-auth/probe.pass`, keep 0600. The `redis-auth/` directory is 0711 (consumers can traverse to their own file, not list it). **A re-render preserves that ownership** (the new file is chowned to the existing owner before the rename; a non-root renderer rewrites the file in place), so this is a once-only step; still re-run `sudo -u <user> test -r redis-auth/<name>.pass` after every render, and `--redis-acl check` reports each pass file's owner uid, mode and flags a loose mode. Rollback: delete the generated `redis-auth/` directory, `docker network rm noctus-data`, drop the env line. No runtime effect.

**2. Start both Redis instances alongside.** `docker compose -f compose.infra.prod.yml --profile redis-acl up -d redis-acl breaker-redis`. Verify: (i) both healthy; (ii) **version:** `docker exec <c> redis-server --version` shows `v=7.4.6` or higher for **both** `noctus-redis-acl` and `noctus-breaker-redis`, otherwise `rm -sf` them and stop; (iii) `docker network inspect -f '{{.Internal}}' noctus-data` is `true` and `docker inspect <c> --format '{{json .NetworkSettings.Networks}}'` lists only `noctus-data`; (iv) `REDISCLI_AUTH=$(cat redis-auth/ops.pass) docker exec -e REDISCLI_AUTH noctus-breaker-redis redis-cli --user ops --no-auth-warning ping`, and an unauthenticated `redis-cli -h noctus-redis-acl ping` / `-h noctus-breaker-redis ping` from a throwaway container on `noctus-data` returns `NOAUTH`; (v) **the forced-command user can read its credential:** `sudo -u <forced-command-user> test -r redis-auth/trip.pass && echo ok` (and the probe user for `probe.pass`); (vi) `docker exec noctus-breaker-redis redis-cli --user ops ... config get maxmemory-policy` is refused (ops cannot reconfigure) and `redis-server` was booted with `noeviction`. Rollback: `docker compose -f compose.infra.prod.yml --profile redis-acl rm -sf redis-acl breaker-redis` (old Redis untouched; volumes kept).

**3. Land the tooling on the VPS** (ordinary `deploy_pull` of this commit). Inert: no override exists. Check: `--redis-acl check` still `no_override`, `deploy_image` dry-run of a product shows `redis_auth.files == []`. Rollback: none needed (nothing changed).

**4. Cut services over one at a time**, least critical first, `core` last (it serves SSO): `seed`, `monica`, `agents`, `social-wiring`, `core`. For service N: `python mcp/noctusai/cli.py --redis-acl render --redis-acl-write --redis-acl-services <services already cut over + N>`, then `deploy_image <N>` (same image; the override is added for you) or `vps.recreate`. Verify per service: (i) `/api/health` 200 and container healthy; (ii) logs contain `Rate limiter using Redis backend` (with `REDIS_REQUIRE_AUTH=true` a wrong password fails the boot, so a healthy container is evidence); (iii) an SSO login round trip for that product (session written to `nai_session:<sha256>`); (iv) a rate-limited route returns 429 on a burst; (v) app `ops` `ACL LOG` (`--user ops`, `ops-app.pass`) shows no `reason=command/key` denials for that user (a denial means a key family/command missing from the render: fix the render, not the ACL by hand); (vi) `docker inspect <c> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c '^REDIS_USERNAME='` = 1; (vii) **pass-file access survived the re-render:** `sudo -u <forced-command-user> test -r redis-auth/trip.pass` and `sudo -u <host-probe-user> test -r redis-auth/probe.pass` (a failure means the files were re-owned: re-`chown` once, then investigate); (viii) **cutover marker and override agree:** `--redis-acl check` says `in_sync`, and `cat redis-auth/cutover.services` lists exactly the services cut over so far. **Rollback per service:** re-render **without** that service (`--redis-acl-services <the others>`; an empty value removes the override), then `deploy_image <N>` returns it to the old Redis. Its sessions on the new Redis are left behind: users **log in again**.
  *Rollback-then-forward resurrects sessions.* A session created on the new Redis stays in its AOF until its TTL (<= 24 h). If you roll a service back and later cut it forward again, those sessions reappear, **including ones whose user logged out in between (the logout hit the old Redis)**. On any rollback of `core` or another session-issuing service, `UNLINK` its sessions on the new Redis at rollback time (`docker exec ... redis-cli --scan --pattern 'nai_session:*' | xargs ... UNLINK` with an identity that can; the app `ops` user has no key access by design, so use `docker exec noctus-redis-acl redis-cli` with the product credential from its env file, or restart the instance without its volume), or accept the <= 24 h window.

**5. Breaker adoption.** The breaker (unlanded) reads `NOCTUS_BREAKER_REDIS_URL` / `NOCTUS_BREAKER_REDIS_USERNAME` / `NOCTUS_BREAKER_REDIS_PASSWORD` (table in §3, already in each env file) and the `noctus-breaker-redis` container (§5). There are no breaker keys to migrate; land it **after** step 4.

**6. Soak** (>= 24 h, one nightly job cycle). Watch both `ACL LOG`s, product logs for `WRONGPASS`/`NOPERM`/`breaker: cannot read the breaker keys from Redis`. Rollback: as step 4.

**7. Scrub the old Redis of live credentials** (after `core` is cut over and soaked): every `nai_session:*` key on the OLD Redis is a bearer credential for a session that no longer exists on the new one, and is readable by anything on `noctus-net`. `docker exec noctus-redis redis-cli --scan --pattern 'nai_session:*' | xargs -r -n 200 docker exec -i noctus-redis redis-cli UNLINK` (a legacy raw-keyed record is a usable cookie; the hashed ones are inert only because of the legacy-shape guard). Rollback text, honestly: **sessions start empty**; if a product is pointed back at the old Redis, its users log in again.

**8. Retire the unauthenticated Redises. BLOCKED until `legacy-permutas-celery` has a home.** It uses the shared Redis as a Celery broker (db index N, keys `celery`, `_kombu.*`, `unacked*`, `celery-task-meta-*`, plus pub/sub channels, which a default ACL user cannot use). Two acceptable options, choose after step 0(f): (a) **private net (preferred, no ACL guesswork):** keep the old Redis alive but off `noctus-net`: a new internal `noctus-legacy-data` net joined only by that Redis, `legacy` and `legacy-celery`; rollback = rejoin `noctus-net`. (b) **an ACL user** `legacy-permutas` with `~celery* ~_kombu.* ~unacked* ~celery-task-meta-* &*` and the product command set, tested against a real kombu worker first (kombu's exact command set is NOT verified here). Only then: stop `noctus-redis` for everything else (keep the `redis_data` volume 7 days; rollback `start`). The legacy services-stack `redis` (alias `redis`, `redis:latest`, no auth, `deploy/services/compose.services.yml`): n8n has no `QUEUE_BULL_REDIS_*` env and stores in SQLite, WAHA Core has no Redis env, both only `depends_on` it for start order; after step 0(c) confirms no n8n Redis credential, remove the `depends_on: redis` entries and the service (or move it to the private net in (a)).

**9. Harden the base compose (a deliberate follow-up commit, after the soak, when every roster service is cut over).** Until then a *manual* bare `docker compose -f docker-compose.prod.yml up` (not the toolkit) silently returns a service to the old Redis. Make that fail closed: in `docker-compose.prod.yml` add to every roster service `REDIS_REQUIRE_AUTH: "true"` (a bare recreate then crash-loops without credentials: intended, §3) and the `noctus-data` network (list it beside `noctus-net`, or add it once to the `x-prod-defaults` anchor `networks:`). Do **not** land this before step 4 completes: it would make an ordinary promote crash-loop every product. Manual compose runbooks (`production-deploy.md`, the fleet `README.md`, the header of `docker-compose.prod.yml`) already say to add the second `-f` while the override exists.

**Downtime.** Per product: one container recreate (~20-40 s, `start_period: 20s`); APIs of other products unaffected. The new Redis starts **empty**: every user of the moved product is logged out once (sessions are not copied; the AOF then persists on the new volume), in-flight chatbot buffers and `conversation:memory:*` of that product are dropped (cut over with `ZCARD queue:conversation_due` at 0, step 0(e)), rate-limit counters reset (harmless). A warm copy (RDB `SAVE` + load before first start) is possible but not scripted; the owner's call, not needed for correctness.

## 5. Same-window changes on the unlanded breaker branches

Both must pass credentials and target the **breaker** instance `noctus-breaker-redis`, or they break the moment step 2 lands. The exact env names the products read: `NOCTUS_BREAKER_REDIS_URL`, `NOCTUS_BREAKER_REDIS_USERNAME`, `NOCTUS_BREAKER_REDIS_PASSWORD` (§3); `make_breaker_store` passes them to `make_redis_client(url, username=..., password=...)` explicitly (the seam's `REDIS_*` names stay for the app Redis).

**`feat/supabase-request-telemetry` — the `breaker-trip.sh` forced command (deploy/watchdog/)** (runs as the forced-command user; password from its own `0600` file, **never argv**):
```bash
REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-breaker-redis}"
TRIP_PASS_FILE="${NOCTUS_REDIS_TRIP_PASS_FILE:-/opt/noctus/noctusai/deploy/fleet/redis-auth/trip.pass}"
[[ -r "$TRIP_PASS_FILE" ]] || { echo '{"error":"trip credential unreadable"}' >&2; exit 3; }
export REDISCLI_AUTH; REDISCLI_AUTH="$(cat "$TRIP_PASS_FILE")"
rcli() { timeout 15 docker exec -e REDISCLI_AUTH "$REDIS_CONTAINER" redis-cli --no-auth-warning --user trip "$@" 2>/dev/null; }
out="$(rcli SETNX "$KEY" "$canon")"             # was: docker exec "$REDIS_CONTAINER" redis-cli SET ... NX
exists="$(rcli EXISTS "$KEY")"                  # was: docker exec ... redis-cli EXISTS
# SETNX replies 1 (tripped now) | 0 (an earlier trip stands); the old `OK` / empty-nil mapping becomes 1 / 0.
```
`host-probe.sh` uses `--user probe` with `redis-auth/probe.pass` (owned by its user) for its read-only `EXISTS`; `trip` is never used for reads.

**`feat/supabase-breaker` — the `supabase_breaker` toolkit module**, class `VpsRedisOps`: default `container="noctus-breaker-redis"`; `_cli` reads the ops credential **on the VPS** (never sent over SSH argv):
```python
cmd = ("REDISCLI_AUTH=\"$(cat /opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass)\" "
       f"docker exec -e REDISCLI_AUTH {shlex.quote(self._container)} redis-cli --no-auth-warning --user ops "
       + " ".join(shlex.quote(a) for a in args))
```
and extend the failure test to `"NOAUTH" in out or "WRONGPASS" in out or "NOPERM" in out`. `ops` has **no `scan`**: use `smembers` of each live slug's `noctus:breaker:<slug>:index` (slugs from `build-scope.txt`) plus the fleet key; the product-side store maintains the index (`SADD` with a persisted trip, `SREM` on release). Re-arm = `del` the key + `srem` it from the index + `set` the `noctus:breaker:<slug>:rearm:<source>` marker (**only ops writes it; products hold read-only**) + `rpush`/`ltrim` the audit list. `get`, `mget`, `set`, `del`, `rpush`, `ltrim`, `smembers`, `sadd`, `srem` are inside the `ops` grant.

## 6. Things this does not (and could not) verify

The live `REDIS_URL` each product resolves; n8n's stored credentials/workflows; WAHA's actual Redis use (config shows none); the `legacy-permutas-celery` broker host and kombu's exact command/channel needs (hence step 8 prefers a private net); the two Redis containers' hardening (`user: redis`, `cap_drop ALL`, `read_only`) against the real image (no Docker daemon in the authoring environment; the digest and its 7.4.6 tag were read from the registry, the ACL behaviour tests ran on a local 7.0.12 `redis-server`, which lacks `client|setinfo`, a 7.2+ command redis-py sends and swallows the refusal of, so a breaker-instance `ACL LOG` shows `client|setinfo` noise); the compose override's behaviour on the VPS's compose version (verified locally: `env_file` appends, `networks` unions).

Composes with: `redis-auth-seam.md` (client side) · `containerization.md` · `dev-prod-parity.md` · `prod-watchdog.md` · `deploy-config-contract.md` · `product-lockfile-and-slug-drift.md` (derive, don't hand-keep).
