# Resumable chunked uploads (seed)

> `noctusai_lib.domain.resumable_uploads` (backend seam) + `uploadResumable` / `useResumableUpload` in `@noctusai/lib`
> (frontend). Built 2026-11-13. First consumer (pilot): social-wiring Edição de Fotos `NovoLote`.

## Why

One big request restarts from zero on a dropped mobile connection and its progress bar lies. Here the file is cut into
parts, 4 are sent in parallel, a failed part retries with exponential backoff, and after a disconnect only the parts
the SERVER reports as missing are re-sent. Progress counts server-confirmed parts only.

## Decision: own chunk endpoints, not Supabase TUS

TUS (or a signed upload URL) puts a storage credential in the browser, scopes by bucket policy rather than by one
session, and a signed URL is a single PUT (not resumable). Our endpoints keep the resume state (the parts) server-side,
bind every session to ONE org + ONE object prefix, and run on Fake / Local / Supabase through the existing
`StorageBackend` seam. Trade-off: `complete` assembles in memory, so `UploadPolicy.max_bytes` (default 500 MiB) bounds it.

## Shape

| Piece | What |
|---|---|
| `ResumableUploadService` | `open` (limits, type, `client_key` resume) -> `status` (parts held) -> `put_part` (exact size, idempotent) -> `complete` (409 `partes_faltando` + `missing`) / `abort` / `expire_stale` (scheduler hook) / `consume` (server-side read + delete) |
| `UploadSessionStore` | Protocol + Fake + Supabase; `upload_sessions` + append-only `upload_session_events` (`opened`/`completed`/`aborted`/`expired`), service-role only (organ migration `resumable_uploads`) |
| `create_resumable_upload_router` | access tier `org`; open / status / `PUT parts/{n}` raw bytes / complete / abort; the host registers `part_path_pattern(prefix): part_body_limit()` in `max_body_path_overrides` |
| FE `uploadResumable(api, file, opts)` | concurrency 4, retry + backoff (network / 408 / 425 / 429 / 5xx only), resume by `clientKey`, re-sends `missing` on a 409 at complete; needs `api.putRaw` (`createApiClient` provides it) |

Keys are derived server-side: `<prefix>/<org>/_parts/<session>/<n>` and `<prefix>/<org>/<session>/<filename>`; another
org's session is a 404. Schedule `expire_stale()` in the host to drop abandoned parts (TTL default 24 h).

## Consuming it (pilot)

`createEdicaoFotosHooks(api, { resumableThresholdBytes })` is OPT-IN: photos at or above the threshold go chunked then
`POST /lotes/{id}/fotos/de-upload {upload_ids}`; the rest keep the legacy multipart request.

## Anti-patterns

Handing the browser a storage token; trusting the client's part list instead of `GET status`; counting in-flight bytes
as progress; retrying a final 4xx (expired / invalid part).
