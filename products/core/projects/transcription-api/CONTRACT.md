# Platform transcription API — contract (2026-10-10)

> **Owner requirement (2026-10-09):** the self-hosted transcriber is a **24/7 live service with an API we can call at any time** (agents, scripts, products). Transcription runs on our server, never on a laptop.
> **Owner decisions:** async jobs API (submit → id → poll), with rate limiting and caps as an explicit safety requirement; built from this session (noctusai-fe).
> **Builds on, does not replace:** `products/social-wiring/projects/core-studio/specs/transcription-contract.md` (the seed `transcription` seam, the `noctus-transcriber` worker, its abuse shield). Read it first; this file only states what differs.
> Roadmap: `project-history/roadmaps/transcription-api-2026-10.md`.

## 0 · Placement and why

The API lives in **core** (`products/core/backend`, schema `public`). Core is already public at `core.noctusai.com` through the tunnel, so there is **no new public hostname**. The worker stays exactly as shipped: `transcribe-net` (internal, no egress), no credentials, one job at a time. Core joins `transcribe-net`; nothing else changes on the worker's network.

This is the "platform-level queue" the SW contract §6 named as the fix for `NOC-REMEDIATE[transcription-fairness]`. Follow-up (not in this project): social-wiring consumes this API instead of running its own transcription queue.

## 1 · Auth

- Seed session dependency (`noctusai_lib.api.auth.session.dep`), two caller kinds:
  - **Machine:** `Authorization: Bearer pk_*` product token, resolved against `public.api_tokens` (seed SEED-1 shape; see `products/agents/backend/migrations/007_api_tokens.sql`). Required scopes: `transcription:write` for submit/cancel, `transcription:read` for reads.
  - **User:** a normal platform session (Bearer JWT). Allowed, same quotas.
- **Caller identity** = `(caller_kind, caller_id)`: `token` + `api_tokens.id`, or `user` + `user_id`. Every row stores it plus `org_id`.
- A caller sees **only its own jobs**. Anything else is **404**, never 403, so ids cannot be enumerated.
- If core has no `pk_*` resolver yet, slice A adds `public.api_tokens` + `api_token_audit` in the SEED-1 shape and slice B wires `SupabaseApiTokenResolver(schema="public")`. Minting is platform-admin only (existing token admin seam).

## 2 · Endpoints (core, prefix `/api/transcriptions`)

Error envelope is the platform standard `{codigo, mensagem}` (pt-BR messages). Status vocabulary is **reused from the SW contract §4** so there is one vocabulary platform-wide.

| Method + path | Body / query | Success | Notes |
|---|---|---|---|
| `POST /api/transcriptions` | multipart `arquivo` (required), `idioma` (default `pt`), `rotulo` (≤120 chars, optional), `segmentos` (bool, default false) | **202** `{id, status:"na_fila", posicao, estimativa_s, duracao_s}` | validation order in §3; quota charged on the **probed** duration |
| `GET /api/transcriptions/{id}` | — | 200 `{id, status, posicao?, duracao_s, idioma, rotulo?, texto?, segmentos?, modelo?, rtf?, erro?:{codigo,mensagem}, criado_em, iniciado_em?, concluido_em?, expira_em}` | `texto` only when `concluida` |
| `GET /api/transcriptions` | `status?`, `limit` (≤100, default 20), `cursor?` | 200 `{items:[…same minus texto/segmentos…], next_cursor?}` | own jobs only |
| `DELETE /api/transcriptions/{id}` | — | 204 | `na_fila` → cancel, refund minutes, delete audio. `concluida`/`falhou` → purge text now. `processando` → **409** `em_processamento` |
| `GET /api/transcriptions/_stats` | — | 200 `{fila, processando, minutos_hoje_global, minutos_hoje_por_org[], worker_saudavel, habilitada}` | platform admin only |

**Statuses:** `na_fila → processando → concluida | falhou | cancelada`.

**Errors:** 401 (strict, no token) · 403 `escopo_insuficiente` · 404 · 409 `em_processamento` · 413 `arquivo_grande` · 415 `formato_invalido` · 422 `duracao_excedida | audio_vazio | audio_corrompido` · 429 `limite_requisicoes | limite_envios_hora | cota_diaria_chamador | cota_diaria_org | limite_em_andamento` · 503 `fila_cheia | capacidade_diaria | transcricao_indisponivel | transcricao_desativada`. Every 429/503 carries `Retry-After`.

**Client polling guidance:** every 5 s for the first minute, then every 30 s; `estimativa_s` is a hint, not a promise.

## 3 · Safety: caps, quotas, rate limits

Platform callers transcribe whole recordings (e.g. a 25-min video), so the file caps are larger than SW's voice-answer caps. They are constants in one place (`TranscriptionLimits` override for core) — not scattered literals.

**Per file**
| Limit | Value |
|---|---|
| Max upload | **150 MB** (stream cut at the cap → 413) |
| Max duration | **45 min** |
| Min duration | 1 s (`audio_vazio`) |
| Formats | magic-byte allowlist from the SW contract §1 (webm, mp4/m4a, ogg, mp3, wav) + `/v1/probe` codec allowlist |

**Validation order (synchronous, before anything is queued):** Content-Length / streamed size → magic bytes → kill switch → worker `/v1/probe` (duration + codec) → quota RPC (§3 table) → store audio → enqueue.

**Durable quotas — Postgres, one atomic RPC** `public.reservar_transcricao_api(caller_kind, caller_id, org_id, duracao_s)` (advisory xact lock per caller; checks + insert in one transaction; returns the row or a `codigo`):
| Check | Limit |
|---|---|
| Per caller | ≤ 20 submissions / rolling hour; ≤ 180 min / rolling 24 h; ≤ 3 in flight (`na_fila` + `processando`) |
| Per org | ≤ 300 min / rolling 24 h |
| Global (this API) | ≤ 600 min / rolling 24 h; queue depth ≤ 20 |

Minutes from failures **we** caused (worker crash, timeout, unavailable) are refunded (`minutos_reembolsados`), exactly as in the SW contract.

**Burst rate limits — Redis** via core's existing limiter (`app/rate_limit.py` → `create_product_limiter`, Redis-backed when `REDIS_URL` is set), keyed by caller identity: `POST` 10/min, `GET` 120/min, `DELETE` 30/min → 429 `limite_requisicoes`. Prod Redis exists (`noctus-redis`, 2026-10-10 inventory) — the SW contract's "no Redis in prod" line was wrong and is corrected. Redis connections go through the seed Redis auth seam (see roadmap R-track) once it lands.

**Kill switch:** `transcricao_api_habilitada` in `platform_settings` (DB first, env fallback), ships **false**. False → submit 503 `transcricao_desativada`; the worker loop leaves `na_fila` jobs untouched.

**Timeouts:** worker call timeout `3×duracao + 60 s`; a job not finished `3×duracao + 1 h` after `iniciado_em` (or 6 h after `criado_em` if never started) is marked `falhou` by the sweep and refunded.

**Worker cap dependency:** the worker's in-process hard cap is `min(1800, 3×duracao)` s. A 45-min file needs up to 8100 s. Slice E raises the worker cap to `min(9000, 3×duracao)` (seed `integrations/transcription/server/`, coordinated with noctusai-76) **before** the 45-min limit is enabled; until then core enforces `duracao ≤ 10 min` (`TRANSCRIPTION_API_MAX_S` env, default 600).

## 4 · Data (slice A — one core migration, number scaffolded at integrate)

- `public.jobs` from `seed/lib/backend/noctusai_lib/domain/jobs/migrations/jobs.sql.template` (if core has none). Job type `transcricao_api`, payload `{transcricao_id}` only — no paths, no PII.
- `public.transcricoes_api`: `id uuid pk, org_id, caller_kind text CHECK (token|user), caller_id uuid, rotulo, idioma, storage_path, bytes, duracao_s numeric, formato, status CHECK(...), texto, segmentos jsonb, erro_codigo, modelo, rtf, criado_em, iniciado_em, concluido_em, expira_em, audio_apagado_em, minutos_reembolsados bool default false`.
  - Indexes: `(caller_kind, caller_id, criado_em)`, `(org_id, criado_em)`, `(status, criado_em)`.
  - RLS on; **service-role only** for every operation (core reads/writes through the service client; callers never hit PostgREST directly).
- RPC `reservar_transcricao_api` (§3). `SECURITY DEFINER` with `EXECUTE` revoked from `anon, authenticated` (keeper `check_secdef_execute_revoke`).
- Private bucket `core-transcricoes` (`public = false`; `check_storage_no_public_buckets` stays green). Path `org/<caller_kind>/<caller_id>/<uuid>.<ext>`; original filename never stored.
- `platform_settings` row `transcricao_api_habilitada = false`.

## 5 · Worker loop + retention (slice B)

- In-process core worker on the seed jobs primitive (`domain/jobs/worker.py`): concurrency 1, lease 300 s + heartbeat, `max_retries=2`. `TranscriberBusy` → **RescheduleLater** (`retry_after`) without consuming a retry (seed outcome added in `d75ee57bb`).
- Transcriber via `make_transcriber()` with `TRANSCRIPTION_BACKEND=local_whisper`, `TRANSCRIBER_URL=http://noctus-transcriber:9000`, `TRANSCRIBER_TOKEN` from `.env.fleet`. Never silently falls back to OpenAI.
- **Retention (LGPD — voice is personal data; file `noctus.dev.lgpd_flag`):**
  - audio deleted **immediately** after `concluida`; after 72 h for `falhou`/`cancelada` (sweep every 15 min);
  - `texto`/`segmentos` purged **30 days** after `concluido_em` (`expira_em`), or immediately on `DELETE`;
  - logs never contain text or storage paths. One structured line per job: `id, org, caller_kind, bytes, duracao_s, rtf, wait_s, status, codigo`.

## 6 · Client tool (slice C)

`noctus.transcription.submit` / `noctus.transcription.get` MCP tools (+ `noctus.transcription.transcribe` convenience: submit a local file, poll with backoff until terminal or `timeout_s`, return `{status, texto, duracao_s, rtf}`), with CLI flags. Config: `NOCTUS_TRANSCRIPTION_URL` (default `https://core.noctusai.com`) + `NOCTUS_TRANSCRIPTION_TOKEN` (a `pk_*` token) from the repo-root `.env`. Pure HTTP client — no ffmpeg, no model, nothing local. Honors 429/503 `Retry-After`.

## 7 · Slices (file-disjoint)

| Slice | Owner | Files | Depends on |
|---|---|---|---|
| A · Core migration | backend-engineer | `products/core/backend/migrations/NNN_transcription_api.sql` + its migration test | this contract |
| B · Core API + worker + sweeps | backend-engineer | `products/core/backend/app/routers/transcriptions.py`, `app/services/transcription_api/**`, router + worker registration in `app/main.py`, `app/config.py` fields, tests under `products/core/backend/tests/` | contract (parallel with A; schema is fixed here) |
| C · Client tool | engineer-seed | `mcp/noctusai/tools/noctus/transcription/**`, its tests, `mcp/noctusai/cli.py` flags | contract only |
| D · Compose + env | tech-lead | `deploy/fleet/docker-compose.prod.yml` (core joins `transcribe-net`; transcriber off the opt-in profile, `restart: unless-stopped`), `deploy/fleet/env.fleet.keys` | §6 VPS measurement (SW contract) passes |
| E · Worker cap | coordinated with noctusai-76 | `seed/lib/backend/noctusai_lib/integrations/transcription/server/engine.py` (+ test) | — |
| F · Enable | tech-lead + owner | `transcricao_api_habilitada = true` after D, deploy, smoke | non-product deploy path (`b27397f43`, another session) + D |
