import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LeaderboardEntry {
  user_id: string;
  total_pontos: number;
  rank: number;
  nome: string;
  avatar_url?: string;
}

export interface Pontuacao {
  id: string;
  user_id: string;
  acao: string;
  pontos: number;
  referencia_id?: string;
  referencia_tipo?: string;
  created_at: string;
}

export interface Conquista {
  tipo: string;
  nome: string;
  descricao: string;
  icone: string;
  desbloqueada: boolean;
  desbloqueada_em?: string;
}

export interface RegrasGamificacao {
  pontos_por_acao: Record<string, number>;
  conquistas_disponiveis: Array<{
    tipo: string;
    nome: string;
    descricao: string;
    icone: string;
  }>;
}

type Periodo = 'semana' | 'mes' | 'geral';

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useLeaderboard(periodo: Periodo = 'geral') {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['leaderboard', periodo],
    queryFn: async () => {
      const result = await api.get('/api/gamificacao/leaderboard', { periodo });
      return (result.data || []) as LeaderboardEntry[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useMeusPontos(page: number = 1) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['meus-pontos', page],
    queryFn: async () => {
      const result = await api.get('/api/gamificacao/pontos', { page, page_size: 50 });
      return result as {
        data: Pontuacao[];
        pagination: { page: number; page_size: number; total: number } | null;
        total_pontos?: number;
      };
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useMinhasConquistas() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['minhas-conquistas'],
    queryFn: async () => {
      const result = await api.get('/api/gamificacao/conquistas');
      return (result.data || []) as Conquista[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRegrasGamificacao() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['regras-gamificacao'],
    queryFn: async () => {
      const result = await api.get('/api/gamificacao/regras');
      return result.data as RegrasGamificacao;
    },
    enabled: !!user,
    staleTime: 30 * 60 * 1000,
  });
}

export function useRegistrarPontos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      acao: string;
      referencia_id?: string;
      referencia_tipo?: string;
    }) => {
      const result = await api.post('/api/gamificacao/registrar', data);
      return result.data as {
        pontos: number;
        acao: string;
        novas_conquistas: Array<{ tipo: string; nome: string }>;
      };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] });
      queryClient.invalidateQueries({ queryKey: ['meus-pontos'] });
      queryClient.invalidateQueries({ queryKey: ['minhas-conquistas'] });
      if (data.novas_conquistas.length > 0) {
        for (const conquista of data.novas_conquistas) {
          toast.success(`Nova conquista desbloqueada: ${conquista.nome}!`);
        }
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar pontos', { description: error.message });
    },
  });
}
