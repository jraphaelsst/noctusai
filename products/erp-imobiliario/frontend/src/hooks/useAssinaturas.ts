import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import {
  Assinatura,
  EnviarAssinaturaData,
  ResumoAssinaturas,
} from '@/types/assinaturas';

interface FiltrosAssinaturas {
  status?: string;
  contrato_id?: string;
  page?: number;
  page_size?: number;
}

export function useAssinaturas(filtros?: FiltrosAssinaturas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['assinaturas', filtros],
    queryFn: async () => {
      const result = await api.get('/api/assinaturas', {
        status: filtros?.status,
        contrato_id: filtros?.contrato_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Assinatura[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useAssinatura(id?: string) {
  return useQuery({
    queryKey: ['assinatura', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/assinaturas/${id}`);
      return result.data as Assinatura;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useResumoAssinaturas() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['assinaturas-resumo'],
    queryFn: async () => {
      const result = await api.get('/api/assinaturas/resumo');
      return result.data as ResumoAssinaturas;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useEnviarAssinatura() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: EnviarAssinaturaData) => {
      const result = await api.post('/api/assinaturas/enviar', data);
      return result.data as Assinatura;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assinaturas'] });
      queryClient.invalidateQueries({ queryKey: ['assinaturas-resumo'] });
      toast.success('Documento enviado para assinatura!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar para assinatura', { description: error.message });
    },
  });
}

export function useCancelarAssinatura() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/assinaturas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assinaturas'] });
      queryClient.invalidateQueries({ queryKey: ['assinaturas-resumo'] });
      toast.success('Assinatura cancelada');
    },
    onError: (error: Error) => {
      toast.error('Erro ao cancelar assinatura', { description: error.message });
    },
  });
}
