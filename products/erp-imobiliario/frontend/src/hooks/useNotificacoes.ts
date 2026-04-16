import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { createNotificationHooks } from '@noctusai/lib/notifications';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import type { NotificacaoPreferencia } from '@/types/notificacoes';

export type { Notificacao, ContagemNaoLidas } from '@noctusai/lib/notifications';

// Core notification hooks (shared across all products)
export const {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
} = createNotificationHooks(api, useAuthStore);

// ERP-specific: notification preferences (stored in erp.notificacao_preferencias)

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
