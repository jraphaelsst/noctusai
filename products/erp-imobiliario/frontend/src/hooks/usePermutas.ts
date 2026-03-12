import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface PerfilPermuta {
  id: string;
  owner_id: string;
  natureza: 'permuta_imovel' | 'permuta_automovel';
  valor: number;
  status: string;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
  tipo_imovel?: string | null;
  cep?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  estado?: string | null;
  zona?: string | null;
  condominio_nome?: string | null;
  quartos?: number | null;
  vagas?: number | null;
  tipo_veiculo?: string | null;
  marca?: string | null;
  modelo?: string | null;
  motor?: string | null;
  ano?: number | null;
  quilometragem?: number | null;
  faixa_preco_min?: number | null;
  faixa_preco_max?: number | null;
  regiao_preferida?: string[] | null;
  aceita_completar_diferenca?: boolean;
  limite_complemento?: number | null;
  metragem_min?: number | null;
  metragem_max?: number | null;
  quartos_min?: number | null;
  vagas_min?: number | null;
  ano_min?: number | null;
  ano_max?: number | null;
  quilometragem_max?: number | null;
}

export type NovoPerfilPermutaForm = Omit<PerfilPermuta, 'id' | 'owner_id' | 'created_at' | 'updated_at'>;

export function usePerfilsPermuta() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['permutas'],
    queryFn: async () => {
      const result = await api.get('/api/ativos', { natureza: 'permuta_imovel,permuta_automovel' });
      return (result.data || []) as PerfilPermuta[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePerfilPermuta(id?: string) {
  return useQuery({
    queryKey: ['permuta', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/ativos/${id}`);
      return result.data as PerfilPermuta;
    },
    enabled: !!id,
  });
}

export function useCreatePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: NovoPerfilPermutaForm) => {
      const result = await api.post('/api/ativos', {
        ...data,
        valor: data.valor || data.faixa_preco_min || 0,
      });
      return result.data as PerfilPermuta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      toast.success('Perfil de permuta criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar perfil de permuta', { description: error.message });
    },
  });
}

export function useUpdatePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<PerfilPermuta> & { id: string }) => {
      const result = await api.patch(`/api/ativos/${id}`, data);
      return result.data as PerfilPermuta;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      queryClient.invalidateQueries({ queryKey: ['permuta', variables.id] });
      toast.success('Permuta atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar permuta', { description: error.message });
    },
  });
}

export function useDeletePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/ativos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      toast.success('Permuta excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir permuta', { description: error.message });
    },
  });
}
