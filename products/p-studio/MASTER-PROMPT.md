# P Studio — MASTER-PROMPT

> Guia autoritativo de desenvolvimento deste workspace. Leia antes de mexer em
> qualquer coisa. Onde este documento e o código divergirem, o código venceu —
> corrija este documento.

- Portas: backend **8014** · frontend dev **8180** — do registry `PRODUCTS`
  em `start.sh` (`p-studio:P Studio:8014:8180`), a fonte única. As antigas
  **8020**/**5176** são do produto PRÉ-absorção e não existem mais em lugar
  nenhum desde a migration `004_url_base_porta_da_casa.sql`.
- Schema: `p_studio` · Org slug: `p-studio`
- Idioma: **pt-BR** em domínio, UI, comentários e docs. Inglês só em
  identificador de framework (`useState`, `APIRouter`, `queryKey`).

## O que é o produto

Operação e finanças de uma produtora de fotografia e audiovisual imobiliário.
O cliente é o estúdio; os clientes dele são imobiliárias, corretores e
incorporadoras.

O fluxo, em uma frase: **imobiliária pede mídia → negócio é orçado e negociado
→ aprovado vira captação agendada → material entra na produção → é entregue →
entrega gera lançamento financeiro, cobrado até ser recebido.**

Essa frase é a razão de o modelo ter três pipelines paralelos pendurados num
mesmo negócio.

## Procedência

| | |
|---|---|
| Protótipo | `cadu/realty-lens-pro/` — **CONGELADO, SOMENTE LEITURA** |
| Base de conhecimento | `cadu/_NOC_ABSORPTION/` — 6 docs |
| Precedente estrutural | `dilidu/` |

⚠️ **Nunca escreva em `realty-lens-pro/`.** É um repositório conectado à
Lovable: commits no branch sincronizam de volta para o editor deles. Tudo que
precisava ser extraído já está em `_NOC_ABSORPTION/`.

O protótipo era **portador de especificação, não código para portar**: ~70% das
telas renderizavam arrays hardcoded. O que sobreviveu foi a spec de 10 módulos,
o vocabulário, os tokens de design e três tabelas de cadastro.

## Arquitetura

```
p-studio/
├── README.md          como rodar, stack, portas
├── MASTER-PROMPT.md   este arquivo
├── dev.sh             sobe os dois processos
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI, registro de routers
│   │   ├── config.py        pydantic-settings
│   │   ├── database.py      clientes Supabase (usuário / admin) + execute()
│   │   ├── dependencies.py  guardas de auth → CurrentUser
│   │   ├── routers/         um por domínio, finos — `cadastros` ·
│   │   │                    `captacoes` · `dashboard` · `financeiro` ·
│   │   │                    `integracoes` · `me` · `negocios` · `producoes`
│   │   ├── services/        regra de negócio + IO
│   │   └── schemas/         Pydantic Create / Update / Out por domínio
│   ├── migrations/          001_p_studio_schema.sql, 002_plataforma_e_seeds.sql
│   └── tests/               harness FakeDB, testes de router com status fixado
└── frontend/
    ├── src/
    │   ├── lib/         api.ts · supabase.ts · utils.ts · status.ts
    │   ├── stores/      auth.ts (zustand)
    │   ├── components/  ui.tsx · AppLayout.tsx · Protected.tsx · Kanban.tsx
    │   ├── hooks/       useApi.ts — wrappers react-query
    │   ├── pages/       uma por tela (10)
    │   └── types/       espelho manual dos schemas Pydantic
    └── vite.config.ts, tailwind.config.ts, …
```

### Regra estrutural

- **Router fino, service gordo.** O router valida entrada (Pydantic), chama um
  método de service e devolve. Nenhuma regra de negócio no router.
- **Todo IO mora em service.** É a costura por onde entram as integrações
  futuras (Calendar, WhatsApp, Stripe) sem reescrever nada.
- **O SPA nunca fala com o Postgres.** Só com o backend. Isso é a mudança
  arquitetural mais importante em relação ao protótipo, que consultava Supabase
  direto do browser e por isso não tinha onde colocar agregação nem automação.

## Modelo de dados

Onze tabelas em `p_studio`. Toda tabela carrega `org_id uuid NOT NULL` com RLS
`USING (org_id = public.current_org_id())`.

```
clientes ──┬── imoveis ──┐
           │             │
           └── negocios ─┴─── negocio_servicos ── servicos
                  │
                  ├── captacoes ──── captacao_equipamentos ── equipamentos
                  ├── producoes ──── producao_eventos
                  └── lancamentos
```

Decisões que valem entender antes de propor mudanças:

- **Três status separados, não um.** Um negócio, sua produção e sua fatura
  avançam independentemente. Um `status` único em `negocios` mentiria.
- **`producao_eventos` é log append-only.** A spec pede data, responsável,
  comentário, upload e **histórico de mudanças** por etapa. Log é a forma
  honesta de guardar isso.
- **`lancamentos` é tabela, não status.** Um negócio pode faturar em parcelas, e
  o financeiro precisa agregar através de negócios.
- **`atrasado` é derivado, não armazenado.** Um lançamento faturado com
  vencimento no passado está atrasado *agora*, sem depender de um job noturno. O
  banco guarda 4 status; a API expõe 5 (`status` vs. `status_exibido`).
- **O dashboard não tem tabela.** Cada um dos nove KPIs é uma agregação — é
  precisamente o que só existe porque há backend.

### Convenções de schema

- Tabelas, colunas, rotas e UI em **pt-BR**, snake_case, tabelas no plural.
- Enums como `TEXT` + `CHECK`, não tipo enum do Postgres — estende sem dança de
  migration.
- Dinheiro `NUMERIC(12,2)` (valor de imóvel chega a oito dígitos).
- `TIMESTAMPTZ` para instantes; `DATE` para o que é genuinamente data
  (`data` da captação, `vencimento`).
- Toda tabela: `id uuid PK`, `org_id uuid NOT NULL`, `created_at`, `updated_at`.
- Soft-delete via `ativo boolean` nos cadastros (clientes, serviços,
  equipamentos); delete duro nas transacionais.

## Pipelines (ordem canônica — não reordenar sem migration)

**Comercial (9):** `novo_lead` → `orcamento` → `negociacao` → `aprovado` →
`agendamento` → `producao` → `entregue` → `recebido` → `arquivado`

**Produção (8):** `agendado` → `captado` → `backup` → `selecao` → `edicao` →
`revisao` → `entregue` → `arquivado`

**Financeiro (5):** `a_faturar` → `faturado` → `recebido` · `atrasado`
(derivado) · `cancelado` (terminal)

Os rótulos vivem no backend (`ETAPA_LABELS`, `STATUS_LABELS`) e são servidos por
`GET /api/negocios/etapas`, `/api/producoes/etapas` e `/api/financeiro/status`.
**O frontend não hardcoda rótulo de etapa** — busca a lista. O que ele mapeia
localmente é só a *cor* (`src/lib/status.ts`).

## Sistema de status por cor (spec § 9)

Oito cores semânticas, herdadas verbatim do protótipo, aplicadas como
`bg-status-X/15 text-status-X border-status-X/30`:

| Token | Cor | Significa |
|---|---|---|
| `status-lead` | cinza | novo lead |
| `status-scheduled` | azul | agendado |
| `status-captured` | amarelo | captado |
| `status-editing` | roxo | em edição |
| `status-delivered` | verde | entregue |
| `status-received` | verde escuro | recebido |
| `status-late` | vermelho | atrasado |
| `status-cancelled` | preto | cancelado |

### Como a paleta foi portada

O protótipo estava em Tailwind v4 (`@theme` com OKLCH direto). A plataforma está
em **Tailwind v3**. A ponte: `src/index.css` guarda os *componentes* OKLCH
soltos (`--primary: 0.58 0.14 40`) e `tailwind.config.ts` remonta
`oklch(var(--primary) / <alpha-value>)`. É isso que preserva os modificadores de
opacidade — sem eles o `bg-status-X/15` não existiria e o sistema de cor cairia.

Marca: **terracota** sobre branco quente. Fontes: **Inter** (UI) + **Fraunces**
(display, via `.font-display`). Raio `0.625rem`. Tema claro/escuro via classe
`.dark` no `<html>`, alternado no header e persistido em localStorage.

## Convenções de frontend

- **Nada de mock.** Nenhum array hardcoded de dados de domínio, em nenhuma tela.
  Foi o pecado central do protótipo (cinco telas inteiras, e uma — a agenda —
  que aceitava um agendamento e o descartava no reload). Se um endpoint não
  existe, o caminho é criá-lo no backend, não fingir no frontend.
- **Um wrapper por endpoint** em `src/hooks/useApi.ts`. Página não monta URL.
- **Mutations via `useApiMutation(invalidate, fn, mensagem)`** — invalida as
  queries afetadas e mostra o toast. Se a mutação mexe no funil, invalide também
  `producoes` / `financeiro` / `dashboard`: mudar etapa tem efeito colateral no
  backend (abre produção, registra entrega, dá baixa).
- **Exclusão em dois toques** (`<BotaoExcluir>`), nunca `window.confirm`.
- **Formulário é `useState` com objeto plano** e um helper `set(k, v)`. Sem
  react-hook-form: os formulários são pequenos e a dependência não se paga.
- **Tipos em `src/types/index.ts` são espelho manual** dos schemas Pydantic. Não
  há geração automática de propósito — o contrato é pequeno e revisá-lo à mão é
  o que mantém as duas pontas honestas. Mudou o schema, mude o tipo.
- **Componentes de UI ficam em um arquivo** (`components/ui.tsx`). O protótipo
  instalou 47 componentes shadcn e usou cinco.

## Endpoints (58 rotas)

```
GET    /api/health                          GET    /api/me
GET    /api/dashboard                       GET    /api/clientes-metricas

CRUD   /api/clientes           (+ ?incluir_inativos)
CRUD   /api/imoveis            (+ ?incluir_inativos)
CRUD   /api/servicos           (+ ?incluir_inativos)
CRUD   /api/equipamentos       (+ ?incluir_inativos)

GET    /api/negocios/etapas
CRUD   /api/negocios
PATCH  /api/negocios/{id}/etapa             ← move o card, com efeito colateral

GET    /api/captacoes?inicio=&fim=
CRUD   /api/captacoes
PATCH  /api/captacoes/checklist/{item_id}   ← confere um item

GET    /api/producoes/etapas
CRUD   /api/producoes
PATCH  /api/producoes/{id}/etapa            ← avança, registrando evento
POST   /api/producoes/{id}/eventos          ← comentário no histórico

GET    /api/financeiro/status
GET    /api/financeiro/resumo
GET    /api/financeiro/por-cliente
CRUD   /api/financeiro?status=              ← filtra pelo status EXIBIDO
POST   /api/financeiro/{id}/baixa           ← registra recebimento
```

Para conferir o contrato exato a qualquer momento:

```bash
cd backend && SUPABASE_URL=https://x.supabase.co SUPABASE_ANON_KEY=k \
  ORG_ID=00000000-0000-0000-0000-000000000000 \
  ./venv/bin/python -c "from app.main import app; import json; print(json.dumps(app.openapi()))"
```

## Testes

**Backend** — `cd backend && ./venv/bin/python -m pytest`. Harness com FakeDB
em memória (sem rede), testes de router com status HTTP fixado.

**Frontend** — `cd frontend && npm test` (Vitest + Testing Library). Padrão do
`dilidu`: unitários para `lib/*` e primitivos; testes de página com react-query
real e o módulo `api` mockado, verificando render, estado vazio, modais,
validação de formulário e **o payload exato de cada mutação**.

`src/test/utils.tsx` traz `renderWithProviders`.

**Verificação mínima antes de qualquer commit:**

```bash
cd frontend && npm run build     # tem que passar limpo
cd backend  && ./venv/bin/python -m pytest
```

## Lacunas conhecidas

1. **Upload de arquivos.** A spec pede upload por etapa de produção. O schema
   deixa espaço (`producao_eventos.arquivo_url`); precisa de um bucket no
   Supabase Storage com RLS própria. Não construído.
2. **Papéis de equipe.** A spec pede “permissões por usuário” mas nunca define
   os papéis. `responsavel` é texto livre. **Não invente hierarquia que o
   estúdio não pediu.**
3. **Rotacionar a senha do admin** que o protótipo gravou no histórico do git.
   → `_NOC_ABSORPTION/01-DATA-MODEL.md` § Security findings.
4. **Migração dos dados existentes.** Três tabelas do protótipo têm dados reais
   (`clientes`, `servicos`, `equipamentos`). Exportar e carregar no `p_studio`
   com o `org_id` certo antes do go-live. Não é necessário em dev — a migration
   002 semeia.
5. **Automações (módulo 10)** — Calendar, WhatsApp, Drive, Dropbox, Stripe, PIX.
   Explicitamente futuro; as costuras existem, nada foi construído.
6. **Busca global** no header do protótipo (`⌘K`) não foi portada — era
   decorativa lá, e portá-la sem implementar seria repetir o erro.

## Absorção pela plataforma

Quando chegar a hora: mover para `products/p-studio/`, trocar `main.py` por
`create_product_app()` do `noctusai_seed`, `components/ui.tsx` pelos primitivos
de `@noctusai/lib` e o login local pelo SSO do Core. O schema `p_studio` já vive
no Postgres da plataforma e já está exposto no PostgREST; o produto já está
registrado em `public.products`.
