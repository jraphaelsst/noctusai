# Monica

CRM do consultório de psicanálise de **Mônica Tangerino** (psicanalista; fala sobre os assuntos importantes da vida pelas lentes da psicanálise; Instagram `@psimonicatangerino` profissional, `@monicatangerino` pessoal). Primeiro produto da organização "Mônica Tangerino"; hoje CRM, no futuro ERP (o financeiro já está montado e escondido atrás de `status_pagina`). UI em pt-BR. Tudo é órgão da seed — o produto só liga os órgãos.

## Telas

| Rota | O que é | Órgão da seed |
|---|---|---|
| `/` | Início: quantos leads em cada etapa do funil | `useLeadsBoard` |
| `/leads` (Funil) · `/leads/lista` (Lista) | Kanban de leads (arrastar muda a etapa; clicar abre o lead; "abrir conversa") e a tabela com filtros (etapa, origem, data do 1º contato, busca). **Funil e Lista compartilham os filtros.** CRUD completo (a Mônica apaga números que não são leads) | `LeadsBoard`, `LeadsList`, `LeadDetailModal` |
| `/conversas` | Conversas de WhatsApp: ler e responder, `?chat=` abre uma conversa, "Ver lead" no cabeçalho | `WhatsAppInbox` |
| `/contexto` | Quem a Mônica é, em palavras dela (abordagem, serviços, tom de voz…) — a base do futuro agente de leads | `OrgSpecsForm` via proxy `/api/contexto` |
| `/configuracoes/conexoes` | Conexão do WhatsApp por QR (só administradores). Abas como sub-rotas; cresce com uma linha em `sections` | `SectionTabsPage`, `WhatsAppConnectionsPage` |
| `/equipe` · `/financeiro` | Equipe e financeiro (organs da seed) | `TeamPage`, `FinanceRoutedPage` |

Funil: **Lead → Atendimento → Negociação → Fechado**. Origens: WhatsApp, Instagram, Indicação, Outro (`backend/app/crm.py` — são dados, mudar não pede migration). Todo número novo que escreve (não-grupo) vira lead em "Lead" com origem WhatsApp; apagar o lead **não** o traz de volta (a conversa persiste — é o desejado). Toda mensagem, recebida ou enviada, atualiza a prévia do cartão.

## Stack

- **Backend**: FastAPI via `create_product_app()` (porta 8020); `mount_leads`, conexões + caixa de entrada do WhatsApp (`app/routers/whatsapp_router.py`), proxy `/api/contexto`, `mount_finance`.
- **Frontend**: React via `createProductApp()` + `createProductLayout()` (porta 8240).
- **Banco**: Supabase, schema `monica` (migrations 001–016: leads, `whatsapp_connections|chats|messages`, finance, `status_pagina`).

## Configuração (nomes; valores só no `.env` do servidor)

| Chave | Para quê |
|---|---|
| `ENCRYPTION_KEY` | Fernet: a chave da API do WAHA fica cifrada em `whatsapp_connections` (sem ela o boot em produção falha) |
| `MONICA_WAHA_BASE_URL` | URL do WAHA **próprio da Mônica**. Sem default; vazio ⇒ criar conexão responde 503 claro. **Nunca** o WAHA compartilhado (single-session, número do One Chat) |
| `MONICA_WAHA_SESSION` | sessão do WAHA (default `default`) |
| `MONICA_WAHA_WEBHOOK_HMAC_SECRET` | igual ao `WHATSAPP_HOOK_HMAC_KEY` do WAHA, se ele assinar |
| `REDIS_URL` | tempo real da caixa de entrada (SSE entre workers). Sem Redis e sem a opção abaixo, o boot em produção recusa |
| `MONICA_INBOX_REALTIME_IN_PROCESS` | `true` declara 1 worker (sem Redis) |
| `AGENTS_URL` / `PRODUCT_URL_AGENTS` | onde fica o produto `agents` (Contexto); `AGENTS_ALLOW_FAKE=true` só em dev |
| `MONICA_AGENT_KEY` | chave da definição de agente do Contexto (default `monica-leads`) |

## Rodando

```bash
uvicorn app.main:app --reload --port 8020 --app-dir products/monica/backend
cd products/monica/frontend && npm run dev
```

## Testes

```bash
cd products/monica/backend && pytest          # 75: 401 estrito, inbox -> lead, contexto, finance, migrations
cd products/monica/frontend && npx vitest run # 10 CRM + finance route
cd products/monica/frontend && npx vite build
```

## Dados pessoais (LGPD)

As conversas são dados pessoais ligados à saúde (consultório de psicanálise). Registro e pendências em `LGPD-WARNINGS.md` (entrada `products/monica`) e `KB § PATTERNS/security/lgpd.md`. O contexto da Mônica (`agents.agent_org_specs`) é conteúdo dela, não de pacientes.

## Operação

`ops/agents/` — definição do agente `monica-leads` (campos do Contexto) e o script de pré-preenchimento (preparado, não aplicado). Passos de go-live em `ops/agents/README.md`.
