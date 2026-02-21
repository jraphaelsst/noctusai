import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';

// --- Configuration ---
// Set to your FastAPI backend URL. Falls back to Supabase Edge Functions if empty.
const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || '';

// Match as stored in the database
export interface Match {
  id: string;
  imovel_id: string;
  perfil_permuta_id: string;
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
  // Joined data
  imovel?: any;
  perfil_permuta?: any;
}

// --- Internal helpers ---

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

async function callMatchingAPI(params: { imovel_id?: string; perfil_permuta_id?: string }) {
  if (BACKEND_API_URL) {
    // Call FastAPI backend
    return callBackendAPI('/api/matching/gerar', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  } else {
    // Fallback: call Supabase Edge Function
    const { data, error } = await supabase.functions.invoke('gerar-matches', {
      body: params,
    });
    if (error) throw error;
    return data;
  }
}

// --- Hooks ---

/**
 * Fetch persisted matches from the database.
 * Can filter by imovel_id, perfil_permuta_id, or min_score.
 */
export function useMatches(options?: {
  imovel_id?: string;
  perfil_permuta_id?: string;
  min_score?: number;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matches', options?.imovel_id, options?.perfil_permuta_id, options?.min_score],
    queryFn: async () => {
      if (BACKEND_API_URL) {
        // Call FastAPI backend
        const params = new URLSearchParams();
        if (options?.imovel_id) params.set('imovel_id', options.imovel_id);
        if (options?.perfil_permuta_id) params.set('perfil_permuta_id', options.perfil_permuta_id);
        if (options?.min_score) params.set('min_score', String(options.min_score));

        const result = await callBackendAPI(`/api/matching?${params.toString()}`);
        return (result.data || []) as Match[];
      } else {
        // Fallback: read directly from Supabase
        let query = supabase
          .from('matches')
          .select(`
            *,
            imovel:imoveis!matches_imovel_id_fkey(
              id, tipo, preco_pedido, aceita_permutas,
              cidade, estado, bairro, cep,
              area_privativa, area_total, quartos, vagas,
              titulo_anuncio, fotos, owner_id, status
            ),
            perfil_permuta:perfis_permutas!matches_perfil_permuta_id_fkey(
              id, categoria, tipo_imovel, tipo_movel,
              faixa_preco_min, faixa_preco_max, regiao_preferida,
              aceita_completar_diferenca, limite_complemento,
              valor_estimado, cliente_ofertante_id, status
            )
          `)
          .order('score', { ascending: false });

        if (options?.imovel_id) query = query.eq('imovel_id', options.imovel_id);
        if (options?.perfil_permuta_id) query = query.eq('perfil_permuta_id', options.perfil_permuta_id);
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
 * Count matches per perfil_permuta_id for badge display.
 */
export function useMatchCounts() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['match-counts'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('matches')
        .select('perfil_permuta_id, score');

      if (error) throw error;

      const counts: Record<string, number> = {};
      (data || []).forEach((match) => {
        const key = match.perfil_permuta_id;
        counts[key] = (counts[key] || 0) + 1;
      });

      return counts;
    },
    enabled: !!user,
  });
}

/**
 * Trigger the matching algorithm to recalculate matches.
 * Calls FastAPI backend if VITE_BACKEND_API_URL is set, otherwise Supabase Edge Function.
 */
export function useRecalcularMatches() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { imovel_id?: string; perfil_permuta_id?: string }) => {
      return callMatchingAPI(params);
    },
    onSuccess: (_data) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      queryClient.invalidateQueries({ queryKey: ['match-counts'] });

      const total = _data?.total || 0;
      toast.success(`${total} match${total !== 1 ? 'es' : ''} encontrado${total !== 1 ? 's' : ''}!`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar matches', {
        description: error.message,
      });
    },
  });
}

/**
 * Update the status of a match (aceitar/rejeitar).
 */
export function useAtualizarStatusMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ matchId, status }: { matchId: string; status: 'aceito' | 'rejeitado' }) => {
      if (BACKEND_API_URL) {
        // Call FastAPI backend
        return callBackendAPI(`/api/matching/${matchId}`, {
          method: 'PATCH',
          body: JSON.stringify({ status }),
        });
      } else {
        // Fallback: update directly via Supabase
        const { data, error } = await supabase
          .from('matches')
          .update({ status, updated_at: new Date().toISOString() })
          .eq('id', matchId)
          .select()
          .single();

        if (error) throw error;

        const { data: { user } } = await supabase.auth.getUser();
        if (user) {
          supabase.from('user_actions_log').insert([{
            usuario_id: user.id,
            tipo_acao: 'editar',
            tipo_entidade: 'match',
            entidade_id: matchId,
            descricao: `${status === 'aceito' ? 'Aceitou' : 'Rejeitou'} match ${matchId}`,
          }]).then();
        }

        return data as Match;
      }
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['matches'] });
      queryClient.invalidateQueries({ queryKey: ['match-counts'] });
      toast.success(
        variables.status === 'aceito' ? 'Match aceito!' : 'Match rejeitado'
      );
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar match', {
        description: error.message,
      });
    },
  });
}
