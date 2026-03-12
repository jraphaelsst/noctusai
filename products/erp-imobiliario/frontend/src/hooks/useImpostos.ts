import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import {
  Imposto,
  ImpostoCreateData,
  ImpostoUpdateData,
  ResumoImpostos,
} from '@/types/impostos';

interface FiltrosImpostos {
  imovel_id?: string;
  ano?: number;
  tipo?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

export function useImpostos(filtros?: FiltrosImpostos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['impostos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/impostos', {
        imovel_id: filtros?.imovel_id,
        ano: filtros?.ano,
        tipo: filtros?.tipo,
        status: filtros?.status,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Imposto[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useImposto(id?: string) {
  return useQuery({
    queryKey: ['imposto', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/impostos/${id}`);
      return result.data as Imposto;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useResumoImpostos(filtros?: { ano?: number; imovel_id?: string }) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['impostos-resumo', filtros],
    queryFn: async () => {
      const result = await api.get('/api/impostos/resumo', {
        ano: filtros?.ano,
        imovel_id: filtros?.imovel_id,
      });
      return result.data as ResumoImpostos;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateImposto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ImpostoCreateData) => {
      const result = await api.post('/api/impostos', data);
      return result.data as Imposto;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['impostos'] });
      queryClient.invalidateQueries({ queryKey: ['impostos-resumo'] });
      toast.success('Imposto cadastrado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao cadastrar imposto', { description: error.message });
    },
  });
}

export function useUpdateImposto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ImpostoUpdateData) => {
      const result = await api.patch(`/api/impostos/${id}`, data);
      return result.data as Imposto;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['impostos'] });
      queryClient.invalidateQueries({ queryKey: ['impostos-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['imposto'] });
      toast.success('Imposto atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar imposto', { description: error.message });
    },
  });
}

export function useDeleteImposto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/impostos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['impostos'] });
      queryClient.invalidateQueries({ queryKey: ['impostos-resumo'] });
      toast.success('Imposto excluído!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir imposto', { description: error.message });
    },
  });
}
