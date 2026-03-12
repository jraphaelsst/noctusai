import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import type {
  Comissao,
  ComissaoResumo,
  ComissaoCreateData,
  ComissaoUpdateData,
  ComissaoStatus,
} from '@/types/comissoes';

interface FiltrosComissoes {
  status?: ComissaoStatus;
  page?: number;
  page_size?: number;
}

export function useComissoes(filtros?: FiltrosComissoes) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['comissoes', filtros],
    queryFn: async () => {
      const result = await api.get('/api/comissoes', {
        status: filtros?.status,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Comissao[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
  });
}

export function useComissao(id?: string) {
  return useQuery({
    queryKey: ['comissao', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/comissoes/${id}`);
      return result.data as Comissao;
    },
    enabled: !!id,
  });
}

export function useComissaoResumo() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['comissoes-resumo'],
    queryFn: async () => {
      const result = await api.get('/api/comissoes/resumo');
      return result.data as ComissaoResumo;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateComissao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ComissaoCreateData) => {
      const result = await api.post('/api/comissoes', data);
      return result.data as Comissao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comissoes'] });
      queryClient.invalidateQueries({ queryKey: ['comissoes-resumo'] });
      toast.success('Comissão criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar comissão', { description: error.message });
    },
  });
}

export function useUpdateComissao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ComissaoUpdateData & { id: string }) => {
      const result = await api.patch(`/api/comissoes/${id}`, data);
      return result.data as Comissao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comissoes'] });
      queryClient.invalidateQueries({ queryKey: ['comissao'] });
      queryClient.invalidateQueries({ queryKey: ['comissoes-resumo'] });
      toast.success('Comissão atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar comissão', { description: error.message });
    },
  });
}

export function useDeleteComissao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/comissoes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comissoes'] });
      queryClient.invalidateQueries({ queryKey: ['comissoes-resumo'] });
      toast.success('Comissão excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir comissão', { description: error.message });
    },
  });
}
