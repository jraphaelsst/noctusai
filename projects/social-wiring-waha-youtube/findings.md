# findings.md — social-wiring-waha-youtube

Inline self-branch feature work (branch `feat/sw-waha-youtube`, off `origin/dev` 5755947a). Two tasks, file-disjoint (C1), both done inline by the architect (user: "work inline, don't dispatch — safer with other agents still working").

- **T1** — WAHA multi-session connection UI: per-user "lines" (WAHA URL + session + API key), API key Fernet-encrypted at rest, full QR/status/restart/logout/webhook lifecycle in-house (no WAHA dashboard needed).
- **T2** — YouTube page refactor: one `/youtube` page, top tabs Vídeos(default)|Upload; Vídeos→[Vídeos|Shorts], Upload→[Chat(default)|Computador|Drive]; Computador simplified to file+code; live step progress (100% = validation).

## Slips
_(none)_

## Errors
_(none)_

## Mistakes
_(none)_

## Lessons
- The seed `CredentialStore` (`token_store`) is single-row per `(org, provider)` — it does NOT fit a multi-row-per-user "connection lines" shape. Building a dedicated `whatsapp_connections` table is the honest model, NOT a seed fork: the ENCRYPTION primitive (`cryptography.fernet` + the shared `ENCRYPTION_KEY`) is still consumed from the seed via the product `credential_vault` seam.
- `video_cache` carries no Shorts flag — only `duration` (ISO-8601). `upload_jobs.target_format` ('youtube'|'shorts'|'unknown') exists on the upload side but the catalog rows don't carry it. The Vídeos/Shorts split is a **frontend duration heuristic (≤60s = Short)** — v1; see follow-up.
- The seed `WahaClient` had no `start_session` — required to pair a FRESH multi-session line (`POST /api/sessions/{name}/start`). Added to `WahaClient` + `FakeWahaClient` (additive; benefits ERP/therapy too).

## Interesting findings
- Follow-up (seed-lift candidate, N=1): a "multi-row per-user encrypted connection store" could become a seed primitive if ERP/therapy want per-user WAHA lines (N=2 trigger).
- Follow-up (Shorts accuracy): carry a real format flag from the upload pipeline (`upload_jobs.target_format`) into `video_cache`, or add a backend `is_short` derivation, to replace the frontend duration heuristic.
