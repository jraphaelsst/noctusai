import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface PortalAcesso {
  id: string;
  cliente_id: string;
  // SECURITY: `token` is ONLY populated at the one-shot issue moment
  // (POST /gerar-acesso). The admin listing endpoint hides it; re-issue via
  // gerar-acesso to get a fresh token. See Phase 3b token-leak defense.
  token?: string;
  ativo: boolean;
  data_expiracao?: string;
  ultimo_acesso?: string;
  created_at: string;
  link?: string;
}

export interface ChamadoPortal {
  id: string;
  cliente_id: string;
  portal_acesso_id: string;
  assunto: string;
  descricao: string;
  status: 'aberto' | 'em_andamento' | 'resolvido' | 'fechado';
  prioridade: 'baixa' | 'media' | 'alta' | 'urgente';
  resposta?: string;
  created_at: string;
  updated_at: string;
}

interface FiltrosAcessos {
  cliente_id?: string;
  page?: number;
  page_size?: number;
}

interface FiltrosChamados {
  status?: string;
  cliente_id?: string;
  page?: number;
  page_size?: number;
}

export function usePortalAcessos(filtros?: FiltrosAcessos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['portal-acessos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/portal-cliente/acessos', {
        cliente_id: filtros?.cliente_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as PortalAcesso[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useGerarAcesso() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { cliente_id: string; data_expiracao?: string }) => {
      const result = await api.post('/api/portal-cliente/gerar-acesso', data);
      return result.data as PortalAcesso;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal-acessos'] });
      toast.success('Acesso gerado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar acesso', { description: error.message });
    },
  });
}

export function useRevogarAcesso() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/portal-cliente/acessos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal-acessos'] });
      toast.success('Acesso revogado');
    },
    onError: (error: Error) => {
      toast.error('Erro ao revogar acesso', { description: error.message });
    },
  });
}

export function useChamadosPortal(filtros?: FiltrosChamados) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['chamados-portal', filtros],
    queryFn: async () => {
      const result = await api.get('/api/portal-cliente/chamados', {
        status: filtros?.status,
        cliente_id: filtros?.cliente_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as ChamadoPortal[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useUpdateChamado() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; status?: string; resposta?: string }) => {
      const result = await api.patch(`/api/portal-cliente/chamados/${id}`, data);
      return result.data as ChamadoPortal;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chamados-portal'] });
      toast.success('Chamado atualizado');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar chamado', { description: error.message });
    },
  });
}


// ---------------------------------------------------------------------------
// Public client-portal hooks (no Bearer auth — uses portal token in URL).
// Mirrors the shape of `usePortalExterno` public hooks: a plain `fetch` against
// VITE_BACKEND_API_URL bypasses the seed `api.*` helper because the seed helper
// injects Bearer auth, which the public endpoints intentionally reject/ignore.
// LGPD-flag note: each of these endpoints is gated by the portal token + slowapi
// rate-limit (`DEFAULT_PORTAL_RL`). Cataloged in PROJECT.md Phase 6 + LGPD.
// ---------------------------------------------------------------------------

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

async function fetchPublicClientPortal(path: string, init?: RequestInit) {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, init);
  } catch {
    throw new Error(`Servidor indisponível (${path}). Verifique se o backend está rodando.`);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const message = data?.error?.message || data?.detail || `Erro HTTP ${response.status}`;
    throw new Error(`[${response.status}] ${message}`);
  }
  return response.json();
}

export interface PortalDashboard {
  contratos: unknown[];
  financeiro: unknown[];
  documentos: unknown[];
}

export function usePortalClienteDashboard(token?: string) {
  return useQuery({
    queryKey: ['portal-cliente-dashboard', token],
    queryFn: async () => {
      if (!token) return null;
      const result = await fetchPublicClientPortal(`/api/portal-cliente/${token}/dashboard`);
      return result.data as PortalDashboard;
    },
    enabled: !!token,
    retry: false,
  });
}

export function usePortalClienteFinanceiro(token?: string) {
  return useQuery({
    queryKey: ['portal-cliente-financeiro', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublicClientPortal(`/api/portal-cliente/${token}/financeiro`);
      return (result.data || []) as unknown[];
    },
    enabled: !!token,
  });
}

export function usePortalClienteChamados(token?: string) {
  return useQuery({
    queryKey: ['portal-cliente-chamados', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublicClientPortal(`/api/portal-cliente/${token}/chamados`);
      return (result.data || []) as ChamadoPortal[];
    },
    enabled: !!token,
  });
}

export function useCriarChamadoCliente(token: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { assunto: string; descricao: string; prioridade?: string }) => {
      if (!token) throw new Error('Token de portal requerido');
      const result = await fetchPublicClientPortal(`/api/portal-cliente/${token}/chamados`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      return result.data as ChamadoPortal;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal-cliente-chamados', token] });
      toast.success('Chamado criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar chamado', { description: error.message });
    },
  });
}
