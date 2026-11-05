# Notifications Pattern

Notifications are a **platform concern**, not per-product. THE definition agents follow (owner, 2026-11-04). Two classes, never mixed.

## The two classes

| Class | Use it for | Channel | Look |
|---|---|---|---|
| **Feedback** (system) | the result of an action the user just took: saved, failed, error | sonner `toast.success` / `toast.error`, client only, no DB row | green / red (richColors), with an X close |
| **Operational** | something that happened which the user did not trigger: new lead, Vista sync applied, approval pending | an in-app row via `noctusai_lib.domain.notifications.write_in_app` -> bell list + live **neutral** pop-up | neutral (no green/red), title + message, X close, ~8 s auto-dismiss (pauses on hover), click opens `metadata.link` |

Anti-pattern: reporting an operational event only as a toast (it vanishes, and nobody online sees it), or a user-triggered result as a DB row.

## Storage and API

- Single table `public.notifications` (core). Product events are `type='system'`; the product kind lives in `metadata.tipo` (core's CHECK admits only core's own types). A product never writes `type` itself - `write_in_app` does.
- `read` is exposed as `is_read` via `map_notification_to_pt()`.
- Every product gets the proxy router from the seed (`seed/framework/backend/noctusai_seed/routers.py -> _create_notificacoes_router`): `GET /api/notificacoes`, `GET /api/notificacoes/contagem` (`{nao_lidas: N}`, unwrapped), `PATCH /api/notificacoes/{id}/ler`, `POST /api/notificacoes/ler-todas`. Products do not write notification routers.

## Emitting an operational notice (backend)

`write_in_app(core, user_ids, kind, title, message, metadata, org_id)`, wrapped for the common case by **`notify_org_admins(core, org_id=, kind=, title=, message=, produto=, link=, entidade=)`** (same module). Rules:

- `metadata = {"categoria": "operacional", "link": "/relative/path" | null, "produto": "<slug>", "entidade": {"tipo": "lead"|"imovel"|..., "id": "<id>"} | null}` (`operational_metadata()` builds it).
- `kind` is snake_case pt-BR: `lead_novo`, `leads_importados`, `imoveis_vista_sincronizado`, `imovel_aprovacao_pendente`.
- `title` <= 60 chars, `message` <= 160 chars (the helper truncates). No PII beyond a name: never a phone or e-mail.
- **Recipients: org owners + admins** (owner decision "keep admins for now"), resolved by ONE seed helper, `resolve_org_admin_user_ids` (trusted `noctus_users` + active `org_memberships`; never `user_metadata`). Never a per-product recipient query.
- **An empty recipient set logs WARNING and returns 0.**
- **Emission never fails the caller**: `notify_org_admins` catches and logs at ERROR; a lost notice must not fail the lead / the sync.
- Emit at the ONE seam all paths stack on (e.g. SW `leads_service.create_lead`), so two paths cannot duplicate or forget. Bulk operations emit ONE summary, not N rows; historical backfills emit none.
- **WhatsApp / email only by explicit owner decision per event** - never the default for an operational notice.

## Events that MUST notify (extend this list)

| Event | kind | Where |
|---|---|---|
| New lead (manual, API, Meta, OLX, Imovelweb) | `lead_novo` | SW `leads_service.create_lead` via `lead_notice.avisar_lead_novo` |
| Bulk lead import finished | `leads_importados` | SW importer `commit` (one summary) |
| Vista sync applied changes | `imoveis_vista_sincronizado` | SW Vista sync (one per run, only when N > 0) |
| Approval pending | `imovel_aprovacao_pendente` | SW Vista divergence approval |

Deferred: WhatsApp-inbox intake lead (`NOC-REMEDIATE[lead-novo-whatsapp-intake]`, in `lead_notice.py`).

## Frontend

- `NotificationBell` (`@noctusai/lib/design-system`), mounted on every authenticated page; count from `/contagem`, list from `/api/notificacoes`.
- A seed hook polls about every 15 s while the tab is visible (and on focus) and shows ONE neutral pop-up per unread item newer than the session high-water mark (max 3, rest collapsed into "+N novas notificacoes"); the first load never toasts the backlog. `<Toaster>` has `closeButton`.
- Feedback toasts stay sonner green/red with X (see `../frontend/frontend.md` Toasts).

---

See also: `../04-SHARED-LIBRARY.md` - `backend.md` - `../frontend/frontend.md` (Toasts)
