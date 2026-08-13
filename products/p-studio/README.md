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

Dois processos (ou use `./dev.sh`, que sobe os dois):

```bash
# Backend (porta 8020)
cd backend
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt   # 1ª vez
cp .env.example .env    # preencha SUPABASE_URL / SUPABASE_ANON_KEY / ORG_ID
./venv/bin/uvicorn app.main:app --reload --port 8020

# Frontend (porta 5176)
cd frontend
npm install    # 1ª vez
cp .env.example .env
npm run dev
```

Acesse **http://localhost:5176**.

## Portas

| Processo | Porta |
|---|---|
| Backend FastAPI | **8020** |
| Frontend Vite | **5176** |

O backend só aceita CORS de `http://localhost:5176` por padrão
(`backend/app/config.py` → `cors_origins`). Se mudar a porta do frontend, mude
`CORS_ORIGINS` no `.env` do backend junto.

Nenhuma das duas colide com o registro de portas da plataforma
(`noctusai/start.sh`, que hoje usa 8000–8012 nos backends e 5173/8080–8160 nos
frontends) nem com o `dilidu` (8010/5175). Vale registrar, porém, uma colisão
**pré-existente e alheia a este produto**: `dilidu` roda o backend na 8010, que
é a mesma porta do `orbity` dentro do monorepo — os dois não sobem juntos.

## Credenciais de desenvolvimento

A migration `002_plataforma_e_seeds.sql` provisiona um admin local:

| Email | Senha |
|---|---|
| `admin@pstudio.local` | `senha123` |

⚠️ Só para ambiente local. Em produção o usuário é provisionado pelo fluxo
normal da plataforma. (O protótipo gravou a senha real do dono do estúdio no
histórico do git — ver `_NOC_ABSORPTION/01-DATA-MODEL.md` § Security findings.
Essa senha precisa ser rotacionada.)

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
