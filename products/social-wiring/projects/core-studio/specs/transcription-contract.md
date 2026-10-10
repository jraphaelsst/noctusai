# Self-hosted transcription — design + contract (2026-10-09)

> Authored by the architect advisor, adopted by the tech-lead. Owner decisions: local faster-whisper large-v3-turbo on the prod server, hard-capped (1 core, ~2 GB, one job, queue), abuse-shielded. §7 records the tech-lead decisions on the points the design left open.

## Design: self-hosted, abuse-shielded transcription (`transcription` seam + `noctus-transcriber` worker)

**Recommendation: [F]ormalize.** Add a new seed IO module, `noctusai_lib.integrations.transcription`. Products queue jobs through the existing seed jobs primitive and the existing `social_wiring.jobs` table. The worker container holds no credentials, only answers on the internal network, and does one job at a time.

### What I checked in the tree
- `seed/lib/backend/noctusai_lib/integrations/llm/audio.py:16`: `transcribe_audio` goes through the LLM provider registry and needs an API key (`resolve_api_key`). A local Whisper engine is not an LLM provider, so adding a `local_whisper` provider there would bend the LLM seam. Keep `llm.audio` as it is and wrap it.
- `seed/lib/backend/noctusai_lib/domain/jobs/` already has `Job`, `JobRepository` (Fake + Supabase Real + factory) and a `Worker` with lease and heartbeat. `claim_next_job` uses `FOR UPDATE SKIP LOCKED` and reclaims expired leases.
- social-wiring already has the queue table (`migrations/121_jobs.sql`) and a running worker precedent (`app/modules/edicao_fotos/services/worker.py`). No new queue table is needed.
- **There is no Redis in prod.** `deploy/fleet/docker-compose.prod.yml` has no redis service, so the seed `RedisQuotaTracker` cannot be used. The in-memory tracker is lost on restart. Quotas therefore have to live in Postgres.
  - **Correction (2026-10-10):** prod Redis DOES exist — `noctus-redis` (redis:7-alpine) runs from `deploy/fleet/compose.infra.prod.yml`, not the fleet compose this check read, and `REDIS_URL` is set in prod `.env`. Durable minute quotas still belong in Postgres (auditable, tied to the rows, refundable); short-window request rate limits may use Redis. See `products/core/projects/transcription-api/CONTRACT.md` §3.
- No browser audio recorder exists anywhere: no `MediaRecorder` in `seed/lib/frontend/src` or any product. The recorder is a new seed organ, not a product-local component.
- Prod services share `x-prod-defaults` (`restart: unless-stopped`, `noctus-net`). Only 4 services set `mem_limit`, and none set `cpus`.

---

### 1. The seam (seed lib)
New package `seed/lib/backend/noctusai_lib/integrations/transcription/`:
- **`types.py`**
  - `TranscriptResult(text, duracao_s, idioma, modelo, rtf, segmentos?)`
  - `AudioProbe(duracao_s, codec, container, sample_rate, canais)`
  - Errors: `TranscriberBusy` (retryable, carries `retry_after_s`), `TranscriptionRejected` (permanent: decode or type failure), `TranscriberUnavailable`.
- **`protocol.py`**: `Transcriber` with `async probe(audio: bytes) -> AudioProbe` and `async transcribe(audio: bytes, *, language="pt", max_seconds) -> TranscriptResult`.
- **`fake.py`**: `FakeTranscriber`. Returns deterministic text, can be scripted to raise busy or rejected, and probes from a fixture map.
- **Two Real adapters:**
  - `openai_whisper.py`: `OpenAIWhisperTranscriber` wraps the existing `llm.audio.transcribe_audio`.
  - `local_whisper_http.py`: `LocalWhisperTranscriber`, an httpx client to the worker. Sends an `X-Transcriber-Token` header. Maps 503 to `TranscriberBusy`, 422 to `TranscriptionRejected`, and connection errors to `TranscriberUnavailable`. Timeout is `min(1800, 3×duracao + 60)` seconds.
- **`validation.py`** (pure): magic-byte sniffer accepting only these signatures:

  | Format | Signature |
  |---|---|
  | webm | EBML `1A45DFA3` |
  | mp4 / m4a | `ftyp` at offset 4 |
  | ogg | `OggS` |
  | mp3 | `ID3` / `FFFB` / `FFF3` |
  | wav | `RIFF....WAVE` |

  Plus `TranscriptionLimits` constants (numbers in §3).
- **`factory.py`**: `make_transcriber(kind=None)`. `kind` comes from env `TRANSCRIPTION_BACKEND` = `local_whisper | openai | fake`. If `local_whisper` is selected but `TRANSCRIBER_URL` or the token is missing, it raises. It never quietly falls back to OpenAI.
- **`server/` subpackage** (the engine). Optional extra `noctusai-lib[transcription-local]` (faster-whisper, ctranslate2, numpy) so products never install ctranslate2.
  - FastAPI app with `/healthz`, `/v1/probe`, `/v1/transcribe`.
  - Decoding: run `ffmpeg -nostdin -v error -i pipe:0 -t {max} -ac 1 -ar 16000 -f s16le -` as a subprocess, then numpy float32 / 32768. **This sidesteps `av` entirely**, so the 1.2.1 / av 19 `metadata_errors` crash cannot happen. Still pin `av` to whatever faster-whisper resolves, because it is a hard dependency.
  - Model: `WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)`.
  - Call: `transcribe(language="pt", vad_filter=True, beam_size=5)`.
  - An `asyncio.Semaphore(1)` guards transcription. When it is taken, the server returns 503 `{"codigo":"ocupado"}` with `Retry-After: 15`. **The worker has no internal queue.** The durable queue is the DB.
- **How products select it:** env `TRANSCRIPTION_BACKEND` per product container. social-wiring prod = `local_whisper`. Later (follow-up, not in this project): migrate `products/social-wiring/backend/app/services/media_service.py:200` and `mcp/openai_mcp/tools/transcribe.py` to `make_transcriber()`. That gives three consumers on one seam and closes the existing duplication.

### 2. The worker
**Image:** `deploy/services/transcriber/Dockerfile`
- Base: `python:3.12-slim-bookworm` plus Debian `ffmpeg`.
- `pip install --require-hashes -r requirements.lock`: faster-whisper==1.2.1, ctranslate2 and numpy pinned to the versions measured in §6, plus the seed lib extra.
- **Model baked into the image:** `huggingface_hub.snapshot_download("mobiuslabsgmbh/faster-whisper-large-v3-turbo", revision=<pinned commit sha>)` at build time. Runtime env `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`. About 0.8 GB of int8 weights, about 1.3 GB image.
  - Why baked: the image is reproducible and has no runtime egress.
  - Tag the image `transcriber:<model-rev>-<lib-sha>` and rebuild it only when its paths change. That needs a separate workflow, not the product build-scope.
- Runs as a non-root uid, `read_only: true`.

**Compose service `transcriber` (`container_name: noctus-transcriber`):**
- No `ports`, `expose: ["9000"]`. Not in `deploy/tunnel/ingress.yml`.
- Network: a new `transcribe-net` with `internal: true` (no egress). Only social-wiring (and later consumers) join it. The transcriber does not join `noctus-net`.
- Limits:
  - `cpus: "1.0"`
  - `cpu_shares: 256` (products default to 1024, so products win contention 4:1 inside the 2 vCPU)
  - `mem_limit: 2g`, `memswap_limit: 2g`
  - `pids_limit: 64`
  - `oom_score_adj: 1000`, so the host kernel kills it first. The host has no swap and about 3.9 GB available.
  - `tmpfs: /tmp:size=64m` (charged to the memory cgroup)
  - `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`
- Env: `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`. The entrypoint runs `nice -n 10`. A non-root process cannot lower priority below 0, so this only de-prioritises; `cpu_shares` does the real work.
- **Restart: `on-failure:5`**, not `unless-stopped`. An OOM or crash loop then stops after 5 attempts instead of churning the box. `deploy_verify` and health checks will surface it.
- Healthcheck: `GET /healthz` returns 200 only when the model is loaded. interval 30s, timeout 5s, retries 3, start_period 180s.
- In-process hard cap: transcription is killed at `min(1800, 3×duracao)` seconds. The server also counts minutes per UTC day in memory, capped at 600 min/day. This is a backstop only.

**Job flow:**
1. The social-wiring BE validates and reserves quota, then stores the audio in a private bucket.
2. It enqueues `social_wiring.jobs(type='transcricao', payload={transcricao_id})`. The payload has no path and no PII.
3. The in-process social-wiring worker claims the job, downloads the bytes, and POSTs them to `http://noctus-transcriber:9000/v1/transcribe`. Concurrency for this job type is 1, lease 300s with heartbeat.
4. On result it writes the text to `transcricoes` and deletes the audio.

**What happens on a restart:**
- **Transcriber restarts:** the in-flight HTTP call fails as `TranscriberUnavailable`. The job retries with backoff (`max_retries=2`). Queued jobs live in the DB and are unaffected.
- **social-wiring restarts:** its lease expires, `claim_next_job` reclaims the job, and it runs again. No job is lost. At worst one job runs twice, which is harmless because writing the result is idempotent on `transcricao_id`.
- Busy (503): reschedule with `scheduled_for = now()+retry_after` **without** using up a retry. **Verify first that the seed `Worker` has a reschedule-without-retry outcome** (`domain/jobs/worker.py`). If it does not, that is a small seed addition inside S1.

**Credential isolation:** the worker holds no Supabase key and has no egress. ffmpeg parsing untrusted media (the largest CVE surface) therefore runs where a compromise reaches nothing.

### 3. The abuse shield
**Auth**
- Seed auth dependency on every route, plus an org licence for social-wiring. Job reads are scoped to `user_id = me`.
- Worker calls also require the shared `TRANSCRIBER_TOKEN` (`.env.fleet` key), even on the internal network.

**Caps (`TranscriptionLimits`, overridable per product)**

| Limit | Value |
|---|---|
| Max upload | **15 MB** (10 min of 128 kbps webm ≈ 9.6 MB) |
| Max duration | **10 min** per file |
| Min duration | 1 s, otherwise `audio_vazio` |
| Allowed containers / codecs | webm/opus, ogg/opus, mp4/m4a (aac), mp3, wav (pcm) |

**Validation order (synchronous, before anything is queued)**
1. `Content-Length` ≤ 15 MB, and the stream is cut off at 15 MB (413).
2. Magic bytes (415).
3. `transcriber /v1/probe`: ffprobe with a 5s timeout, at most 2 concurrent calls. Probe calls are not gated by the transcription semaphore. Container and codec must be on the allowlist and duration within limits (422).
4. Quota is charged on the **probed** duration, not on a client-sent value.

**Rate limits and quotas (Postgres, one atomic RPC)**
`social_wiring.reservar_transcricao(user, org, duracao_s)` takes a `pg_advisory_xact_lock` per user, then checks and inserts in one transaction:

| Check | Limit |
|---|---|
| Per user | ≤ 10 submissions/hour, ≤ 30 min/day (rolling 24h) |
| Per user in flight | ≤ 2 queued or processing |
| Per org | ≤ 120 min/day |
| Global | ≤ 600 min/day; queue depth (queued + processing, all orgs) ≤ 20 |

Rolling 24h means `SUM(duracao_s) WHERE created_at > now()-'24h' AND status <> 'falhou_reembolsada'`. Minutes from a failure we caused are refunded.

**Backpressure**
- Per-user or per-org limits: **429**, `codigo` = `limite_usuario | cota_diaria_usuario | cota_diaria_org`, with `Retry-After` set to when the oldest counted row ages out.
- Global depth, global daily cap, transcriber unhealthy, or kill switch: **503**, `codigo` = `fila_cheia | capacidade_diaria | transcricao_indisponivel | transcricao_desativada`, with `Retry-After`.

**Timeouts**
- Worker hard cap: `3×duracao` (≤ 30 min).
- Client timeout: worker cap + 60s.
- A job still not finished 2h after creation is marked failed by the sweep and its minutes are refunded.

**Retention (LGPD: voice is personal data)**
- Audio goes in a **private** bucket `sw-transcricoes`. No public flag; `check_storage_no_public_buckets` must stay green. Path is `org/user/uuid.ext`; the original filename is never used.
- Audio is deleted **immediately** after success. Failed or dead-lettered audio is deleted after **72h** by a sweep that runs every 15 min.
- `transcricoes.audio_apagado_em` records the deletion.
- Transcript text lives only on the job row and in the answer the user saves. Unsaved transcripts are purged after 7 days.
- Logs never contain transcript text or audio paths.
- **Tech-lead action:** file `noctus.dev.lgpd_flag` for retention and purpose (done with this contract's commit).

**Logging and metrics**
- One structured line per job: `job_id, org, user, bytes, duracao_s, rtf, wait_s, status, codigo`.
- An admin-only `GET /api/transcricoes/_stats` returns `queue_stats` (seed repo) plus daily minutes per org.

**Kill switch**
- A DB-first setting `transcricao_habilitada` (platform_settings, then env fallback). When false, submit returns 503 `transcricao_desativada` and the worker leaves pending jobs untouched.
- Hard stop: `docker stop noctus-transcriber`. Jobs keep `pending`; health checks make new submits return 503.

### 4. Async UX contract (generic, reusable by the YouTube and extraction consumers)
- **`POST /api/transcricoes`**
  - Body: multipart `arquivo` + `contexto_tipo` (`cerebro_resposta`) + `contexto_ref` (`{cerebro_id}:{question_id}`).
  - Returns **202** `{id, status:"na_fila", posicao, estimativa_s, duracao_s}`.
- **`GET /api/transcricoes/{id}`**
  - Returns `{id, status, posicao?, duracao_s, texto?, erro?:{codigo, mensagem}, criado_em, concluido_em?}`.
  - Statuses: `na_fila → processando → concluida | falhou | cancelada`.
- **`DELETE /api/transcricoes/{id}`**: cancels a job that is still `na_fila` (refunds minutes and deletes the audio). Returns 409 if it is already processing.
- **Error envelope** (platform standard): `{codigo, mensagem}` with pt-BR messages.
  - 413 `arquivo_grande`, 415 `formato_invalido`, 422 `duracao_excedida | audio_vazio | audio_corrompido`, 429 and 503 as in §3, 404 for another user's job (never 403, so job ids cannot be enumerated).
- **Frontend behaviour**
  - Poll every 3s for the first 30s, then every 10s, and stop on a terminal status. Use TanStack `refetchInterval` with `showSkeleton = isPending && !data`, never `isLoading`.
  - On `concluida`, the text fills the textarea and the user reviews it before "Aplicar". This matches spec §3.5 line 361 and check-step 21.
  - **Transcription never writes into the brain on its own**, which also gets rid of the legacy 1 MiB chunk endpoint.

### 5. Slice plan (file-disjoint)

| Step | Slice | Owner | Files | Depends on |
|---|---|---|---|---|
| 0 | Contracts | tech-lead, inline | Worker HTTP contract (`/healthz`, `/v1/probe`, `/v1/transcribe`, errors) + product API contract (§4), written into `projects/.../core-studio/` | — |
| 1 | Seed client | engineer-seed | `integrations/transcription/{__init__,types,protocol,fake,openai_whisper,local_whisper_http,validation,factory}.py` + tests. Also the jobs `Worker` reschedule-without-retry, if missing. | 0 |
| 2 | Worker / devops | devops-engineer (+ engineer-seed for `server/`) | `integrations/transcription/server/**` + its tests + the `[transcription-local]` extra; `deploy/services/transcriber/**` (Dockerfile, `requirements.lock`); `transcriber` service + `transcribe-net` in `deploy/fleet/docker-compose.prod.yml`; build workflow; `.env.fleet` keys (`TRANSCRIBER_TOKEN`) | 0; parallel with 1 (S1 owns `__init__`, S2 only `server/`) |
| 3 | Product backend | backend-engineer | social-wiring migration, router, service, job handler, retention sweep, kill switch | lands after S1 |
| 4 | Frontend | frontend-engineer | Seed organ `useAudioRecorder` + `VoiceAnswerInput` in `seed/lib/frontend/src/...` (webm → mp4 → mp3 mime fallback, timer, 10-min auto-stop, waveform) + social-wiring brain editor wiring | 0 only (contract-first); parallel with 3 |
| 5 | Measurement | devops | See §6 | S2 image; **before** S3/S4 integrate, so the go/no-go comes early |
| 6 | Enable | tech-lead | Turn on `transcricao_habilitada` after measurement passes and predeploy_check is green | 5 |

**Migration** (social-wiring, numbered at integrate time, ≥219; `noctus.dev.scaffold_migration` will compute it):
- `NNN_transcricoes.sql`:
  - Table `social_wiring.transcricoes`: `id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, status CHECK(...), texto, erro_codigo, modelo, rtf, criado_em, iniciado_em, concluido_em, audio_apagado_em, minutos_reembolsados bool`.
  - Indexes on `(user_id, criado_em)`, `(org_id, criado_em)` and `(status)`.
  - RLS: owner can SELECT their own rows. All writes are service-role only.
  - RPC `reservar_transcricao` (advisory lock, quota and depth checks, insert, returns the row or a `codigo`).
  - Private bucket insert with `public = false`.
- `jobs` is reused from migration 121, so there is no second migration.

### 6. Risks and the throughput measurement
**Measurement (step 5, on the VPS, before enabling):**
- `docker run --cpus 1 --cpu-shares 256 -m 2g` the image against 3 pt-BR fixtures: 30 s, 3 min, 10 min webm/opus.
- Record:
  - RTF = wall time / audio length
  - Peak memory from cgroup `memory.peak`
  - Model load time
  - Product health p95 during the run (`smoke_fleet` + `spa_smoke` latency vs a baseline with the transcriber off)
- **Pass criteria:** RTF ≤ 1.5, peak ≤ 1.6 GB, product p95 health latency within +20% of baseline, zero OOM.
- Expectation: the Mac's 0.42× used many threads. One EPYC core at int8 likely lands around 1–2× real time, so 10 minutes of audio could take 10–20 minutes. That is acceptable for an async queue, but you need to measure it.

**Fallback ladder, if it fails:**
1. Try `beam_size=1` (greedy, roughly 1.5–2× faster decode, small quality loss in pt).
2. Lower the max duration to 5 min.
3. Fall back to `faster-whisper-small` int8 (about 4× faster, about 0.5 GB RAM, noticeably worse pt-BR).
4. Set `TRANSCRIPTION_BACKEND=openai` per product. The factory supports it with no code change; about $0.006/min, bounded by the same quotas.

**Risks**
- **Host memory, no swap:** the 2 GB cap leaves about 1.9 GB of headroom. `mem_limit` plus `oom_score_adj=1000` make the transcriber the first thing killed. Re-check headroom with `noctus.vps_disk` / stats before enabling.
- **Deploy path:** `noctus.dev.deploy_image` / `migrate_product` refuse anything that is not ativo+live in the catalog, and the transcriber is not a product. **Decision needed:** add a sanctioned non-product service path (a service allowlist in deploy_image), or deploy it as part of core. Do not use a manual `docker compose up` workaround.
- **Disk:** the image is about 1.3 GB. Check `noctus.vps_disk` before the first pull, and prune old tags.
- **Faster-whisper / av drift:** solved by the ffmpeg-pipe decode plus the hash-locked requirements. `server/` gets a test that decodes webm, mp4 and ogg fixtures through ffmpeg.
- **Later URL consumers (YouTube, Minhas extrações):** SSRF and huge downloads. Fetching must happen in the product, with a duration check (yt-dlp metadata) **before** download and the same quotas. The transcriber stays without egress.
- **Fairness across products:** with more consumers, each product's worker competes for one global semaphore. Busy returns 503 and the job is rescheduled. Acceptable up to about 3 consumers; beyond that, move to a platform-level queue (a core schema `jobs`). Mark it `NOC-REMEDIATE[transcription-fairness]`.

**Relevant paths**
- /Users/rapha/Documents/repository/NoctusAI/noctusai/seed/lib/backend/noctusai_lib/integrations/llm/audio.py
- /Users/rapha/Documents/repository/NoctusAI/noctusai/seed/lib/backend/noctusai_lib/domain/jobs/ (`__init__.py`, `repo.py`, `worker.py`, `migrations/jobs.sql.template`)
- /Users/rapha/Documents/repository/NoctusAI/noctusai/seed/lib/backend/noctusai_lib/integrations/quota/__init__.py (in-memory/Redis only, so Postgres is used instead)
- /Users/rapha/Documents/repository/NoctusAI/noctusai/seed/lib/backend/noctusai_lib/integrations/storage/
- /Users/rapha/Documents/repository/NoctusAI/noctusai/products/social-wiring/backend/migrations/121_jobs.sql
- /Users/rapha/Documents/repository/NoctusAI/noctusai/products/social-wiring/backend/app/modules/edicao_fotos/services/worker.py
- /Users/rapha/Documents/repository/NoctusAI/noctusai/products/social-wiring/backend/app/services/media_service.py (line 200)
- /Users/rapha/Documents/repository/NoctusAI/noctusai/products/social-wiring/projects/core-studio/specs/pesquisa-cerebro-spec.md (§3.5 lines 355–375, §6 line 507)
- /Users/rapha/Documents/repository/NoctusAI/noctusai/deploy/fleet/docker-compose.prod.yml (lines 110–117 `x-prod-defaults`)

## 7 · Tech-lead decisions (2026-10-09)

- ✅ 7 · Owner authorized prod exposure of `transcriber` (2026-10-09, typed phrase; record `deploy/consent/transcriber.prod.yml`). Ships with the opt-in compose profile and the kill switch OFF; enabled only after the §6 measurement and the owner's evaluation.

- **Deploy path:** formalize a sanctioned **non-product service allowlist** in `noctus.dev.deploy_image` / `deploy_verify` (the transcriber is infrastructure, not a product; folding it into core would couple unrelated release cycles). No manual `docker compose up`. This is its own toolkit slice, shipped with its tests, before the transcriber's first prod deploy.
- **Enable order:** S5 measurement on the VPS (pass criteria in §6) gates S6. The kill switch `transcricao_habilitada` ships **off**.
- **Fallback ladder** in §6 is pre-approved in order 1→3; step 4 (OpenAI) needs the owner's go, since the owner chose self-hosted for cost.
- **Migration number:** scaffolded at integrate time (≥219 band; other sessions hold 218–220).

