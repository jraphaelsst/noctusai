# 03 — ERP Frontend Context

> Path: `products/erp-imobiliario/frontend/src/`
> Dev server: Vite on port **8080**
> API target: `VITE_BACKEND_API_URL` (default: `http://localhost:8001`)

---

## Overview

Full real estate CRM frontend with 54 lazy-loaded pages, 56 TanStack Query hooks, Zustand stores for UI state, and shadcn/ui components. All routes are protected behind auth. The Supabase client uses `db: { schema: 'erp' }` so all direct `.from()` calls target the ERP schema.

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
| `authStore.ts` | None (managed by AuthProvider) | `user`, `isInitialized`, `setUser()`, `setInitialized()` |
| `filtrosStore.ts` | localStorage (`filtros-storage`) | `periodo`, `dataInicio` (string), `dataFim` (string), corretor/status/tipo filters |
| `funilFiltrosStore.ts` | localStorage (`funil-filtros-storage`) | `busca`, `responsavelId`, `origem`, `etapa`, `incluirArquivados` |

**Date fields in stores use `string | undefined` (ISO strings), not `Date` objects.** Convert at component boundaries:
- Calendar `selected`: `selected={dataInicio ? new Date(dataInicio) : undefined}`
- Calendar `onSelect`: `onSelect={(date) => setDataInicio(date?.toISOString())}`
- date-fns functions: `setDataInicio(startOfDay(hoje).toISOString())`

---

## Pages (54)

### Core Pages
`Dashboard`, `Funil`, `Clientes`, `ClienteDetalhes`, `Metas`, `Usuarios`, `Admin`, `NotFound`, `SSOCallback`

### Property Management
`Imoveis`, `ImovelDetalhes`, `Condominios`, `Permutas`, `PermutaDetalhes`, `Negociacoes`

### Real Estate Operations
`Locacoes`, `LocacaoDetalhes`, `Vistorias`, `VistoriaDetalhes`, `Contratos`, `ContratoDetalhes`, `Propostas`, `PropostaDetalhes`

### Financial
`Financeiro`, `Comissoes`, `Banco`, `Assinaturas`, `Impostos`, `Manutencao`

### Insurance & Documents
`Seguros`, `Documentos`, `Chaves`, `Certidoes`

### Marketing & Communication
`Marketing`, `Portais`, `PortalExterno`, `PortalCliente`, `SiteImoveis`, `Emails`, `WhatsAppInbox`, `Notificacoes`, `MetaAds`

### Compliance & Analytics
`Dimob`, `AnaliseCredito`, `Filiais`, `Distribuicao`, `Relatorios`, `BI`, `Gamificacao`

### Admin & Settings
`Configuracoes`, `Matching`, `Agenda`, `Campo`, `LogAcoes`

---

## Hooks (56)

All follow TanStack Query patterns (`useQuery`, `useMutation`, `useQueryClient`).

### Core
`useUserProfile`, `useUserRole`, `useUserRoles`, `useIsAdminOrCoordenador`

### Goals
`useMetas`, `useMetasConfig`, `useMetasOrdem`, `useAtualizarStatusMetas`, `useConcluirMetaAgrupada`, `useCriarMetaHoje`

### Clients & Sales
`useClientes`, `useFunil`, `usePermutas`, `useMatches`

### Properties
`useImoveis`, `useCondominios`, `useCepSearch`

### Financial & Operations
`useFinanceiro`, `useBanco`, `useComissoes`, `useAssinaturas`, `useImpostos`, `useManutencao`, `useSeguros`

### Contracts & Leasing
`useContratos`, `useLocacoes`, `usePropostas`

### Admin & Compliance
`useAgenda`, `useAnaliseCredito`, `useBI`, `useCampo`, `useChaves`, `useCertidoes`, `useDistribuicao`, `useDocumentos`, `useEmails`, `useFiliais`, `useGamificacao`, `useMarketing`, `usePortais`, `usePortalCliente`, `usePortalExterno`, `useRelatorios`, `useSiteImoveis`, `useVistorias`, `useWhatsApp`

### Dashboard & Analytics
`useDashboardResumo` (in useBI.ts), `useBIVendas`, `useBICaptacao`, `useBICorretores`, `useBIImoveis`, `useBIFinanceiro`

### Integrations
`useNotificacoes` (6 hooks: list, count, mark read, preferences), `useMetaApi` (config, leads, campaigns, sync)

### AI & Utilities
`useAI`, `useAtividades`, `useActionLog`, `useProfiles`, `useDebounce`, `use-mobile`, `useRecuperarSenha`, `useRequisitarSenha`

---

## Key Components

### Layout
- `layout/Layout.tsx` — Main app wrapper
- `layout/Header.tsx` — Top bar
- `layout/Sidebar.tsx` — Navigation sidebar with **8 collapsible groups** (RLS-driven via `status_pagina` table):
  1. **Principal** — Dashboard, Funil, Clientes, Metas
  2. **Comercial** — Imóveis, Condomínios, Permutas, Negociações, Propostas, Contratos, Locações, Comissões
  3. **Financeiro** — Financeiro, Impostos, Banco, Análise de Crédito
  4. **Operacional** — Agenda, Vistorias, Manutenção, Chaves, Campo, Seguros
  5. **Marketing & Comunicação** — Marketing, Emails, WhatsApp, Meta Ads, Notificações
  6. **Documentos** — Documentos, Assinaturas, DIMOB, Relatórios
  7. **Portais & Site** — Portal Cliente, Portal Externo, Site Imóveis
  8. **Analytics & IA** — BI, Matching IA, Gamificação
  - Plus standalone items: Distribuição, Filiais, Configurações
  - Plus admin-only **Painel de Controle**: Usuários, Admin, Log de Ações
- `NotificationBell.tsx` — Notification bell dropdown for the header

### Auth
- `auth/AuthProvider.tsx` — Auth context provider (manages `isInitialized` flag + periodic activity tracking)
- `auth/LoginForm.tsx` — Login/signup form

### Shared Components
- `shared/DocumentosTab.tsx` — Reusable document tab accepting `{ entityType, entityId }`, used by ClienteDocumentos, ImovelDocumentos, etc.

### Domain Components
- `clientes/` — ClienteCard, ColunaFunil, FiltrosFunil, NovoClienteDialog, ClienteResumo, ClienteDocumentos, ClienteHistorico, ClienteAtividades, ClientePropostas
- `imoveis/` — ImovelResumo, ImovelFotos, ImovelDocumentos, ImovelMatches, ImovelPropostas, ImovelVistorias
- `contratos/` — ContratoResumo, ContratoParcelas, ContratoDocumentos
- `locacoes/` — LocacaoResumo, LocacaoDocumentos, LocacaoVistorias
- `permutas/` — PermutaResumo, PermutaMatches, PermutaCriterios
- `propostas/` — PropostaResumo, PropostaDocumentos, PropostaHistorico
- `vistorias/` — VistoriaResumo, VistoriaFotos, VistoriaChecklist
- `matching/MatchResultsPanel.tsx` — AI matching results display
- `metas/MetasDraggableSection.tsx` — Draggable goals UI
- `ai/AIDescriptionGenerator.tsx` — AI description generation
- `whatsapp/SendPropertyModal.tsx` — WhatsApp property sharing

### Shared UI Components
- `ui/empty-state.tsx` — Empty state placeholder for empty lists
- `ui/entity-link.tsx` — Cross-entity navigation links
- `ui/page-breadcrumb.tsx` — Breadcrumb navigation for detail pages
- `ui/page-skeleton.tsx` — Full-page loading skeleton

### UI Library
60+ shadcn/ui components (accordion, alert, badge, button, calendar, card, chart, dialog, dropdown-menu, form, input, pagination, select, table, tabs, etc.)

### Key Library Files

| File | Purpose |
|------|---------|
| `lib/api-client.ts` | Centralized API client (get/post/patch/delete with auth, 204 handling, `unknown` body types) |
| `lib/utils.ts` | `formatCurrency()`, `formatDate()`, `getTodayAtMidnight()`, `cn()` |
| `lib/constants.ts` | Centralized status/type config maps with proper Portuguese accents |
| `lib/validations.ts` | Zod schemas (loginSchema, signUpSchema, corretorSchema, clienteSchema, etc.) |
| `lib/categorias.ts` | Meta category ordering and labels |

---

## Toast Pattern (Mandatory)

Use **sonner** for all toasts. The old `useToast` hook and shadcn toast components have been deleted.

```typescript
import { toast } from 'sonner';

// Success
toast.success("Operação realizada com sucesso");

// Error with description
toast.error("Erro ao salvar", { description: "Verifique os campos do formulário" });

// Never use:
// - import { useToast } from '@/hooks/use-toast'  (DELETED)
// - toast({ title: "...", variant: "destructive" })  (OLD PATTERN)
```

---

## Hook Quality Patterns (Mandatory)

### Auth Guards
Every query hook that fetches user-scoped data must include `enabled: !!user`:
```typescript
const { data } = useQuery({
  queryKey: ["metas", user?.id],
  queryFn: () => api.get("/api/metas"),
  enabled: !!user,  // Prevents unauthenticated requests
});
```

### staleTime Guidelines
| Data Type | staleTime | Examples |
|-----------|-----------|---------|
| Reference data (rarely changes) | 10-30 min | condominios, portaisFeeds, siteConfig, metasConfig |
| Active working data | 3-5 min | imoveis, imoveisPortal, perfilsPermuta, filiais, chaves, analisesCredito |
| Real-time-ish data | 30s-2 min | contagemNaoLidas, checkins |
| AI/expensive operations | 5 min | matchCounts |

### Mutation Invalidations
Every mutation must invalidate all affected query keys. Cross-entity invalidations are critical:
```typescript
onSuccess: () => {
  queryClient.invalidateQueries({ queryKey: ["locacoes"] });
  queryClient.invalidateQueries({ queryKey: ["imoveis"] });  // Creating a locação affects imóvel status
}
```

### Constants Centralization
Status/type config maps (label + color) live in `lib/constants.ts`:
```typescript
import { PROPOSTA_STATUS_CONFIG, CONTRATO_STATUS_CONFIG } from '@/lib/constants';

const config = PROPOSTA_STATUS_CONFIG[status];
// { label: "Aceita", color: "bg-green-100 text-green-800" }
```

Available maps: `PROPOSTA_STATUS_CONFIG`, `CONTRATO_STATUS_CONFIG`, `CONTRATO_TIPO_CONFIG`, `VISTORIA_STATUS_CONFIG`, `VISTORIA_TIPO_CONFIG`, `MANUTENCAO_STATUS_CONFIG`, `AGENDA_TIPO_CONFIG`, `GAMIFICACAO_PERIODO_CONFIG`, `DOCUMENTO_TIPO_CONFIG`. Plus `formatFileSize()`.

---

## Auth Initialization Pattern

`AuthProvider` calls `setInitialized()` on `authStore` after `getSession()` resolves. `AppContent` in `App.tsx` shows `<PageSkeleton />` while `!isInitialized`, preventing the login form from flashing briefly before the session loads.

```typescript
// AppContent
const { user, isInitialized } = useAuthStore();
if (!isInitialized) return <PageSkeleton />;
if (!user) return <LoginForm />;
return <AuthenticatedRoutes />;
```

---

## Supabase Client (`integrations/supabase/client.ts`)

- Configured with `db: { schema: 'erp' }` — all `.from()` calls target the `erp` schema
- Only used directly for: auth (`supabase.auth.*`), `status_pagina` sidebar query, `user_roles` query, `user_actions_log` insert, `negociacoes` insert
- All other data operations go through the API client below

## API Client (`lib/api-client.ts`)

- Auto-includes Bearer token from Supabase session
- Methods: `get()`, `post()`, `patch()`, `delete()`
- Base URL: `VITE_BACKEND_API_URL` (default `http://localhost:8001`)
- All methods use `safeFetch()` wrapper (catches network errors with user-friendly Portuguese message)
- Handles HTTP 204 No Content (returns `null`, no `.json()` call)
- Body params typed as `unknown` (not `any`) for type safety
- `get()` supports `params` object for query string construction (skips undefined/null/empty values)
- File uploads (`useStorage`) use raw `fetch()` with `BACKEND_URL` prefix (FormData requires omitting Content-Type header)

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
