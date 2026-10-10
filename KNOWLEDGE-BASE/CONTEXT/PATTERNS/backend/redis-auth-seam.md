# Redis auth seam

> One seam builds every Redis client: `noctusai_lib.integrations.redis`. Prod Redis requires an ACL user + password; the seam is how that credential reaches every consumer (and every future feature) without per-site edits.

## Rule

- **Every Redis client goes through the seam** — `make_redis_client` (sync), `make_async_redis_client` (`redis.asyncio`), `redis_connection_url` (libraries that only take a URI, e.g. slowapi `storage_uri`). Never `redis.from_url`, `Redis(...)`, `StrictRedis(...)`, `aioredis` in seed or product code (tests + fakeredis exempt).
- **Credentials** come from `REDIS_URL` (may embed `user:pass@`) or the split env `REDIS_USERNAME` / `REDIS_PASSWORD`. Precedence: credentials embedded in the URL win; split creds apply only when the URL has none — never both. Explicit `username=`/`password=` args beat env.
- **Never log a raw Redis URL.** `redact_redis_url(url)` (password -> `***`, user kept) is the only way.
- **`REDIS_REQUIRE_AUTH=true`** (settings: `redis_require_auth`) makes the seam raise `RedisAuthRequired` at construction when no credentials resolve — fail-closed, loud, never an unauthenticated connection and never a silent in-memory fallback (the rate limiter re-raises it). Default false so nothing breaks before the rollout; turn it on in prod once Redis has the password.
- Settings fields (`BaseAppSettings`): `redis_username`, `redis_password` (SecretStr), `redis_require_auth`. The seam reads the process env, so they must be exported (compose `environment:`/`env_file:`), same as `REDIS_URL`.

## Gate

Keeper `check_redis_client_via_seam` (`--check-redis-client-via-seam`): AST scan of `seed/**/backend` + ACTIVE products' backend (`deploy/fleet/active-scope.txt`). Pre-commit runs it with `--paths` = the staged backend `.py` files only, so a commit is judged on what it touches. Full audit: run the flag with no `--paths`; also part of the aggregate compliance sweep.

## Adding a Redis-consuming feature

Take the URL from `settings.redis_url`, build the client with the factory, keep a `client=` injection point for tests (fakeredis via `make_fake_redis_client`).

Composes with: `seed-fake-real-adapter.md`, `core-url-routing.md`.
