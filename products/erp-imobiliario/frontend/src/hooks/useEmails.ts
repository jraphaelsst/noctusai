import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Email {
  id: string;
  cliente_id?: string;
  remetente: string;
  destinatario: string;
  assunto: string;
  corpo: string;
  corpo_html?: string;
  direcao: 'enviado' | 'recebido';
  status: 'rascunho' | 'enviado' | 'entregue' | 'aberto' | 'erro';
  template_id?: string;
  aberturas: number;
  cliques: number;
  created_at: string;
}

export interface EmailTemplate {
  id: string;
  nome: string;
  assunto: string;
  corpo: string;
  variaveis: string[];
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

interface FiltrosEmails {
  cliente_id?: string;
  direcao?: string;
  status?: string;
  data_inicio?: string;
  data_fim?: string;
  page?: number;
  page_size?: number;
}

interface FiltrosTemplates {
  page?: number;
  page_size?: number;
}

export function useEmails(filtros?: FiltrosEmails) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['emails', filtros],
    queryFn: async () => {
      const result = await api.get('/api/emails', {
        cliente_id: filtros?.cliente_id,
        direcao: filtros?.direcao,
        status: filtros?.status,
        data_inicio: filtros?.data_inicio,
        data_fim: filtros?.data_fim,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Email[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useEmail(id?: string) {
  return useQuery({
    queryKey: ['email', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/emails/${id}`);
      return result.data as Email;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useEnviarEmail() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      destinatario: string;
      assunto: string;
      corpo: string;
      cliente_id?: string;
      template_id?: string;
    }) => {
      const result = await api.post('/api/emails/enviar', data);
      return result.data as Email;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      toast.success('Email enviado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar email', { description: error.message });
    },
  });
}

export function useEmailTemplates(filtros?: FiltrosTemplates) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['email-templates', filtros],
    queryFn: async () => {
      const result = await api.get('/api/emails/templates', {
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as EmailTemplate[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      nome: string;
      assunto: string;
      corpo: string;
      variaveis?: string[];
    }) => {
      const result = await api.post('/api/emails/templates', data);
      return result.data as EmailTemplate;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      toast.success('Template criado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar template', { description: error.message });
    },
  });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: {
      id: string;
      nome?: string;
      assunto?: string;
      corpo?: string;
      variaveis?: string[];
      ativo?: boolean;
    }) => {
      const result = await api.patch(`/api/emails/templates/${id}`, data);
      return result.data as EmailTemplate;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      toast.success('Template atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar template', { description: error.message });
    },
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/emails/templates/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      toast.success('Template excluido!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir template', { description: error.message });
    },
  });
}
