import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';
import type { Conversation, ConversationFilter } from '@/types/messaging';

const KEYS = {
  all: ['conversations'] as const,
  list: (filter?: ConversationFilter) => ['conversations', 'list', filter] as const,
  unread: ['conversations', 'unread-count'] as const,
};

interface ConversationsResponse {
  data: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

export function useConversations(filter?: ConversationFilter) {
  const { user } = useAuthStore();
  return useQuery<ConversationsResponse>({
    queryKey: KEYS.list(filter),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filter && filter !== 'todas') params.set('filter', filter);
      const url = `/api/conversations${params.toString() ? `?${params}` : ''}`;
      const res = await api.get(url);
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 10 * 1000,
    refetchInterval: 5 * 1000,
  });
}

export function useUnreadCount() {
  const { user } = useAuthStore();
  return useQuery<{ count: number }>({
    queryKey: KEYS.unread,
    queryFn: async () => {
      const res = await api.get('/api/conversations/unread-count');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 10 * 1000,
    refetchInterval: 15 * 1000,
  });
}

export function useStartConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { participant_user_id?: string; participant_clinic_id?: string; is_support?: boolean; initial_message?: string }) => {
      const res = await api.post('/api/conversations', data);
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEYS.all });
    },
    onError: () => {
      toast.error('Erro ao iniciar conversa');
    },
  });
}

export function useArchiveConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (conversationId: string) => {
      const res = await api.post(`/api/conversations/${conversationId}/archive`, {});
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Conversa arquivada');
    },
    onError: () => {
      toast.error('Erro ao arquivar conversa');
    },
  });
}

export function useMuteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ conversationId, mute }: { conversationId: string; mute: boolean }) => {
      const res = await api.post(`/api/conversations/${conversationId}/mute?mute=${mute}`, {});
      return res.data ?? res;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: KEYS.all });
      toast.success(variables.mute ? 'Conversa silenciada' : 'Notificacoes ativadas');
    },
    onError: () => {
      toast.error('Erro ao alterar silenciamento');
    },
  });
}
