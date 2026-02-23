import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface Condominio {
  id: string;
  owner_id: string;
  nome: string;
  cep?: string | null;
  estado?: string | null;
  cidade?: string | null;
  bairro?: string | null;
  endereco?: string | null;
  numero?: number | null;
  km?: number | null;
  valor_condominio?: number | null;
  portaria?: boolean;
  piscina?: boolean;
  academia?: boolean;
  playground?: boolean;
  salao_festas?: boolean;
  churrasqueira?: boolean;
  created_at: string;
  updated_at: string;
}

export function useCondominios() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['condominios'],
    queryFn: async () => {
      const result = await api.get('/api/condominios');
      return (result.data || []) as Condominio[];
    },
    enabled: !!user,
  });
}

export function useCondominio(id?: string) {
  return useQuery({
    queryKey: ['condominio', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/condominios/${id}`);
      return result.data as Condominio;
    },
    enabled: !!id,
  });
}

export function useCreateCondominio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Omit<Condominio, 'id' | 'owner_id' | 'created_at' | 'updated_at'>) => {
      const result = await api.post('/api/condominios', data);
      return result.data as Condominio;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      toast.success('Condomínio criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar condomínio', { description: error.message });
    },
  });
}

export function useUpdateCondominio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Condominio> & { id: string }) => {
      const result = await api.patch(`/api/condominios/${id}`, data);
      return result.data as Condominio;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      toast.success('Condomínio atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar condomínio', { description: error.message });
    },
  });
}

export function useDeleteCondominio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/condominios/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      toast.success('Condomínio excluído!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir condomínio', { description: error.message });
    },
  });
}
