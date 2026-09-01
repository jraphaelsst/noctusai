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

1. **Comercial** — public pré-qualificação form, lead triage, calculadora de
   escopo, orçamentos, contrato em PDF, assinatura (dry-run seam).
2. **Marca** — identidade visual, tom de voz, linhas editoriais, personas, and
   the Cofre de Acessos (Fernet-encrypted at rest). A persistent sidebar shows
   the palette and tone next to whatever the designer is working on.
3. **Calendário** — editorial calendar, drag to reschedule, copy + peças.
4. **Esteira** — the 8-step rigid kanban, play/pause timesheet, Contador de
   Refações, and the white-label `/aprovar/:token` portal. This is the MVP.
5. **Distribuição** — publishing queue, per-channel credentials, BI de
   eficiência (refação rate + real cost per client).
6. **Financeiro** — faturas, itens excedentes, DRE with margin per account,
   inadimplência.

**Custos** underpins 1, 5 and 6: the funções + profissionais table that defines
what an hour actually costs. Without a rate there, those three report R$ 0,00.

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

## Tests

```bash
cd products/igig/backend  && pytest           # 330
cd products/igig/frontend && npx vitest run   # 56
cd products/igig/frontend && npx vite build
```
