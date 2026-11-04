# Notification classes — feedback (green/red) vs operational (neutral)

> **Rule.** There are exactly two kinds of in-app notice. Pick by ONE question: *did the user just do something that produced this result?*
>
> | Class | Use it for | Channel | Look |
> |---|---|---|---|
> | **Feedback** (system) | the result of an action the user just took: saved, failed, error | `toast.success` / `toast.error` (sonner), client only, no DB row | green / red (`richColors`), with an X close |
> | **Operational** | something that happened which the user did not trigger: new lead, Vista sync applied, approval pending | an in-app row via `noctusai_lib.domain.notifications.write_in_app` → bell list **and** a live neutral pop-up | neutral (no green/red), title + message, X close, ~8 s auto-dismiss (pauses on hover), click opens `metadata.link` |
>
> WhatsApp and e-mail are never the default for operational notices; each needs an explicit owner decision per event.

## Backend — writing an operational notice

`write_in_app(core, user_ids, kind, title, message, metadata, org_id)`:

- `metadata` = `{"categoria": "operacional", "link": "/relative/path" | null, "produto": "<slug>", "entidade": {"tipo": "lead"|"imovel"|…, "id": "<id>"} | null}`.
- `kind` is snake_case pt-BR (`lead_novo`, `imoveis_vista_sincronizado`, `imovel_aprovacao_pendente`); `title` ≤ 60 chars, `message` ≤ 160; no PII beyond a name (never a phone / e-mail).
- Recipients come from ONE seed helper in `noctusai_lib.domain.notifications` (never per product). An empty recipient set logs WARNING and returns 0 — a notice never fails the caller.

## Frontend — what the seed already does (products write nothing)

- `<Toaster richColors closeButton>` — mounted once by `createProductApp`; feedback toasts get an X.
- `toastOperacional({ title, message, link, onOpen })` (`@noctusai/lib`) — the neutral pop-up. Never hand-roll a green/red toast for an operational event, and never use `toast.success` for "a lead arrived".
- `useLiveNotifications` — mounted ONCE in the authenticated shell (`createProductApp` ← `infra.appConfig.notifications`). It reads the bell's own list (poll ~15 s while the tab is visible, plus on focus): the first load of a session never toasts the backlog (high-water mark), at most 3 pop-ups at once, the rest collapse into "+N novas notificações". Click → marks read and opens `metadata.link` (cross-product via `createOpenInProduct`, i.e. core's SSO launch URL).
- The bell is on every authenticated page: a header bell where the layout has one, otherwise the shell's floating fallback (`useNotificationBellMounted`). The list refetches when opened.
- A product that does not spread `infra.appConfig` into `createProductApp` gets neither the pop-ups nor the fallback bell: pass `notifications: { hooks, onNavigateProduct }`.

## Why (2026-11-04)

The owner got no "new lead" pop-up and "the bell doesn't open". Root causes found in a real browser: (1) core never flips the global `useAuthReady()` signal (a custom auth provider skips the seed providers that do), so every notification query stayed disabled forever: empty list, badge 0, never polled; (2) nothing turned a new backend notice into a pop-up; (3) core pages without their own header had no bell at all. The dropdown itself opened fine (hit-test verified) — stacking was not the cause.

Tests: `seed/lib/frontend/src/live-notifications.test.tsx`, `…/NotificationBell.test.tsx`, core `e2e/tests/notifications.spec.ts`.
