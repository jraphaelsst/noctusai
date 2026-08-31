import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface ScoreBreakdown {
  embedding_similarity: number;
  compatibilidade_regiao: number;
  compatibilidade_preco: number;
  compatibilidade_specs: number;
  qualidade_anuncio: number;
  interesses: number;
}

export interface Match {
  id: string;
  ativo_origem_id: string;
  ativo_destino_id: string;
  score: number;
  score_breakdown: ScoreBreakdown | null;
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
  ativo_origem?: Record<string, unknown>;
  ativo_destino?: Record<string, unknown>;
}

export function useMatches(options?: {
  ativo_origem_id?: string;
  ativo_destino_id?: string;
  status?: string;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matches', options?.ativo_origem_id, options?.ativo_destino_id, options?.status],
    queryFn: async () => {
      const result = await api.get('/api/matching', {
        ativo_origem_id: options?.ativo_origem_id,
        ativo_destino_id: options?.ativo_destino_id,
        status: options?.status,
      });
      return (result.data || []) as Match[];
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}

export function useMatchCounts() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['match-counts'],
    queryFn: async () => {
      const result = await api.get('/api/matching/counts');
      return (result.data || {}) as Record<string, number>;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecalcularMatches() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params?: { ativo_origem_id?: string; ativo_destino_id?: string }) => {
      return api.post('/api/matching/gerar', params || {});
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

export function useEmbedAtivo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (ativoId: string) => {
      return api.post('/api/matching/embed', { ativo_id: ativoId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      toast.success('Embedding gerado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar embedding', { description: error.message });
    },
  });
}

export function useEmbedBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      return api.post('/api/matching/embed-batch', {});
    },
    onSuccess: (data: Record<string, unknown>) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      const embedded = (data?.embedded as number) || 0;
      toast.success(`${embedded} ativo(s) embedado(s) com sucesso!`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar embeddings em lote', { description: error.message });
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
    // Optimistic accept/reject: sets `status` on the matching row of every
    // cached `['matches', ...]` list immediately; `onError` rolls back to the
    // pre-mutation snapshot. Same rollback discipline as
    // products/social-wiring/frontend/src/hooks/useCardHub.ts
    // useSetClienteTagsMutation (~L235).
    onMutate: async ({ matchId, status }: { matchId: string; status: 'aceito' | 'rejeitado' }) => {
      await queryClient.cancelQueries({ queryKey: ['matches'] });
      const previousQueries = queryClient.getQueriesData<Match[]>({ queryKey: ['matches'] });
      previousQueries.forEach(([queryKey, data]) => {
        if (!data) return;
        queryClient.setQueryData<Match[]>(
          queryKey,
          data.map((m) => (m.id === matchId ? { ...m, status } : m)),
        );
      });
      return { previousQueries };
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      queryClient.invalidateQueries({ queryKey: ['match-counts'] });
      toast.success(variables.status === 'aceito' ? 'Match aceito!' : 'Match rejeitado');
    },
    onError: (error: Error, _variables, context) => {
      context?.previousQueries?.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
      toast.error('Erro ao atualizar match', { description: error.message });
    },
  });
}
