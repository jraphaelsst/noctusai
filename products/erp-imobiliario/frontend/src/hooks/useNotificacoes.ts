import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import type { Notificacao, NotificacaoPreferencia, ContagemNaoLidas } from '@/types/notificacoes';

export function useNotificacoes(page = 1, pageSize = 20, apenasNaoLidas = false) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['notificacoes', page, pageSize, apenasNaoLidas],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (apenasNaoLidas) params.set('apenas_nao_lidas', 'true');
      const result = await api.get(`/api/notificacoes?${params}`);
      return {
        data: (result.data || []) as Notificacao[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
  });
}

export function useContagemNaoLidas() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['notificacoes-contagem'],
    queryFn: async () => {
      const result = await api.get('/api/notificacoes/contagem');
      return result.data as ContagemNaoLidas;
    },
    enabled: !!user,
    refetchInterval: 30000, // Poll every 30s
  });
}

export function useMarcarComoLida() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (notificacaoId: string) => {
      const result = await api.patch(`/api/notificacoes/${notificacaoId}/ler`);
      return result.data as Notificacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notificacoes'] });
      queryClient.invalidateQueries({ queryKey: ['notificacoes-contagem'] });
    },
  });
}

export function useMarcarTodasComoLidas() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post('/api/notificacoes/ler-todas');
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notificacoes'] });
      queryClient.invalidateQueries({ queryKey: ['notificacoes-contagem'] });
      toast.success('Todas as notificações marcadas como lidas');
    },
  });
}

export function useNotificacaoPreferencias() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['notificacao-preferencias'],
    queryFn: async () => {
      const result = await api.get('/api/notificacoes/preferencias');
      return (result.data || []) as NotificacaoPreferencia[];
    },
    enabled: !!user,
  });
}

export function useAtualizarPreferencia() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { canal: string; tipo_evento: string; ativo: boolean }) => {
      const result = await api.patch('/api/notificacoes/preferencias', data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notificacao-preferencias'] });
      toast.success('Preferência atualizada');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar preferência', { description: error.message });
    },
  });
}
