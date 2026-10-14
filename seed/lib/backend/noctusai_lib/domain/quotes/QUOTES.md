# Quotes organ (`noctusai_lib.domain.quotes` + `@noctusai/lib` `quotes/`)

Roadmap `project-history/roadmaps/erp-seed-2026-10.md` E2/W4. Mined from three products (N=3):

| Feature | igig `orcamento` | erp-imobiliario `propostas` | social-wiring `atendimento_propostas` | Organ |
|---|---|---|---|---|
| status flow | rascunho/enviado/aceito/recusado/expirado/substituido | enviada/em_analise/contraproposta/aceita/recusada/expirada | rascunho/enviada/aceita/recusada/cancelada | `draft/sent/viewed/accepted/rejected/expired/superseded` |
| versions | `nova-versao`, previous -> substituido | counter-proposal (value only) | one accepted per atendimento | `root_id` + `version`, one `is_current`, one `accepted` per root (DB) |
| validity + lazy expiry | `validade`, flips on read | `prazo_validade` (never expires) | `validade_ate` | `valid_until`, persisted lazy flip + `expire_due` |
| lines + discount | items, header discount | single `valor_proposta` | JSON snapshot | lines (item or free text) + line and header discount |
| PDF / e-mail | PDF in bucket, SMTP | - | - | PDF on demand (xhtml2pdf call site), e-mail via `EmailSender`, DOCX via host template |
| accept | staff-only `aceitar` | staff status PATCH | staff `aceitar` | staff **and** public signed link, with a consent record |
| convert | funnel "fechado" + pautas | - | materialise into live negotiation set | `QuoteAcceptHandler` seam (order / contract) |

**Left out on purpose (domain, not generic):** igig recurrence (weekday bitmask x qty x 4), cost/margin from team hourly rate and
calendar "pautas"; erp-imobiliario `imovel_id`, counter-proposal value and `historico` JSON (the organ keeps an append-only
`quo_events` instead; a counter-offer is a new version); social-wiring parcelas/favorecidos/intermediarios/testemunhas JSON
snapshots (a vertical's `QuoteAcceptHandler` materialises its own terms). Hosts attach domain data through the handler, not columns.

## Invariants the database holds
* A quote that left `draft` is frozen (commercial columns + lines): a revision is a new version.
* `quo_acceptances` (consent: who, when, IP, UA, the exact sentence, sha256 of the terms) and `quo_events` are append-only;
  one decision per version.
* Composite org FKs: a quote cannot name another org's party; a line/acceptance cannot name another org's quote.
* Money is `BIGINT` cents; `total = subtotal - discount` is a CHECK. Numbers come from `quo_next_number` (atomic, per org).

## The public link
`commerce.access_links` HMAC token, purpose `quote_accept`, org + quote bound, TTL capped at the validity day. Every bad token is
the same 404 `link_invalido`. The output is an allow-list (`public.py`): the customer's NAME, the offer, never document / e-mail /
phones / internal ids. Rate limits are the host's (`rate_limit=limiter.limit`); the recorded IP is the host's `client_ip`.

## Convert-on-accept
Accept = claim (conditional UPDATE) -> record (append-only) -> handler. Handler failure is stored (`conversion_status=failed`) and never
undoes the acceptance; `POST /{id}/convert` retries (handlers MUST be idempotent on `quote.id`). No handler wired => `skipped`.
Contracts / commerce-order handlers are wired by the host; this organ imports neither.

## Not yet (named destinations)
NOC-REMEDIATE[quotes-signature-webhook-route]: `esign.apply_signature_event` is the entry point, but the provider webhook ROUTE
(secret + URL) is the host's; no seed route yet. — 2026-10-14
