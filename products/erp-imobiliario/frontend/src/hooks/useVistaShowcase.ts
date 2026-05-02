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
  status: 'live' | 'permission_denied' | 'not_found' | 'not_configured' | 'doc_only';
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
