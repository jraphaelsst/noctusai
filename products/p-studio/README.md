# P Studio — Operação e Financeiro

Sistema de operação e finanças de uma produtora de fotografia e audiovisual
imobiliário. Uma imobiliária pede mídia de um imóvel → o negócio é orçado e
negociado → aprovado, vira uma **captação** agendada (com checklist de
equipamentos) → o material entra no pipeline de **produção** (backup → seleção
→ edição → revisão) → é **entregue** → e a entrega gera um **lançamento**
financeiro que é cobrado até ser recebido.

Construído **nos moldes de um produto NoctusAI** para futura absorção pela
plataforma principal: frontend Vite + React SPA, backend FastAPI, schema
Postgres próprio (`p_studio`) no Supabase compartilhado da plataforma, RLS por
organização, migrations SQL numeradas e convenções pt-BR. Mesmo precedente do
`dilidu/`.

> Este é o **rebuild**. O protótipo Lovable (`cadu/realty-lens-pro/`) está
> **congelado e é somente leitura** — escrever nele sincroniza de volta para o
> editor da Lovable. O conhecimento extraído dele vive em
> `cadu/_NOC_ABSORPTION/`.

## Como rodar

Um container, um comando — o modelo da casa. Da raiz do monorepo:

```bash
./start.sh p-studio
```

As portas vêm do registry `PRODUCTS` em `start.sh`
(`p-studio:P Studio:8014:8180`), que é a **fonte única** de porta por produto:
backend **8014**, frontend dev **8180**. `frontend/vite.config.ts` não repete a
porta do backend — o factory a deriva do registry, justamente para as duas não
poderem divergir.

Antes da primeira subida, copie os dois `.env.example`:

```bash
cp products/p-studio/backend/.env.example  products/p-studio/backend/.env
cp products/p-studio/frontend/.env.example products/p-studio/frontend/.env
```

O `.env` do backend precisa de `SUPABASE_URL` / `SUPABASE_ANON_KEY` /
`P_STUDIO_ORG_ID` (namespaced desde `1868357f` — `ORG_ID` puro era um footgun
no `.env` compartilhado da frota). O do frontend precisa de `VITE_CORE_URL` e
`VITE_CORE_API_URL` além do par do Supabase: sem elas o `SSOCallback` do seed
cai no default `http://localhost:8000` e o login SSO falha com um
"Failed to fetch" que não nomeia a causa.

## Portas

| Processo | Porta | Fonte |
|---|---|---|
| Backend FastAPI | **8014** | registry `PRODUCTS` em `start.sh` |
| Frontend Vite (dev) | **8180** | registry `PRODUCTS` em `start.sh` |

As portas **8020** (backend) e **5176** (frontend) eram do produto PRÉ-absorção
e não existem mais em lugar nenhum — a migration
`004_url_base_porta_da_casa.sql` moveu `url_base` para a porta da casa e diz
isso explicitamente. Se você as encontrar em algum lugar, é drift; corrija.

CORS de desenvolvimento sai do mesmo registry
(`noctusai_lib.config.cors_registry.derive_cors_origins`), não de uma lista
mantida à mão — o mesmo mecanismo que, em produção, deriva a allowlist do
bridge de SSO no core.

## Credenciais de desenvolvimento

A migration `002_plataforma_e_seeds.sql` provisiona um admin local
(`admin@pstudio.local`, senha `senha123` no arquivo). **Num banco novo essa
conta não sobrevive**: a `007_remover_admin_de_desenvolvimento.sql` roda logo
depois e a remove — de propósito, porque as migrations deste produto rodam
contra o Supabase de PRODUÇÃO, compartilhado pela frota, e uma conta
admin/owner rotulada como "de desenvolvimento" não tem o que fazer lá.

Para entrar em ambiente local, provisione um usuário pelo fluxo normal da
plataforma (convite — `p_studio.invitations`, migration `006`).

⚠️ A conta semeada foi removida do banco vivo em **2026-08-17**; ela existia
desde 2026-08-13. A senha viva **não** era `senha123` (conferido em
2026-08-14 — ver `project-history/roadmaps/p-studio-2026-08.md`
§ Known hazards); o arquivo da `002` não é registro fiel do que rodou. O
protótipo Lovable gravou a senha real do dono do estúdio no histórico do git
— ver `_NOC_ABSORPTION/01-DATA-MODEL.md` § Security findings. Essa senha
precisa ser rotacionada.

## Arquitetura

- **Banco:** Supabase da plataforma NoctusAI, schema `p_studio`. Migrations em
  `backend/migrations/` (`001_p_studio_schema.sql`, `002_plataforma_e_seeds.sql`).
- **Auth:** Supabase Auth. O usuário é membro da org “P Studio” em
  `public.noctus_users` — é isso que faz `public.current_org_id()` resolver.
- **RLS por organização:** toda tabela carrega `org_id` e a política é
  `USING (org_id = public.current_org_id())`. O backend sempre consulta com o
  JWT do usuário, então a RLS vale de ponta a ponta. O `ORG_ID` do `.env` é
  conveniência para carimbar INSERTs — não é o controle de acesso.
- **API:** FastAPI REST em `/api/*` — 58 rotas, routers por domínio
  (`clientes`, `imoveis`, `servicos`, `equipamentos`, `negocios`, `captacoes`,
  `producoes`, `financeiro`, `dashboard`, `me`).
- **Frontend:** Vite + React 18 + react-router + Tailwind v3, primitivos de UI
  próprios (`src/components/ui.tsx`), react-query em `src/hooks/useApi.ts`.
  **Zero mock** — toda tela lê e escreve nos endpoints reais.

### Domínios (11 tabelas)

```
clientes ──┬── imoveis ──┐
           │             │
           └── negocios ─┴─── negocio_servicos ── servicos
                  │
                  ├── captacoes ──── captacao_equipamentos ── equipamentos
                  ├── producoes ──── producao_eventos
                  └── lancamentos
```

`negocios` é a espinha. Os três pipelines (comercial, produção, financeiro)
penduram nele e avançam **independentemente** — por isso são tabelas separadas
com colunas de status próprias, e não um campo `status` em `negocios`.

## Telas

| Rota | Tela | Módulo da spec |
|---|---|---|
| `/` | Dashboard executivo | 1 |
| `/crm` | CRM Comercial (kanban de 9 etapas) | 2 |
| `/agenda` | Agenda operacional (dia/semana/mês + checklist) | 3 |
| `/producao` | Pipeline de produção (kanban de 8 etapas + histórico) | 4 |
| `/imoveis` | Cadastro de imóveis | 5 |
| `/servicos` | Serviços contratados | 6 |
| `/financeiro` | Gestão financeira | 7 |
| `/clientes` | Gestão de clientes (com métricas calculadas) | 8 |
| `/equipamentos` | Equipamentos | extra |
| — | Sistema de status por cor | 9 |

O módulo 10 (“automações futuras”: Google Calendar, WhatsApp, Drive, Stripe,
PIX) é explicitamente futuro — a arquitetura guarda as costuras (services
donos do IO), nada foi construído.

## Testes

**Backend** (pytest, em `backend/`):

```bash
./venv/bin/python -m pytest
```

**Frontend** (Vitest + Testing Library, em `frontend/`):

```bash
npm test
npm run test:watch
```

## Absorção pela plataforma NoctusAI

Passos restantes: mover `frontend/`+`backend/` para `products/p-studio/` no
monorepo, trocar `main.py` por `create_product_app()` do `noctusai_seed`, os
primitivos de UI pelos de `@noctusai/lib` e o login local pelo SSO do Core.
Ver `MASTER-PROMPT.md` para o guia de desenvolvimento completo.
