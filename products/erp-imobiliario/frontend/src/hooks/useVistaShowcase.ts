/**
 * Vista CRM showcase hooks — admin-only proxy onto external CRM.
 *
 * Every hook hits an ERP backend route under /api/vista-showcase/*; the
 * Vista API key never reaches the browser.
 *
 * See products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';

// ── Types (mirror backend Showcase* DTOs) ────────────────────

export interface VistaTabStatus {
  tab: string;
  label: string;
  // `pending_intake` was added backend-side on 2026-08-21 and this union was
  // not updated with it — so a status the API can genuinely return was absent
  // from the type for a day. Vista blocks us (`permission_denied`) and we
  // haven't wired it yet (`pending_intake`) are different answers to "why is
  // this empty?" and the UI must be able to tell them apart.
  status:
    | 'live'
    | 'permission_denied'
    | 'pending_intake'
    | 'not_found'
    | 'not_configured'
    | 'doc_only';
  endpoint: string;
  note?: string | null;
}

export interface VistaPagination {
  pagina: number;
  quantidade: number;
  total?: number | null;
  paginas?: number | null;
}

export interface VistaShowcaseImovel {
  codigo: string;
  titulo?: string | null;
  categoria?: string | null;
  finalidade?: string | null;
  status?: string | null;
  cidade?: string | null;
  bairro?: string | null;
  endereco?: string | null;
  cep?: string | null;
  estado?: string | null;
  valor_venda?: number | null;
  valor_locacao?: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  area_construida?: number | null;
  dormitorios?: number | null;
  suites?: number | null;
  vagas?: number | null;
  banheiros?: number | null;
  foto_url?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  data_atualizacao?: string | null;
  corretor_nome?: string | null;
  raw: Record<string, unknown>;
}

export interface VistaShowcaseImovelDetalhes {
  codigo: string;
  base: VistaShowcaseImovel;
  caracteristicas: Record<string, unknown>;
  raw: Record<string, unknown>;
}

/**
 * One client, LIST projection. Mirrors backend `ShowcaseCliente`.
 *
 * 🔴 There is no birth date / sex / marital status / profession here, and
 * that is deliberate — see `VistaShowcaseClienteDetalhes`. If you find
 * yourself wanting to add one to render a list column, that is the moment to
 * re-open the minimisation decision, not to widen the type.
 *
 * Also no `raw`: unlike imóveis/usuários/agências the backend sends no
 * untouched Vista payload for this family, and reports `raw_available: false`.
 */
export interface VistaShowcaseCliente {
  codigo: string;
  nome?: string | null;
  celular?: string | null;
  status?: string | null;
  data_cadastro?: string | null;
  corretor_nome?: string | null;
  interesse?: string | null;
}

/**
 * One client, DETAIL projection. Mirrors backend `ShowcaseClienteDetalhes`.
 * The only shape in the frontend that carries the demographic fields, and it
 * is only ever populated by opening one named client.
 */
export interface VistaShowcaseClienteDetalhes {
  codigo: string;
  base: VistaShowcaseCliente;
  data_nascimento?: string | null;
  sexo?: string | null;
  estado_civil?: string | null;
  profissao?: string | null;
}

export interface VistaClientesFilters {
  nome?: string;
  status?: string;
}

export interface VistaShowcaseUsuario {
  codigo: string;
  nome?: string | null;
  email?: string | null;
  setor?: string | null;
  foto_url?: string | null;
  raw: Record<string, unknown>;
}

export interface VistaShowcaseAgencia {
  codigo: string;
  nome?: string | null;
  endereco?: string | null;
  cidade?: string | null;
  bairro?: string | null;
  site?: string | null;
  raw: Record<string, unknown>;
}

export interface VistaEnvelope<T> {
  source: 'vista';
  tab: string;
  live: boolean;
  fetched_at: string;
  pagination?: VistaPagination | null;
  items: T[];
  raw_available: boolean;
  warnings: string[];
}

export interface VistaDiagnosticProbe {
  endpoint: string;
  status: string;
  http_status: number | null;
  latency_ms?: number;
}

export interface VistaDiagnostic {
  tenant_base_url: string;
  configured: boolean;
  probes: VistaDiagnosticProbe[];
}

export interface VistaImoveisFilters {
  status?: string;
  categoria?: string;
  cidade?: string;
  bairro?: string;
  finalidade?: string;
}

// ── Hooks ────────────────────────────────────────────────────

// `api.get<T>()` from @noctusai/seed/infra returns the parsed JSON directly
// as `T` (not an axios-style { data: T } wrapper). Earlier drafts of these
// hooks read `result.data` — that masked the real envelope behind `undefined`
// and TanStack Query v5 raised "Query data cannot be undefined". Always read
// the response shape directly, and never let a queryFn return undefined.

export function useVistaTabs(enabled: boolean) {
  return useQuery({
    queryKey: ['vista-showcase', 'tabs'],
    queryFn: async () => {
      const result = await api.get<{ tabs: VistaTabStatus[] }>('/api/vista-showcase/tabs');
      return result?.tabs ?? [];
    },
    enabled,
    staleTime: 60_000,
  });
}

export function useVistaImoveis(
  enabled: boolean,
  page: number,
  pageSize: number,
  filters: VistaImoveisFilters,
) {
  return useQuery({
    queryKey: ['vista-showcase', 'imoveis', page, pageSize, filters],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
      });
      const result = await api.get<VistaEnvelope<VistaShowcaseImovel>>(
        `/api/vista-showcase/imoveis?${params.toString()}`,
      );
      return result ?? null;
    },
    enabled,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });
}

export function useVistaImovelDetalhes(codigo: string | null) {
  return useQuery({
    queryKey: ['vista-showcase', 'imovel-detalhes', codigo],
    queryFn: async () => {
      const result = await api.get<VistaEnvelope<VistaShowcaseImovelDetalhes>>(
        `/api/vista-showcase/imoveis/${encodeURIComponent(codigo!)}`,
      );
      return result?.items?.[0] ?? null;
    },
    enabled: !!codigo,
    staleTime: 60_000,
  });
}

export function useVistaImoveisConteudo(enabled: boolean) {
  return useQuery({
    queryKey: ['vista-showcase', 'imoveis-conteudo'],
    queryFn: async () => {
      const result = await api.get<VistaEnvelope<Record<string, unknown>>>(
        '/api/vista-showcase/imoveis-conteudo',
      );
      return result?.items?.[0] ?? {};
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}

/**
 * One page of the client list.
 *
 * `enabled` is threaded from the tab so the query cannot fire from anywhere
 * that has not deliberately opened Clientes — merely rendering the showcase
 * page must not read personal data.
 *
 * `placeholderData` is NOT used here on purpose. Keeping the previous page
 * visible while the next loads is nice for a property grid; for a personal
 * data table it means one admin's screen keeps showing rows the current query
 * no longer authorises. Page changes show a skeleton instead.
 */
export function useVistaClientes(
  enabled: boolean,
  page: number,
  pageSize: number,
  filters: VistaClientesFilters,
) {
  return useQuery({
    queryKey: ['vista-showcase', 'clientes', page, pageSize, filters],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
      });
      const result = await api.get<VistaEnvelope<VistaShowcaseCliente>>(
        `/api/vista-showcase/clientes?${params.toString()}`,
      );
      return result ?? null;
    },
    enabled,
    // Deliberately short. Personal data read live and not cached is the whole
    // LGPD posture of this page; a long staleTime would quietly turn the
    // browser into the cache the backend refuses to be.
    staleTime: 15_000,
    gcTime: 60_000,
  });
}

/**
 * One named client, including the four demographic fields.
 *
 * Fires ONLY when a `codigo` is set, i.e. when an admin opened that specific
 * record — which is also what makes the backend's `projection: "detail"`
 * audit row meaningful.
 */
export function useVistaClienteDetalhes(codigo: string | null) {
  return useQuery({
    queryKey: ['vista-showcase', 'cliente-detalhes', codigo],
    queryFn: async () => {
      const result = await api.get<VistaEnvelope<VistaShowcaseClienteDetalhes>>(
        `/api/vista-showcase/clientes/${encodeURIComponent(codigo!)}`,
      );
      return result?.items?.[0] ?? null;
    },
    enabled: !!codigo,
    staleTime: 15_000,
    gcTime: 60_000,
  });
}

export function useVistaUsuarios(enabled: boolean) {
  return useQuery({
    queryKey: ['vista-showcase', 'usuarios'],
    queryFn: async () => {
      const result = await api.get<VistaEnvelope<VistaShowcaseUsuario>>(
        '/api/vista-showcase/usuarios',
      );
      return result?.items ?? [];
    },
    enabled,
    staleTime: 60_000,
  });
}

export function useVistaAgencias(enabled: boolean) {
  return useQuery({
    queryKey: ['vista-showcase', 'agencias'],
    queryFn: async () => {
      const result = await api.get<VistaEnvelope<VistaShowcaseAgencia>>(
        '/api/vista-showcase/agencias',
      );
      return result?.items ?? [];
    },
    enabled,
    staleTime: 60_000,
  });
}

export function useVistaDiagnostico(enabled: boolean) {
  return useQuery({
    queryKey: ['vista-showcase', 'diagnostico'],
    queryFn: async () => {
      const result = await api.get<VistaDiagnostic>('/api/vista-showcase/diagnostico');
      return result ?? null;
    },
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
