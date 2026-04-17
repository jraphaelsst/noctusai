import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Imovel {
  id: string;
  owner_id: string;
  natureza: 'imovel';
  valor: number;
  status: string;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
  tipo_imovel?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  estado?: string | null;
  zona?: string | null;
  condominio_id?: string | null;
  condominio_nome?: string | null;
  area_privativa?: number | null;
  area_total?: number | null;
  quartos?: number | null;
  suites?: number | null;
  banheiros?: number | null;
  vagas?: number | null;
  andar?: number | null;
  ano_construcao?: number | null;
  ref?: string | null;
  corretor?: string | null;
  proprietario_id?: string | null;
  aceita_permutas?: boolean;
  finalidade?: string | null;
  iptu?: number | null;
  pronto_para_portais?: boolean;
  titulo_anuncio?: string | null;
  descricao_seo?: string | null;
  fotos?: string[] | null;
  plantas?: string[] | null;
  palavras_chave?: string[] | null;
  pontos_de_interesse?: string[] | null;
  tour_virtual_url?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  lqs_score_hint?: string | null;
  observacoes_negociacao?: string | null;
  interesses?: any[];
}

export type NovoImovelForm = Omit<Imovel, 'id' | 'owner_id' | 'natureza' | 'created_at' | 'updated_at'>;

export function useImoveis() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['imoveis'],
    queryFn: async () => {
      const result = await api.get('/api/ativos', { natureza: 'imovel' });
      return (result.data || []) as Imovel[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useImovel(id?: string) {
  return useQuery({
    queryKey: ['imovel', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/ativos/${id}`);
      return result.data as Imovel;
    },
    enabled: !!id,
  });
}

export function useCreateImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: NovoImovelForm) => {
      const result = await api.post('/api/ativos', {
        ...data,
        natureza: 'imovel',
        fotos: data.fotos || [],
        plantas: data.plantas || [],
        palavras_chave: data.palavras_chave || [],
        pontos_de_interesse: data.pontos_de_interesse || [],
        interesses: data.interesses || [],
      });
      return result.data as Imovel;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Imóvel criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar imóvel', { description: error.message });
    },
  });
}

export function useUpdateImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Imovel> & { id: string }) => {
      const result = await api.patch(`/api/ativos/${id}`, data);
      return result.data as Imovel;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['imovel', variables.id] });
      toast.success('Imóvel atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar imóvel', { description: error.message });
    },
  });
}

export function useDeleteImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/ativos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Imóvel excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir imóvel', { description: error.message });
    },
  });
}
