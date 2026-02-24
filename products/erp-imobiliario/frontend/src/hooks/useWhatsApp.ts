import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface WhatsAppConfigStatus {
  configured: boolean;
  api_version: string;
  phone_number_id_set: boolean;
  api_token_set: boolean;
  dry_run: boolean;
}

export interface WhatsAppMessage {
  id: string;
  phone: string;
  direction: 'sent' | 'received';
  message: string;
  message_type: 'text' | 'property_card' | 'image';
  metadata: Record<string, any>;
  status: 'sent' | 'delivered' | 'read' | 'failed';
  cliente_id?: string | null;
  created_at: string;
}

export interface SendMessageData {
  phone: string;
  message: string;
  cliente_id?: string;
}

export interface SendPropertyData {
  phone: string;
  imovel_id: string;
  cliente_id?: string;
  mensagem_adicional?: string;
}

export interface SendResult {
  message_id?: string;
  status: string;
  phone: string;
  dry_run: boolean;
  formatted_message?: string;
}

export function useWhatsAppConfig() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['whatsapp-config'],
    queryFn: async () => {
      const result = await api.get('/api/whatsapp/config');
      return result.data as WhatsAppConfigStatus;
    },
    enabled: !!user,
    staleTime: 10 * 60 * 1000,
  });
}

export function useWhatsAppHistory(phone?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['whatsapp-history', phone],
    queryFn: async () => {
      if (!phone) return { data: [], pagination: null };
      const result = await api.get(`/api/whatsapp/history/${encodeURIComponent(phone)}`);
      return {
        data: (result.data || []) as WhatsAppMessage[],
        pagination: result.pagination,
      };
    },
    enabled: !!user && !!phone,
  });
}

export function useSendWhatsAppMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: SendMessageData) => {
      const result = await api.post('/api/whatsapp/send', data);
      return result.data as SendResult;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['whatsapp-history'] });
      if (data.dry_run) {
        toast.success('Mensagem simulada com sucesso (modo teste)');
      } else {
        toast.success('Mensagem enviada com sucesso!');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar mensagem', { description: error.message });
    },
  });
}

export function useSendWhatsAppProperty() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: SendPropertyData) => {
      const result = await api.post('/api/whatsapp/send-property', data);
      return result.data as SendResult;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['whatsapp-history'] });
      if (data.dry_run) {
        toast.success('Imovel enviado em modo teste');
      } else {
        toast.success('Imovel enviado via WhatsApp!');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar imovel', { description: error.message });
    },
  });
}
