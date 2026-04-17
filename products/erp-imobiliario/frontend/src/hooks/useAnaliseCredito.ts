import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface AnaliseCredito {
  id: string;
  org_id: string;
  cliente_id?: string | null;
  cpf: string;
  nome: string;
  score?: number | null;
  status: 'pendente' | 'aprovado' | 'reprovado' | 'em_analise';
  resultado: Record<string, any>;
  fonte: 'serasa' | 'boa_vista' | 'manual';
  validade?: string | null;
  consultado_por: string;
  created_at: string;
}

export function useAnalisesCredito(filters?: {
  status?: string;
  fonte?: string;
  cpf?: string;
  cliente_id?: string;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['analises-credito', filters],
    queryFn: async () => {
      const result = await api.get('/api/analise-credito', filters);
      return (result.data || []) as AnaliseCredito[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useAnaliseCredito(id?: string) {
  return useQuery({
    queryKey: ['analise-credito', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/analise-credito/${id}`);
      return result.data as AnaliseCredito;
    },
    enabled: !!id,
  });
}

export function useConsultarCredito() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      cpf: string;
      nome: string;
      cliente_id?: string;
      fonte: 'serasa' | 'boa_vista' | 'manual';
      score?: number;
      resultado?: Record<string, any>;
      observacoes?: string;
    }) => {
      const result = await api.post('/api/analise-credito/consultar', data);
      return result.data as AnaliseCredito;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analises-credito'] });
      toast.success('Consulta de crédito realizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao consultar crédito', { description: error.message });
    },
  });
}

export function useAtualizarAnalise() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: {
      id: string;
      status?: 'pendente' | 'aprovado' | 'reprovado' | 'em_analise';
      score?: number;
      resultado?: Record<string, any>;
      validade?: string;
    }) => {
      const result = await api.patch(`/api/analise-credito/${id}`, data);
      return result.data as AnaliseCredito;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analises-credito'] });
      queryClient.invalidateQueries({ queryKey: ['analise-credito'] });
      toast.success('Análise atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar análise', { description: error.message });
    },
  });
}
