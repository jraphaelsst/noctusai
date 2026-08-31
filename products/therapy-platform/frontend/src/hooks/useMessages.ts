import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore, supabase } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { Message } from '@/types/messaging';

const KEYS = {
  all: ['messages'] as const,
  list: (conversationId: string, page?: number) => ['messages', conversationId, page] as const,
};

interface MessagesResponse {
  data: Message[];
  total: number;
  page: number;
  page_size: number;
}

// `KEYS.list(conversationId, page)` has two independently-changing axes,
// and they need OPPOSITE placeholderData treatment:
//
//   - `page` changing within the SAME conversation is the same person's
//     thread — keeping the previous page mounted while the next loads is a
//     legitimate pagination-flicker fix.
//   - `conversationId` changing is a DIFFERENT person's private thread.
//     Reusing the previous conversation's `data` here would render one
//     patient's messages under the newly-selected patient's header until
//     the real fetch resolves — the same cross-patient exposure class
//     documented (and refused) in useClinicalRecords / useLongitudinal /
//     useConsents / useJournal. This is NOT a style choice; do not widen
//     it to `(prev) => prev` in a future sweep.
//
// So the placeholder is scoped by comparing the previous query's own
// conversationId (via TanStack's `previousQuery` callback arg) against the
// CURRENT conversationId — only reused when they match.
// Per `KB § PATTERNS/frontend/lying-loading-state.md` § Key-changing queries.
export function useMessages(conversationId?: string, page = 1, pageSize = 50) {
  const { user } = useAuthStore();
  return useQuery<MessagesResponse>({
    queryKey: KEYS.list(conversationId!, page),
    queryFn: async () => {
      const res = await api.get(
        `/api/conversations/${conversationId}/messages?page=${page}&page_size=${pageSize}`
      );
      return res.data ?? res;
    },
    placeholderData: (prevData, prevQuery) => {
      const prevConversationId = prevQuery?.queryKey[1];
      return prevConversationId === conversationId ? prevData : undefined;
    },
    enabled: !!user && !!conversationId,
    staleTime: 5 * 1000,
    refetchInterval: 3 * 1000,
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      conversationId,
      ...body
    }: {
      conversationId: string;
      message_type: 'text' | 'image' | 'audio';
      content?: string;
      file_url?: string;
      file_type?: string;
      file_size?: number;
    }) => {
      const res = await api.post(`/api/conversations/${conversationId}/messages`, body);
      return res.data ?? res;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: KEYS.list(variables.conversationId) });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
    onError: () => {
      toast.error('Erro ao enviar mensagem');
    },
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (conversationId: string) => {
      const res = await api.patch(`/api/conversations/${conversationId}/read`, {});
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useDeleteMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (messageId: string) => {
      const res = await api.delete(`/api/conversations/messages/${messageId}`);
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEYS.all });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      toast.success('Mensagem excluida');
    },
    onError: () => {
      toast.error('Erro ao excluir mensagem');
    },
  });
}

export function useReportMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ messageId, reason }: { messageId: string; reason: string }) => {
      const res = await api.post(`/api/conversations/messages/${messageId}/report`, { reason });
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Denuncia enviada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao denunciar mensagem');
    },
  });
}

export function useBlockUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await api.post('/api/conversations/block', { user_id: userId });
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      toast.success('Usuario bloqueado');
    },
    onError: () => {
      toast.error('Erro ao bloquear usuario');
    },
  });
}

export function useUnblockUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await api.delete(`/api/conversations/block/${userId}`);
      return res.data ?? res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      toast.success('Usuario desbloqueado');
    },
    onError: () => {
      toast.error('Erro ao desbloquear usuario');
    },
  });
}

export function useUploadAttachment() {
  return useMutation({
    mutationFn: async (file: File) => {
      const token = await getToken();
      const formData = new FormData();
      formData.append('file', file);

      const baseUrl = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8003';
      let resp = await fetch(`${baseUrl}/api/attachments/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (resp.status === 401) {
        const { data: { session } } = await supabase.auth.refreshSession();
        if (session) {
          resp = await fetch(`${baseUrl}/api/attachments/upload`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${session.access_token}` },
            body: formData,
          });
        }
      }

      if (!resp.ok) {
        throw new Error('Falha no upload do arquivo');
      }

      return resp.json();
    },
    onError: () => {
      toast.error('Erro ao enviar arquivo');
    },
  });
}

async function getToken(): Promise<string> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error('Nao autenticado');
  return session.access_token;
}
