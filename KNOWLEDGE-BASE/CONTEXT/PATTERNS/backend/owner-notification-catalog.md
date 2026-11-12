# Owner-notification catalog — every "warn me" is a declared, switchable WhatsApp notification

**Born 2026-11-09.** The Vista sync marked 45 properties as gone from Vista (3 of them exclusives) and only wrote
DB columns. The owner, verbatim: "i should've received a notification via whatsapp. the whatsapp scripted message
notification system we have. this is what i mean when i say 'warn me' or 'notify me' in those processes."

## The rule

1. When the owner asks to be **warned / notified / avisado** about a process, that means a **WhatsApp scripted
   message** to him, shipped in the same change as the process. A DB row, a registry flag, a log line or the admin
   bell alone is not a warning.
2. Every owner-facing notification is a **declared kind** in the product's `notification_kinds.py`
   (`noctusai_lib.domain.notification_catalog.declare_kinds`). Sending an undeclared kind raises
   `UndeclaredNotificationKind`, so a missing declaration fails in tests rather than silently in production.
3. The owner can **switch every kind off per product** on core's admin page **Notificações** (`/admin/notificacoes`).
   The page also shows how each kind behaved in the last 30 days, so he can validate it in daily use.

## Mechanism

| Piece | Where |
|---|---|
| Declarations + gate (Protocol, `FakeNotificationGate`, `SupabaseNotificationGate`, `make_notification_gate`) | `seed/lib/backend/noctusai_lib/domain/notification_catalog/` |
| Gate installed per product (Fake under pytest), declared kinds registered at boot | `seed/framework/backend/noctusai_seed/app.py` §3c + lifespan |
| Owner line (the sender): `notify_owner`, recipients source, WAHA transport, `make_owner_line`; installed at boot next to the gate | `notification_catalog/owner_line.py` + `app.py` §3c-bis |
| Tables: `public.notification_kinds` (the switch; `enabled` is never written by the upsert) · `public.notification_sends` (one row per dispatch decision: sent / partial / failed / suppressed / no_recipient; no message text, no phone numbers) | core migration `117_notification_catalog.sql` |
| Admin API `/api/admin/notifications` (platform tier) + page `AdminNotificacoes.tsx` | `products/core/` |
| SW kinds + the two send paths that pass the gate: `NotificationService._dispatch` (roster `notification_recipients`) and `julia_relatorio_service._gerar_e_entregar` (Julia's report destination) plus the Vista divergence digest | `products/social-wiring/backend/app/services/` |

**Failure posture — fail toward warning.** If the switch can't be read, the gate logs an ERROR and sends anyway.
A ledger write that fails is logged and never raises. Products cache the switch for 60 s, and the page says so.

## Owner line

NoctusAI's own WhatsApp number (L3) sends every owner notification for every product; a client's line is never used.
Contract: `projects/noc-whatsapp-lines/owner-line-CONTRACT.md`. A product calls

```python
from noctusai_lib.domain.notification_catalog import notify_owner
notify_owner("agents", "eval_loop_parada", texto)   # -> OwnerDispatch(status, recipients, delivered, reason)
```

It runs `gate.allowed` -> recipients (core `public.notification_owner_recipients`, 60 s cache) -> one WAHA send per
recipient -> `gate.record`. It never raises (an undeclared kind does). No transport configured records `failed` /
`linha_noc_nao_configurada` and logs `seed.owner_line.nao_configurada` at ERROR. Env: `NOC_OWNER_LINE_WAHA_URL`,
`NOC_OWNER_LINE_WAHA_SESSION` (default `default`), `NOC_OWNER_LINE_WAHA_API_KEY`, `NOC_OWNER_LINE_EXPECTED_NUMBER` (E.164 of NoctusAI's own number); unset URL = no transport. URL set without the expected number = no transport (`linha_noc_numero_nao_declarado`); on first send the session's paired number is checked against it (`linha_noc_numero_divergente` = nothing sent).

## Adding a notification (the checklist)

1. Declare the kind (pt-BR `titulo`, `descricao`, `gatilho`: what arrives and exactly what triggers it).
2. Send it through the product's gated path (in SW: a `NotificationService.notify_*` method that calls `_dispatch`).
3. Avoid repeats: dedupe or warn on a state *transition*, never on every cron tick (see `imoveis_sync_falhou`).
4. Test the switched-off path (`suppressed`, nothing sent) and the no-recipient path (`no_recipient` is recorded,
   never silent).

## One owner number, every live product on the page (W1-D, 2026-11-12)

- **One owner number, in core.** `public.notification_owner_recipients` is the only list of owner numbers (core page
  Notificações → "Quem recebe os avisos"). Anything that needs "the owner's number" READS it — Agents' hand-off number
  (`RuntimeSettingsService.numero_fallback_atendimento`) is the first active recipient, read-only on its page. Core
  migration `121_owner_number_one_source.sql` copied the old agents value into core, straight from that row (no number
  in code or migrations).
- **Every live product is on the page.** `notification_catalog_service.live_roster` adds each `ativo` + `deploy_scope='live'`
  product (and `core`) even when it declares no kind, so "this product warns the owner about nothing" is visible
  (`declared: false`) instead of the product vanishing.
- **Reasons ride with the notice.** Julia's `opt_out` action carries the agent's own `motivo_texto`; SW's owner notice shows
  it (the closed `motivo` enum is only the fallback).
- **skill-scout notices are WhatsApp-only**: core declares `skill_scout_novo_skill` (`canais=("whatsapp",)`) and sends it
  through `notify_owner` (`skill_scout_notice_service`, `POST /api/admin/notifications/skill-scout`).

## Open follow-ups

- Bell-only owner alerts that the owner has **not** asked for by name stay bell-only until he chooses. The candidate
  list is in `project-history/owner-notifications/` (2026-11-09 sweep).
- `NOC-REMEDIATE[notification-sends-retention]` in migration 117.
- A second product that sends owner WhatsApp messages calls the same seed gate; there are no per-product copies.

Related: `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md`.
