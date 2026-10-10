# Email marketing P1b: unsubscribe injection, step executor, domain verification + click tracking, double opt-in

The owner decided on 2026-10-10 that the four capabilities neither the retired `mailing` product nor
`app/modules/email_marketing` ever had get built in social-wiring's own engine. This note pins the
contract BEFORE code (contract-first). It is seed-first: anything generic goes in the seed with
Fake + Real + factory.

Slices ship in this order, one at a time. All four are the same collision class
(`app/modules/email_marketing`), so none run in parallel:
**(a) unsubscribe injection → (b) step executor → (c) domain verification + click tracking → (d) double opt-in**.
Every new owner-visible page or nav entry ships with `status_pagina='desenvolvimento'`.

## 0. What the seed already ships (reused, not rebuilt)

| Need | Seed piece | Note |
|---|---|---|
| Background execution | `noctusai_lib.domain.jobs`: `Worker`, `WorkerHandle`, `JobRepository` (+ `RescheduleLater`, `DeadLetterError`) | SW already has `social_wiring.jobs` (migration 121) and runs workers for edicao_fotos / transcricoes. |
| Transactional email (confirmation mail) | `noctusai_lib.integrations.email`: `EmailSender` Protocol, `FakeEmailSender`, `SmtpEmailSender`, `make_email_sender` | There is **no Resend transactional adapter**, so (d) adds one to the seed. |
| Consent catalog | `register_feature` / `consent_required` | Not needed by P1b. Nothing here calls an LLM. |
| Webhook signatures | `noctusai_lib.security.webhook_signatures` | Already used by the Resend webhook, which is fail-closed since P1(1). |

**New in seed (generic):**
- `noctusai_lib.security.signed_tokens`: an HMAC token bound to a *purpose* (`unsubscribe`,
  `email_confirm`, `click`), with an optional expiry and constant-time verification. Today
  `routers/unsubscribe.py` hand-rolls an HMAC. It moves onto this module, and existing unsubscribe
  tokens keep verifying through a legacy-format fallback.
- `noctusai_lib.integrations.email.resend_adapter.ResendEmailSender`: the Real for the existing
  `EmailSender` Protocol, selected by `make_email_sender` when `resend_api_key` resolves.
- `noctusai_lib.integrations.resend.domains`: Protocol + `FakeResendDomains` + `HttpResendDomains` +
  factory, covering `create(domain)`, `get(id)` and `verify(id)` against the Resend Domains API.
  Any product that sends from its own domain needs it.

## (a) Unsubscribe-link injection (LGPD, one click)

- **Rendering.** `SendService` renders every email. If the template lacks `{{unsubscribe_url}}`, it
  appends a pt-BR footer with the contact's link, so the link is *always present by construction*.
  The P1(1) guard stays as the backstop: a live batch whose rendered body lacks the link is still
  refused. The template tag remains supported for custom placement.
- **One click.** Live emails carry `List-Unsubscribe: <url>` plus
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058).
  `POST /api/email-marketing/unsubscribe/{token}` with the form body `List-Unsubscribe=One-Click`
  succeeds with no page interaction.
- **Endpoints.** Unchanged: `GET`/`POST /api/email-marketing/unsubscribe/{token}`. Invalid token →
  400 (body `{"detail": ...}`). Success → `{"ok": true, "email": ...}`. Idempotent: a second POST
  returns 200 `{"ok": true, "already": true}`.
- **State after.** `contacts.status='unsubscribed'`, `unsubscribed_at` is set, an `unsubscribes`
  row with reason `link_click`, and later sends exclude the contact (they are already filtered to
  `status='active'`).
- **Config.** `FRONTEND_BASE_URL` is required for live sends. Without it, the send is refused with
  `UNSUBSCRIBE_REFUSAL`, unchanged.

## (b) Automation step executor

- **Driver.** A seed `Worker` (handler `email_marketing.automation_step`) plus a `WorkerHandle`
  started in the module's lifespan hook. No hand-rolled loop: the existing 5-minute scheduler
  scan only **enqueues** due enrollments as jobs (idempotency key `enrollment_id:step_id`).
- **Step semantics** (`automation_steps.tipo`, `config` JSONB):

| tipo | config | effect | next |
|---|---|---|---|
| `send_email` | `{template_id}` | Queues one `send_logs` row (`automation_id`, `automation_step_id`). It is sent by the same pipeline, so every guard applies (dry-run, unsubscribe). | Next step, immediately. |
| `wait` | `{hours}` or `{days}` | Sets `next_action_at`. | `RescheduleLater` until due. |
| `condition` | `{field: "tag"\|"status"\|"opened_campaign", op, value, then_posicao, else_posicao}` | Evaluates the contact. | The branch's `posicao`. |
| `add_tag` / `remove_tag` | `{tag}` | Updates `contacts.tags`. | Next step. |
| `move_to_list` | `{list_id}` | Upserts `contact_list_members`. | Next step. |
| `webhook` | (any) | **Not supported.** The enrollment goes to `status='paused'` with an explicit reason in the job's dead letter, never a silent skip. | — |

- **Exit.** A contact that is no longer `active` (unsubscribed, bounced or complained) is
  `exited`. The last step → `completed` with `completed_at`.
- **Errors.** A transient error retries through the seed `RetryPolicy`. A malformed config is a
  `DeadLetterError` and the enrollment is paused with the reason.

## (c) Sender-domain verification + click tracking

- **Domains.** `POST /settings/domains` calls the Resend Domains API `create` and stores
  `resend_domain_id` plus the returned `dns_records` (SPF/DKIM/DMARC). The response carries the
  records to configure. `GET /settings/domains/{id}/verify` calls `verify`, then `get`, and maps
  the result to `pending|verified|failed` with `verified_at`. Without `resend_api_key` → 503 with
  a clear message (no fake "verified").
- **Click tracking.** In live sends, `href`s in the rendered HTML (http/https only, never the
  unsubscribe link or `mailto:`) are rewritten to `/api/email-marketing/t/c/{token}`. The token is
  a `signed_tokens` purpose `click` carrying `{send_log_id, url}`.
  `GET /api/email-marketing/t/c/{token}` → inserts a `link_clicks` row (url, user_agent, ip),
  sets `send_logs.clicked_at` / `status='clicked'` if not already, then **302 to the signed url**.
  An invalid or forged token → 400. **No open redirect:** the target only comes from a signed
  token.

## (d) Double opt-in

- **Schema.** New columns are additive and do not touch the shared `contacts.status`, which
  WhatsApp contacts use too (migration 015): `contacts.email_optin` (`'not_required'` default for
  existing rows, `'pending'`, `'confirmed'`) and `email_confirmed_at`.
- **Flow.** A contact created through `source in ('form','api')`, or by import with
  `double_opt_in=true`, starts `pending`. A confirmation email goes out through the seed
  `EmailSender` (Resend Real / Fake in tests) with a `signed_tokens` purpose `email_confirm` link
  to `/confirmar-email/{token}` (a public FE page). `POST /api/email-marketing/confirm/{token}` →
  `confirmed` + `email_confirmed_at`.
- **Send gate.** Campaign recipients and automation `send_email` steps exclude `pending` contacts,
  by construction in recipient resolution.

## Tests per slice

Every slice ships its tests in `tests/modules/email_marketing/`:
- auth boundaries assert strict `== 401`;
- public token endpoints get forged / expired / valid cases;
- the seed pieces get Fake + Real tests in `seed/lib/backend/tests`;
- migrations pass `migration_replay` (applied twice);
- FE pages get vitest tests.
