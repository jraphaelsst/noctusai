# Roadmap — platform transcription API + seed Redis auth (2026-10)

> Owner asks (2026-10-09/10, session noctusai-fe):
> 1. The transcriber is a **24/7 live API** we can call at any time; transcription never runs locally. Async jobs API, with rate limiting/caps for safety.
> 2. Prod Redis gets **a password** (data kept), via a **seed Redis auth seam** that every active product's Redis usage consumes, so future Redis features go through it by construction.
> Contract: `products/core/projects/transcription-api/CONTRACT.md`.

## T-track — transcription API

| Phase | What | Gate | Status |
|---|---|---|---|
| T0 | Contract + this roadmap | — | shipped (this commit) |
| T1 | Slices A (core migration), B (core API + worker + sweeps), C (client tool) — parallel | T0 | next |
| T2 | Slice E: worker hard cap `min(9000, 3×duracao)` | coordinate with noctusai-76 | open |
| T3 | Slice D: core joins `transcribe-net`; transcriber always-on | SW contract §6 VPS measurement passes | blocked on measurement |
| T4 | Slice F: deploy + enable `transcricao_api_habilitada` + smoke | non-product deploy path (`b27397f43`) on dev; T1–T3 | blocked |
| T5 | Follow-up: social-wiring consumes this API instead of its own queue (closes `NOC-REMEDIATE[transcription-fairness]`) | T4 | deferred |

## R-track — seed Redis auth

| Phase | What | Gate | Status |
|---|---|---|---|
| R0 | Inventory every Redis consumer (seed, active products, mcp, deploy) | — | in progress |
| R1 | Seed seam: one canonical authenticated Redis connection builder (URL with ACL user/password, or split `REDIS_USERNAME`/`REDIS_PASSWORD`); never logs the secret | R0 | open |
| R2 | Migrate every active-product + seed consumer onto R1; keeper forbids constructing a Redis client outside the seam | R1 | open |
| R3 | Prod rollout, zero-downtime: ACL user `noctus` with a VPS-generated password → `REDIS_URL` updated in prod `.env` → recreate consumers → verify every client authenticated → `default` user off → persist via `--aclfile` on the data volume (hash only) in `deploy/fleet/compose.infra.prod.yml`; recreate `noctus-redis` from the canonical file (it currently runs from an old `projects/production-deploy-migration/…` path) | R2 deployed | open |
| R4 | `noctus-services-redis-1` (empty, same no-password exposure on `noctus-net`): password it the same way or retire it if nothing consumes it | R0 finding | open |

## Facts (verified 2026-10-10)

- Prod Redis: `noctus-redis` (redis:7-alpine, AOF, `noctus-net`, 16 live keys: conversation/upload queues, Meta leadgen dedup, realtime agent/WA state, one limiter key) and `noctus-services-redis-1` (redis:latest, empty). **Both accept unauthenticated connections from any container on `noctus-net`.**
- Prod `.env` sets `REDIS_URL` (passwordless, `redis://noctus-redis:6379/0`) and `REDIS_SESSION_ENCRYPTION_KEY`.
- A flush would lose queued work and could double-push Meta leads — never flush as part of this roadmap.

## Decisions log

- 2026-10-09 · Async jobs API, rate limits/caps mandatory, built by noctusai-fe (owner).
- 2026-10-10 · "Reset our Redis" = add a password, keep the data (owner). Seed Redis auth seam, consumed by every active product, enforced for future features (owner).
- 2026-10-10 · API placed in core (already public at core.noctusai.com; worker stays internal-only) — tech-lead, per SW contract §6 fairness note.
