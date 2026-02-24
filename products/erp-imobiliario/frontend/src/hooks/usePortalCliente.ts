import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface PortalAcesso {
  id: string;
  cliente_id: string;
  token: string;
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
