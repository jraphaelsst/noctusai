# 02 — ERP Frontend Context

> Path: `products/erp-imobiliario/frontend/src/` · Port: 8080 · 60 pages · 63 hooks · API: `VITE_BACKEND_API_URL`
> Standard frontend patterns (toast, hooks, auth init, dates): see `../PATTERNS/frontend/frontend.md`.

## Overview

Full real estate CRM frontend. 60 lazy-loaded pages, 63 TanStack Query hooks, Zustand stores, shadcn/ui. Supabase client uses `db: { schema: 'erp' }`.

## State Management

| Layer | Technology |
|-------|-----------|
| Server state | TanStack Query (56 hooks) |
| Global UI | Zustand: authStore, filtrosStore (date range + corretor/status/tipo), funilFiltrosStore (busca + responsavel + etapa) |
| Forms | React useState + React Hook Form |

**Date fields in stores use `string | undefined` (ISO strings), not `Date` objects.** Convert at component boundaries.

## Sidebar Navigation (8 groups)

1. **Principal** — Dashboard, Funil, Clientes, Metas
2. **Comercial** — Imóveis, Condomínios, Permutas, Negociações, Propostas, Contratos, Locações, Comissões
3. **Financeiro** — Financeiro, Impostos, Banco, Análise de Crédito
4. **Operacional** — Agenda, Vistorias, Manutenção, Chaves, Campo, Seguros
5. **Marketing** — Marketing, Emails, WhatsApp, Meta Ads, Notificações
6. **Documentos** — Documentos, Assinaturas, DIMOB, Relatórios
7. **Portais** — Portal Cliente, Portal Externo, Site Imóveis
8. **Analytics** — BI, Matching IA, Gamificação
Plus standalone: Distribuição, Filiais, Configurações. Admin-only: Usuários, Admin, Log de Ações.

## ERP-Specific Patterns

### Modal formData Pattern (Mandatory)

Every edit modal MUST use local `formData` state initialized from entity props. All display fields read from `formData`, never from props directly. Save persists but keeps modal open. Cancel restores original values. `useEffect` syncs when external props change.

### Constants Centralization

Status/type config maps in `lib/constants.ts`: `PROPOSTA_STATUS_CONFIG`, `CONTRATO_STATUS_CONFIG`, `VISTORIA_STATUS_CONFIG`, `MANUTENCAO_STATUS_CONFIG`, `AGENDA_TIPO_CONFIG`, `GAMIFICACAO_PERIODO_CONFIG`, `DOCUMENTO_TIPO_CONFIG`, etc.

### Shared Components

- `shared/DocumentosTab.tsx` — Reusable document tab accepting `{ entityType, entityId }`
- `matching/MatchResultsPanel.tsx` — AI matching results display
- `ai/AIDescriptionGenerator.tsx` — AI description generation

### Supabase Direct Usage

Only for: auth, `status_pagina` sidebar query, `user_roles` query, `user_actions_log` insert, `negociacoes` insert. Everything else goes through API client.
