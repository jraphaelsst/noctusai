import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface SiteConfig {
  id: string;
  org_id: string;
  nome_site: string;
  slug: string;
  logo_url?: string | null;
  cor_primaria: string;
  cor_secundaria: string;
  telefone?: string | null;
  whatsapp?: string | null;
  email_contato?: string | null;
  sobre?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface SitePreview {
  config: SiteConfig | null;
  imoveis: any[];
}

export function useSiteConfig() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['site-config'],
    queryFn: async () => {
      const result = await api.get('/api/site/config');
      return result.data as SiteConfig | null;
    },
    enabled: !!user,
  });
}

export function useCreateSiteConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      nome_site: string;
      slug: string;
      logo_url?: string;
      cor_primaria?: string;
      cor_secundaria?: string;
      telefone?: string;
      whatsapp?: string;
      email_contato?: string;
      sobre?: string;
    }) => {
      const result = await api.post('/api/site/config', data);
      return result.data as SiteConfig;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['site-config'] });
      queryClient.invalidateQueries({ queryKey: ['site-preview'] });
      toast.success('Site criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar site', { description: error.message });
    },
  });
}

export function useUpdateSiteConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Omit<SiteConfig, 'id' | 'org_id' | 'created_at'>>) => {
      const result = await api.patch('/api/site/config', data);
      return result.data as SiteConfig;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['site-config'] });
      queryClient.invalidateQueries({ queryKey: ['site-preview'] });
      toast.success('Configuração do site atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar configuração', { description: error.message });
    },
  });
}

export function useSitePreview() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['site-preview'],
    queryFn: async () => {
      const result = await api.get('/api/site/preview');
      return result.data as SitePreview;
    },
    enabled: !!user,
  });
}
