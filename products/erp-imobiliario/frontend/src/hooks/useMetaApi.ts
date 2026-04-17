import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type { MetaConfig, MetaLead, MetaCampanha } from '@/types/meta_api';

export function useMetaConfig() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['meta-config'],
    queryFn: async () => {
      const result = await api.get('/api/meta/config');
      return result.data as MetaConfig | null;
    },
    enabled: !!user,
  });
}

export function useSalvarMetaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<MetaConfig>) => {
      const result = await api.post('/api/meta/config', data);
      return result.data as MetaConfig;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['meta-config'] });
      toast.success('Configuração Meta salva com sucesso');
    },
    onError: (error: Error) => {
      toast.error('Erro ao salvar configuração', { description: error.message });
    },
  });
}

export function useMetaLeads(page = 1, pageSize = 20, importado?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['meta-leads', page, pageSize, importado],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (importado !== undefined) params.set('importado', String(importado));
      const result = await api.get(`/api/meta/leads?${params}`);
      return {
        data: (result.data || []) as MetaLead[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
  });
}

export function useSyncMetaLeads() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formId?: string) => {
      const params = formId ? `?form_id=${formId}` : '';
      const result = await api.post(`/api/meta/leads/sync${params}`);
      return result.data as { total_fetched: number; imported: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['meta-leads'] });
      toast.success(`Sincronizado: ${data.imported} novos leads importados`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao sincronizar leads', { description: error.message });
    },
  });
}

export function useImportarLeadComoCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (leadId: string) => {
      const result = await api.post(`/api/meta/leads/${leadId}/importar`);
      return result.data as { cliente_id: string; lead_id: string };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['meta-leads'] });
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      toast.success('Lead importado como cliente com sucesso');
    },
    onError: (error: Error) => {
      toast.error('Erro ao importar lead', { description: error.message });
    },
  });
}

export function useMetaCampanhas(page = 1, pageSize = 20) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['meta-campanhas', page, pageSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      const result = await api.get(`/api/meta/campanhas?${params}`);
      return {
        data: (result.data || []) as MetaCampanha[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
  });
}

export function useSyncMetaCampanhas() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post('/api/meta/campanhas/sync');
      return result.data as { total_synced: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['meta-campanhas'] });
      toast.success(`${data.total_synced} campanhas sincronizadas`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao sincronizar campanhas', { description: error.message });
    },
  });
}
