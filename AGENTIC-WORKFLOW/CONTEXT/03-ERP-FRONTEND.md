# 03 — ERP Frontend Context

> Path: `products/erp-imobiliario/frontend/src/`
> Dev server: Vite on port **8080**
> API target: `VITE_BACKEND_API_URL` (default: `http://localhost:8001`)

---

## Overview

Full real estate CRM frontend with 45 lazy-loaded pages, 55 TanStack Query hooks, Zustand stores for UI state, and shadcn/ui components. All routes are protected behind auth.

---

## State Management

| Layer | Technology | Scope |
|-------|-----------|-------|
| Server state | TanStack Query (via hooks) | All API data |
| Global UI state | Zustand | Auth, dashboard filters, funnel filters |
| Form state | React useState + React Hook Form | Modals/dialogs |
| Session state | Supabase Auth | Login/signup/token |

### Zustand Stores

| Store | Persistence | Key State |
|-------|-------------|-----------|
| `authStore.ts` | None (managed by AuthProvider) | `user`, `setUser()` |
| `filtrosStore.ts` | localStorage (`filtros-storage`) | `periodo`, `dataInicio`, `dataFim`, corretor/status/tipo filters |
| `funilFiltrosStore.ts` | localStorage (`funil-filtros-storage`) | `busca`, `responsavelId`, `origem`, `etapa`, `incluirArquivados` |

---

## Pages (45)

### Core Pages
`Dashboard`, `Funil`, `Clientes`, `ClienteDetalhes`, `Metas`, `Usuarios`, `Admin`, `Index`, `NotFound`, `SSOCallback`

### Property Management
`Imoveis`, `Condominios`, `Permutas`, `Negociacoes`

### Real Estate Operations
`Locacoes`, `Vistorias`, `Contratos`, `Propostas`

### Financial
`Financeiro`, `Comissoes`, `Banco`, `Assinaturas`, `Impostos`, `Manutencao`

### Insurance & Documents
`Seguros`, `Documentos`, `Chaves`

### Marketing & Portals
`Marketing`, `Portais`, `PortalExterno`, `PortalCliente`, `SiteImoveis`, `Emails`

### Compliance & Analytics
`Dimob`, `AnaliseCredito`, `Filiais`, `Distribuicao`, `Relatorios`, `BI`, `Gamificacao`

### Admin & Settings
`Configuracoes`, `Matching`, `Agenda`, `Campo`, `LogAcoes`

---

## Hooks (55)

All follow TanStack Query patterns (`useQuery`, `useMutation`, `useQueryClient`).

### Core
`useAuth`, `useUserProfile`, `useUserRole`, `useUserRoles`, `useIsAdminOrCoordenador`, `useIsDev`

### Goals
`useMetas`, `useMetasConfig`, `useMetasOrdem`, `useAtualizarStatusMetas`, `useConcluirMetaAgrupada`, `useCriarMetaHoje`

### Clients & Sales
`useClientes`, `useFunil`, `usePermutas`, `useMatches`, `useMatching`

### Properties
`useImoveis`, `useCondominios`, `useCepSearch`

### Financial & Operations
`useFinanceiro`, `useBanco`, `useComissoes`, `useAssinaturas`, `useImpostos`, `useManutencao`, `useSeguros`

### Contracts & Leasing
`useContratos`, `useLocacoes`, `usePropostas`

### Admin & Compliance
`useAgenda`, `useAnaliseCredito`, `useBI`, `useCampo`, `useChaves`, `useDistribuicao`, `useDocumentos`, `useEmails`, `useFiliais`, `useGamificacao`, `useMarketing`, `usePortais`, `usePortalCliente`, `usePortalExterno`, `useRelatorios`, `useSiteImoveis`, `useVistorias`, `useWhatsApp`

### AI & Utilities
`useAI`, `useAtividades`, `useActionLog`, `useProfiles`, `useDebounce`, `use-mobile`, `use-toast`, `useRecuperarSenha`, `useRequisitarSenha`

---

## Key Components

### Layout
- `layout/Layout.tsx` — Main app wrapper
- `layout/Header.tsx` — Top bar
- `layout/Sidebar.tsx` — Navigation sidebar (RLS-driven via `status_pagina` table)

### Auth
- `auth/AuthProvider.tsx` — Auth context provider
- `auth/LoginForm.tsx` — Login/signup form

### Domain Components
- `clientes/` — ClienteCard, ColunaFunil, FiltrosFunil, NovoClienteDialog
- `matching/MatchResultsPanel.tsx` — AI matching results display
- `metas/MetasDraggableSection.tsx` — Draggable goals UI
- `ai/AIDescriptionGenerator.tsx` — AI description generation
- `whatsapp/SendPropertyModal.tsx` — WhatsApp property sharing

### UI Library
60+ shadcn/ui components (accordion, alert, badge, button, calendar, card, chart, dialog, dropdown-menu, form, input, pagination, select, table, tabs, toast, etc.)

---

## API Client (`lib/api-client.ts`)

- Auto-includes Bearer token from Supabase session
- Methods: `get()`, `post()`, `patch()`, `delete()`
- Base URL: `VITE_BACKEND_API_URL` (default `http://localhost:8001`)

---

## Routing (`App.tsx`)

All routes wrapped in `<Layout>` (authenticated). SSO callback is public.

```
/sso                    SSO callback (public)
/login                  Login page
/                       Dashboard
/funil                  Sales funnel
/clientes/:id?          Client list + details
/imoveis                Properties
/condominios            Condominiums
/permutas               Exchanges
/negociacoes            Negotiations
/metas                  Goals
/matching               AI matching
/configuracoes          Settings
... (30+ more routes)
*                       NotFound (404)
```

All page components are lazy-loaded with `React.lazy()` and `<Suspense>` fallback.

---

## Modal Patterns (Mandatory)

All modals follow a strict `formData` pattern to ensure instant UI feedback.

### Core Rule

Every edit in a modal MUST reflect immediately in the UI without closing or reloading.

### Implementation Pattern

```typescript
// 1. Local state from entity props
const [formData, setFormData] = useState({
  nome: entity.nome || '',
  descricao: entity.descricao || '',
});

// 2. ALWAYS display from formData, NEVER from props directly
<h3>{formData.nome}</h3>        // CORRECT
<h3>{entity.nome}</h3>          // WRONG — won't reflect edits

// 3. Save without closing
const handleSave = async () => {
  await updateMutation.mutateAsync({ id: entity.id, ...formData });
  setIsEditing(false);          // Exit edit mode, but keep modal open
};

// 4. Cancel restores original values
const handleCancel = () => {
  setFormData({ nome: entity.nome || '', descricao: entity.descricao || '' });
  setIsEditing(false);
};

// 5. Sync when external props change
useEffect(() => {
  setFormData({ nome: entity.nome || '', descricao: entity.descricao || '' });
}, [entity]);
```

### Anti-Patterns

- Do NOT mix `formData` and props in display (use formData for everything)
- Do NOT close modal immediately after save if user can continue editing
- Do NOT use entity props directly in display fields during edit mode

### Checklist

- `formData` state initialized from entity props
- All display fields read from `formData`
- Inputs update `formData` via `onChange`
- Save persists data but keeps modal open (when applicable)
- Cancel restores `formData` to original values
- `useEffect` syncs `formData` when external props change

---

## Date & Timezone Patterns

All date handling uses **America/Sao_Paulo** timezone. The server is the source of truth for dates.

### Rules

1. **Storage**: All dates stored in `America/Sao_Paulo` timezone in PostgreSQL
2. **Backend**: SQL functions `current_date_sao_paulo()`, `now_sao_paulo()`, `normalize_timestamp_sp(ts)`
3. **Frontend display**: `DD/MM/YYYY` via `formatDate()`, with time: `DD/MM/YYYY as HH:mm`
4. **Filters**: Use `getTodayAtMidnight()` for consistent date comparisons, `format(date, "PPP", { locale: ptBR })` for display
5. **Comparisons**: Use server-computed fields (`dias_restantes`, `status`) — never `new Date()` locally

### Utilities (`src/lib/utils.ts`)

```typescript
formatDate(dateString: string, includeTime?: boolean): string
// "2025-10-25T14:30:00Z" → "25/10/2025" or "25/10/2025 as 14:30"

getTodayAtMidnight(): Date    // Current date at 00:00:00 for filters
stripTime(date: Date): Date   // Remove time component
```

### Anti-Patterns

- Do NOT use `new Date()` for date comparisons (use server-computed `dias_restantes`)
- Do NOT convert timezones in the frontend (trust the server)
- Do NOT use `new Date(meta.data_prazo)` for comparisons
- Do NOT duplicate date logic locally (use database-calculated fields)

### Troubleshooting

- **Dates appear -1 day**: `new Date("YYYY-MM-DD")` interprets as UTC. Use `formatDate()` which handles this correctly.
- **Inconsistent times**: Check `timezone` in Supabase `config.toml` and edge functions `TZ` env var.
