import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import {
  Contrato,
  ContratoCreateData,
  ContratoUpdateData,
  ParcelaContrato,
  ResumoContratos,
} from '@/types/contratos';

interface FiltrosContratos {
  status?: string;
  tipo?: string;
  cliente_id?: string;
  imovel_id?: string;
  page?: number;
  page_size?: number;
}

export function useContratos(filtros?: FiltrosContratos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['contratos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/contratos', {
        status: filtros?.status,
        tipo: filtros?.tipo,
        cliente_id: filtros?.cliente_id,
        imovel_id: filtros?.imovel_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Contrato[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useContrato(id?: string) {
  return useQuery({
    queryKey: ['contrato', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/contratos/${id}`);
      return result.data as Contrato;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useResumoContratos() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['contratos-resumo'],
    queryFn: async () => {
      const result = await api.get('/api/contratos/resumo');
      return result.data as ResumoContratos;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useParcelas(contratoId?: string) {
  return useQuery({
    queryKey: ['parcelas', contratoId],
    queryFn: async () => {
      if (!contratoId) return [];
      const result = await api.get(`/api/contratos/${contratoId}/parcelas`);
      return (result.data || []) as ParcelaContrato[];
    },
    enabled: !!contratoId,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateContrato() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ContratoCreateData) => {
      const result = await api.post('/api/contratos', data);
      return result.data as Contrato;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contratos'] });
      queryClient.invalidateQueries({ queryKey: ['contratos-resumo'] });
      toast.success('Contrato criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar contrato', { description: error.message });
    },
  });
}

export function useUpdateContrato() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ContratoUpdateData) => {
      const result = await api.patch(`/api/contratos/${id}`, data);
      return result.data as Contrato;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contratos'] });
      queryClient.invalidateQueries({ queryKey: ['contratos-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['contrato'] });
      queryClient.invalidateQueries({ queryKey: ['parcelas'] });
      toast.success('Contrato atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar contrato', { description: error.message });
    },
  });
}

export function useDeleteContrato() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/contratos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contratos'] });
      queryClient.invalidateQueries({ queryKey: ['contratos-resumo'] });
      toast.success('Contrato excluido com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir contrato', { description: error.message });
    },
  });
}

export function useGerarParcelas() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ contratoId, valor_entrada, num_parcelas }: { contratoId: string; valor_entrada: number; num_parcelas: number }) => {
      const result = await api.post(`/api/contratos/${contratoId}/parcelas`, {
        valor_entrada,
        num_parcelas,
      });
      return (result.data || []) as ParcelaContrato[];
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['parcelas'] });
      queryClient.invalidateQueries({ queryKey: ['contratos'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-resumo'] });
      toast.success('Parcelas geradas com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar parcelas', { description: error.message });
    },
  });
}

export function useUpdateParcela() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ parcelaId, ...data }: { parcelaId: string; status?: string; data_pagamento?: string; forma_pagamento?: string }) => {
      const result = await api.patch(`/api/contratos/parcelas/${parcelaId}`, data);
      return result.data as ParcelaContrato;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['parcelas'] });
      queryClient.invalidateQueries({ queryKey: ['contratos-resumo'] });
      toast.success('Parcela atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar parcela', { description: error.message });
    },
  });
}
