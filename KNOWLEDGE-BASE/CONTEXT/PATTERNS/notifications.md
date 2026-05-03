# Notifications Pattern

Notifications are a **platform concern**, not per-product.

## Storage

- Single table: `public.notifications` (Core schema).
- Columns: `id, user_id, org_id, type, title, message, metadata, read, created_at`.
- Field-level mapping: internal `read` column is exposed as `is_read` in Portuguese API responses via `map_notification_to_pt()`.

## Product backends

Every product gets a notification proxy router out of the box via the seed framework:

- Routes: `GET /api/notificacoes`, `GET /api/notificacoes/contagem`, `PATCH /api/notificacoes/{id}/ler`, `POST /api/notificacoes/ler-todas`.
- Implementation: `seed/framework/backend/noctusai_seed/routers.py → _create_notificacoes_router`.
- Talks to Core via `deps.get_core_client()` (service role).

Products don't write notification routers. They just include the auto-wired one.

## Frontend

- Shared component: `NotificationBell` from `@noctusai/lib/design-system`.
- Wired into every product via `@noctusai/seed/infra`.
- Fetches count from `/api/notificacoes/contagem`, list from `/api/notificacoes`.

## Response shapes

- `GET /api/notificacoes` → `{data: [...], total, page, page_size}`.
- `GET /api/notificacoes/contagem` → `{nao_lidas: N}` (unwrapped — no `data` envelope).

The shared frontend hook `useContagemNaoLidas` returns `result` directly (not `result.data`) to match this contract.

## Sending a notification

Use `noctusai_lib.notifications.send_notification(core_db, user_id, ...)` from within a product. Don't write directly to `public.notifications` — the helper handles field mapping and metadata shape.

---

See also:
- `../04-SHARED-LIBRARY.md` — shared notification helpers
- `backend.md` — router → service layer pattern
