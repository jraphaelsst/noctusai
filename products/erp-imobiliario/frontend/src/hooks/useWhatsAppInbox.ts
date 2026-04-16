import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Conversation {
  phone: string;
  last_message: string;
  last_time: string;
  unread: number;
  cliente_nome?: string;
}

export interface Message {
  id: string;
  phone: string;
  direction: string;
  message: string;
  message_type: string;
  status: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useWhatsAppConversations() {
  return useQuery({
    queryKey: ['whatsapp-conversations'],
    queryFn: async () => {
      const result = await api.get('/api/whatsapp/conversations');
      return (result.data || []) as Conversation[];
    },
    refetchInterval: 15000,
  });
}

export function useWhatsAppMessages(selectedPhone: string | null) {
  return useQuery({
    queryKey: ['whatsapp-messages', selectedPhone],
    queryFn: async () => {
      if (!selectedPhone) return [];
      const result = await api.get('/api/whatsapp/messages', { phone: selectedPhone });
      return (result.data || []) as Message[];
    },
    enabled: !!selectedPhone,
    refetchInterval: 5000,
  });
}

export function useWhatsAppConfig() {
  return useQuery({
    queryKey: ['whatsapp-config'],
    queryFn: async () => {
      const result = await api.get('/api/whatsapp/config');
      return result.data;
    },
    retry: false,
  });
}

export function useSendWhatsAppMessage(selectedPhone: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ phone, message }: { phone: string; message: string }) => {
      return api.post('/api/whatsapp/send', { phone, message });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whatsapp-messages', selectedPhone] });
      queryClient.invalidateQueries({ queryKey: ['whatsapp-conversations'] });
    },
    onError: () => toast.error('Erro ao enviar mensagem'),
  });
}
