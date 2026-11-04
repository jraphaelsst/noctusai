# Notifications — frontend mechanics (live pop-up, bell, shell mount)

> **Definitions live elsewhere.** The two classes (feedback vs operational), the row shape (`metadata`, `kind`, limits), recipients and which events must notify are defined ONCE in `KB § PATTERNS/backend/notifications.md`. This doc is only what the seed frontend does with them; products write none of it.

## What the seed does (products consume)

- `<Toaster richColors closeButton>`, mounted once by `createProductApp`: feedback toasts (`toast.success` / `toast.error`) keep green/red and get an X.
- `toastOperacional({ title, message, link, onOpen })` (`@noctusai/lib`): the neutral pop-up for operational notices (card tokens, X, ~8 s, pauses on hover, click → `onOpen`). Never hand-roll a green/red toast for an operational event.
- `useLiveNotifications` (`live-notifications.ts`): reads the SAME list the bell shows (`useNotificacoes(1, 10)`, polled every `NOTIFICATION_POLL_MS` = 15 s while the tab is visible, plus on focus), so there is one request.
  - High-water mark: the first load of a session never toasts the backlog; only unread, unseen notices created after the mark toast.
  - At most 3 pop-ups at once; the rest collapse into "+N novas notificações".
  - A hidden tab defers; `visibilitychange` flushes.
  - Click marks read and opens `metadata.link`; another product's link goes through `createOpenInProduct` (core's SSO launch URL).
- Shell mount: `createProductApp` mounts `ShellNotifications` ONCE for authenticated users, fed by `appConfig.notifications` (`{ hooks, onNavigateProduct }`, filled by `infra.appConfig`). A product that does not spread `infra.appConfig` into `createProductApp` gets nothing; core passes its own (`components/NotificationBell.tsx` exports `notificationHooks` + `openInProduct`).
- Bell on every authenticated page: the page/layout bell where there is one, otherwise the shell's floating fallback (`useNotificationBellMounted`; the fallback passes `countAsMounted={false}`, else it counts itself and unmounts in a loop). The list refetches when the bell opens, and shows an error state, not "nenhuma".

## Auth-ready seam

Every notification query is gated on `useAuthReady()`. A CUSTOM auth provider (core) never runs the seed providers that call `markAuthReady()`, so its queries stayed disabled forever (empty bell, badge 0, never polled; found 2026-11-04). `createProductApp` bridges it at the auth seam (`AuthReadyBridge`, inside the `AuthProvider`, calls `markAuthReady()` when `useAuth().isInitialized`) — not in a notifications component.

Tests: `seed/lib/frontend/src/live-notifications.test.tsx`, `…/NotificationBell.test.tsx`, core `e2e/tests/notifications.spec.ts`.
