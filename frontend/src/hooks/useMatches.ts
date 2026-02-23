import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';

const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || '';

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

async function getAuthToken(): Promise<string> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error('Não autenticado');
  return session.access_token;
}

async function callBackendAPI(endpoint: string, options: RequestInit = {}) {
  const token = await getAuthToken();
  const response = await fetch(`${BACKEND_API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(error.detail || error.error || 'Erro na requisição');
  }
  return response.json();
}

/**
 * Fetch persisted matches from the database.
 */
export function useMatches(options?: {
  ativo_origem_id?: string;
  ativo_destino_id?: string;
  min_score?: number;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matches', options?.ativo_origem_id, options?.ativo_destino_id, options?.min_score],
    queryFn: async () => {
      if (BACKEND_API_URL) {
        const params = new URLSearchParams();
        if (options?.ativo_origem_id) params.set('ativo_origem_id', options.ativo_origem_id);
        if (options?.ativo_destino_id) params.set('ativo_destino_id', options.ativo_destino_id);
        if (options?.min_score) params.set('min_score', String(options.min_score));
        const result = await callBackendAPI(`/api/matching?${params.toString()}`);
        return (result.data || []) as Match[];
      } else {
        let query = supabase
          .from('matches')
          .select(`
            *,
            ativo_origem:ativos!matches_ativo_origem_id_fkey(
              id, natureza, tipo_imovel, valor, aceita_permutas,
              cidade, estado, bairro, cep,
              area_privativa, area_total, quartos, vagas,
              titulo_anuncio, fotos, owner_id, status,
              marca, modelo, tipo_veiculo
            ),
            ativo_destino:ativos!matches_ativo_destino_id_fkey(
              id, natureza, tipo_imovel, valor,
              faixa_preco_min, faixa_preco_max, regiao_preferida,
              aceita_completar_diferenca, limite_complemento,
              marca, modelo, tipo_veiculo, status
            )
          `)
          .order('score', { ascending: false });

        if (options?.ativo_origem_id) query = query.eq('ativo_origem_id', options.ativo_origem_id);
        if (options?.ativo_destino_id) query = query.eq('ativo_destino_id', options.ativo_destino_id);
        if (options?.min_score) query = query.gte('score', options.min_score);

        const { data, error } = await query;
        if (error) throw error;
        return (data || []) as Match[];
      }
    },
    enabled: !!user,
  });
}

/**
 * Count matches per ativo_destino_id for badge display.
 */
export function useMatchCounts() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['match-counts'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('matches')
        .select('ativo_destino_id, score');
      if (error) throw error;

      const counts: Record<string, number> = {};
      (data || []).forEach((match) => {
        const key = match.ativo_destino_id;
        counts[key] = (counts[key] || 0) + 1;
      });
      return counts;
    },
    enabled: !!user,
  });
}

/**
 * Trigger matching recalculation.
 */
export function useRecalcularMatches() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { ativo_origem_id?: string; ativo_destino_id?: string }) => {
      if (BACKEND_API_URL) {
        return callBackendAPI('/api/matching/gerar', {
          method: 'POST',
          body: JSON.stringify(params),
        });
      } else {
        const { data, error } = await supabase.functions.invoke('gerar-matches', {
          body: params,
        });
        if (error) throw error;
        return data;
      }
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

/**
 * Update match status.
 */
export function useAtualizarStatusMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ matchId, status }: { matchId: string; status: 'aceito' | 'rejeitado' }) => {
      if (BACKEND_API_URL) {
        return callBackendAPI(`/api/matching/${matchId}`, {
          method: 'PATCH',
          body: JSON.stringify({ status }),
        });
      } else {
        const { data, error } = await supabase
          .from('matches')
          .update({ status, updated_at: new Date().toISOString() })
          .eq('id', matchId)
          .select()
          .single();
        if (error) throw error;
        return data as Match;
      }
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
