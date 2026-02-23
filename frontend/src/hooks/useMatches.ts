import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface Match {
  id: string;
  ativo_origem_id: string;
  ativo_destino_id: string;
  score: number;
  status: 'pendente' | 'aceito' | 'rejeitado' | 'expirado';
  justificativa: string | null;
  detalhes: {
    compatibilidade_regiao: number;
    compatibilidade_preco: number;
    compatibilidade_specs: number;
    qualidade_anuncio: number;
    gap_valor: number;
  };
  created_at: string;
  updated_at: string;
  ativo_origem?: any;
  ativo_destino?: any;
}

export function useMatches(options?: {
  ativo_origem_id?: string;
  ativo_destino_id?: string;
  min_score?: number;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matches', options?.ativo_origem_id, options?.ativo_destino_id, options?.min_score],
    queryFn: async () => {
      const result = await api.get('/api/matching', {
        ativo_origem_id: options?.ativo_origem_id,
        ativo_destino_id: options?.ativo_destino_id,
        min_score: options?.min_score,
      });
      return (result.data || []) as Match[];
    },
    enabled: !!user,
  });
}

export function useMatchCounts() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['match-counts'],
    queryFn: async () => {
      const result = await api.get('/api/matching');
      const matches = result.data || [];
      const counts: Record<string, number> = {};
      matches.forEach((m: Match) => {
        counts[m.ativo_destino_id] = (counts[m.ativo_destino_id] || 0) + 1;
      });
      return counts;
    },
    enabled: !!user,
  });
}

export function useRecalcularMatches() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { ativo_origem_id?: string; ativo_destino_id?: string }) => {
      return api.post('/api/matching/gerar', params);
    },
    onSuccess: (_data) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      queryClient.invalidateQueries({ queryKey: ['match-counts'] });
      const total = _data?.total || 0;
      toast.success(`${total} match${total !== 1 ? 'es' : ''} encontrado${total !== 1 ? 's' : ''}!`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar matches', { description: error.message });
    },
  });
}

export function useAtualizarStatusMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ matchId, status }: { matchId: string; status: 'aceito' | 'rejeitado' }) => {
      const result = await api.patch(`/api/matching/${matchId}`, { status });
      return result.data as Match;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      queryClient.invalidateQueries({ queryKey: ['match-counts'] });
      toast.success(variables.status === 'aceito' ? 'Match aceito!' : 'Match rejeitado');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar match', { description: error.message });
    },
  });
}
