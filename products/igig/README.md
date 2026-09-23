# IgIg

ERP for a communication agency — CRM and orçamentos, Central da Marca, editorial
planning, the creative production line with a white-label client approval
portal, distribution and metrics, and financeiro with retainers and DRE.

Built on the NoctusAI seed (`noctusai_lib` + `noctusai_seed` backend,
`@noctusai/lib` + `@noctusai/seed` frontend).

> **Note.** This README previously described IgIg as a "minimal reference
> implementation — the spine with no organs" and named it the source of truth
> for `templates/product-seed/`. Both statements were left over from scaffold
> day and are wrong: IgIg is a six-módulo domain product, and the template's
> source is `products/seed/`.

## Stack

- **Backend**: FastAPI via `create_product_app()` (port 8013)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` (port 8170)
- **Database**: Supabase, schema `igig` — RLS on every table
- **Auth**: SSO + direct login
- **Spec**: `IgIg Agency/PROJETO-IGIG-ERP.md`

## Módulos

1. **Comercial** — a public pré-qualificação form + a lead triage funnel
   (`PipelineBoard`, org-editable stages); closing a deal REQUIRES an
   accepted orçamento (creates the Cliente + the calendar's pautas). Lost
   deals archive off-board with a reason. Automações v1 (stage-entry / SLA
   rules) and lead sources (WhatsApp via WAHA, Meta Lead Ads) feed the funnel
   automatically; an "Assistente" (Claude via the seed LLM seam) drafts a
   resumo / próxima ação / mensagem per negócio.
2. **Orçamentos** — versioned proposals over the **Produtos e Serviços**
   catalogue (weekday-bitmask recurrence, server-computed totals + estimated
   margin), a professional PDF, e-mail send (SMTP + Gmail reply watch) and
   contrato generation (digital dry-run seam or física, hand-signed).
3. **Marca** — identidade visual, tom de voz, linhas editoriais, personas, and
   the Cofre de Acessos (Fernet-encrypted at rest). A persistent sidebar shows
   the palette and tone next to whatever the designer is working on.
4. **Calendário** — editorial calendar, drag to reschedule, copy + peças; an
   accepted orçamento's recurring itens auto-generate the month's pautas.
5. **Esteira** — the 8-step rigid kanban, play/pause timesheet, Contador de
   Refações, and the white-label `/aprovar/:token` portal.
6. **Distribuição** — publishing queue, per-channel credentials, BI de
   eficiência (refação rate + real cost per client).
7. **Financeiro** — faturas, itens excedentes, DRE with margin per account,
   inadimplência, monthly competência closing, and PDF/CSV relatórios
   (comercial funnel + financeiro).
8. **Integrações** — per-canal setup screen: social channels, SMTP/Gmail,
   WAHA/Meta lead sources — nothing ever echoes a stored secret back.

**Custos** underpins 1, 6 and 7: the funções + profissionais table that
defines what an hour actually costs. Without a rate there, those report
R$ 0,00 (and an orçamento's estimated margin has no denominator).

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8013 --app-dir products/igig/backend

# Frontend
cd products/igig/frontend && npm run dev
```

Both read the repo-root `.env`. Running from a git worktree needs that file
symlinked in (`ln -s <primary>/.env .env`) — vite's `envDir` points at the tree
root, and without it the SPA renders blank with no console error.

`IGIG_COFRE_KEY` must be set; the app refuses to boot without it rather than
writing credentials in plaintext.

### E-mail (orçamento send + Gmail reply watch)

Per-org SMTP + Gmail are set on **Integrações → E-mail** and stored encrypted
in `igig.integracao` (canais `smtp` / `gmail`). Env (all optional — each gap
is reported loudly, never faked; none is in `required_prod_config`):

| Env | Purpose | Unset ⇒ |
|---|---|---|
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` (+ `SMTP_SECURITY` `SMTP_FROM_EMAIL` `SMTP_FROM_NAME`) | platform SMTP fallback for an org with no account; shown as `origem: "plataforma"` | send answers 409 `smtp_nao_configurado` |
| `GOOGLE_OAUTH_CLIENT_ID` `GOOGLE_OAUTH_CLIENT_SECRET` | Gmail OAuth (scopes `gmail.send` + `gmail.readonly`) | connect answers 503 |
| `PRODUCT_URL_IGIG` (or `PRODUCT_URL_PATTERN`) | OAuth redirect URI `<url>/api/integracoes/email/gmail/oauth/callback` + the post-connect redirect | connect answers 503 |
| `GMAIL_PUSH_GCP_PROJECT` `GMAIL_PUSH_TOPIC` `GMAIL_PUSH_AUDIENCE` `GMAIL_PUSH_SERVICE_ACCOUNT` | `users.watch` → Pub/Sub push → `POST /api/webhooks/gmail/push` (OIDC-verified) | `configuracao_gcp_ok=false`, no watch, webhook 503 |

The daily watch renewal (`app/scheduler.py`) only runs in a deployed container
(`NOCTUS_SCHEDULERS_ENABLED`). One-time GCP setup: KB § INTEGRATIONS/google.md § 5a.

## Tests

```bash
cd products/igig/backend  && pytest           # 700
cd products/igig/frontend && npx vitest run   # 123
cd products/igig/frontend && npx vite build
```
