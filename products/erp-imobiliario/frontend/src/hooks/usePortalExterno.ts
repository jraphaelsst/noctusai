import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface PortalToken {
  id: string;
  org_id: string;
  tipo: 'proprietario' | 'locatario';
  pessoa_id: string;
  token: string;
  nome: string;
  email?: string | null;
  expires_at: string;
  is_active: boolean;
  created_at: string;
  link?: string;
}

export interface PortalData {
  tipo: 'proprietario' | 'locatario';
  nome: string;
  expires_at: string;
}

export function usePortalTokens() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['portal-tokens'],
    queryFn: async () => {
      const result = await api.get('/api/portal/tokens');
      return (result.data || []) as PortalToken[];
    },
    enabled: !!user,
  });
}

export function useGerarLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      tipo: 'proprietario' | 'locatario';
      pessoa_id: string;
      nome: string;
      email?: string;
      dias_validade?: number;
    }) => {
      const result = await api.post('/api/portal/gerar-link', data);
      return result.data as PortalToken;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal-tokens'] });
      toast.success('Link de acesso gerado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar link', { description: error.message });
    },
  });
}

export function useRevogarToken() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (tokenId: string) => {
      await api.delete(`/api/portal/tokens/${tokenId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal-tokens'] });
      toast.success('Token revogado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao revogar token', { description: error.message });
    },
  });
}

// Public portal hooks (no auth required — uses token in URL)
const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

async function fetchPublic(path: string) {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`);
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

export function usePortalValidar(token?: string) {
  return useQuery({
    queryKey: ['portal', token],
    queryFn: async () => {
      if (!token) return null;
      const result = await fetchPublic(`/api/portal/${token}`);
      return result.data as PortalData;
    },
    enabled: !!token,
    retry: false,
  });
}

export function usePortalImoveis(token?: string) {
  return useQuery({
    queryKey: ['portal-imoveis', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublic(`/api/portal/${token}/imoveis`);
      return result.data || [];
    },
    enabled: !!token,
  });
}

export function usePortalFinanceiro(token?: string) {
  return useQuery({
    queryKey: ['portal-financeiro', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublic(`/api/portal/${token}/financeiro`);
      return result.data || [];
    },
    enabled: !!token,
  });
}

export function usePortalContratos(token?: string) {
  return useQuery({
    queryKey: ['portal-contratos', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublic(`/api/portal/${token}/contratos`);
      return result.data || [];
    },
    enabled: !!token,
  });
}

export function usePortalDocumentos(token?: string) {
  return useQuery({
    queryKey: ['portal-documentos', token],
    queryFn: async () => {
      if (!token) return [];
      const result = await fetchPublic(`/api/portal/${token}/documentos`);
      return result.data || [];
    },
    enabled: !!token,
  });
}
