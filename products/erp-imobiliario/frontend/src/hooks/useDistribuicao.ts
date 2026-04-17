import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type {
  DistribuicaoConfig,
  FilaInfo,
  AtribuicaoResult,
  ModoDistribuicao,
} from '@/types/locacoes';

export function useDistribuicaoConfig() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['distribuicao', 'config'],
    queryFn: async () => {
      const result = await api.get('/api/distribuicao/config');
      return result.data as DistribuicaoConfig;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useDistribuicaoFila() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['distribuicao', 'fila'],
    queryFn: async () => {
      const result = await api.get('/api/distribuicao/fila');
      return result.data as FilaInfo;
    },
    enabled: !!user,
    staleTime: 1 * 60 * 1000,
  });
}

export function useUpdateDistribuicaoConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      modo?: ModoDistribuicao;
      corretores_ativos?: string[];
      regras?: Record<string, any>;
    }) => {
      const result = await api.patch('/api/distribuicao/config', data);
      return result.data as DistribuicaoConfig;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['distribuicao'] });
      toast.success('Configuração de distribuição atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar configuração', { description: error.message });
    },
  });
}

export function useAtribuirLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { cliente_id: string; corretor_id?: string }) => {
      const result = await api.post('/api/distribuicao/atribuir', data);
      return result.data as AtribuicaoResult;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['distribuicao'] });
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      if (data.atribuido) {
        toast.success('Lead atribuído com sucesso!');
      } else {
        toast.info(data.motivo || 'Lead não atribuído');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao atribuir lead', { description: error.message });
    },
  });
}
