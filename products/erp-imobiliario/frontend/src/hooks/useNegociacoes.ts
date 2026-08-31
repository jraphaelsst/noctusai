import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { Negociacao, StatusNegociacao } from '@/types/imoveis';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
//
// Routes through backend `/api/negociacoes` (Pattern D resolution, Phase 4,
// 2026-05-20). The pre-existing role-aware visibility filter (admin sees
// everything; non-admin sees rows where they are proprietario or ofertante)
// now lives on the backend — security: tampered client predicates can no
// longer broaden visibility.

export function useNegociacoes(filtroStatus: StatusNegociacao | 'todas') {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['negociacoes', user?.id, filtroStatus],
    queryFn: async () => {
      if (!user) return [];
      const query =
        filtroStatus && filtroStatus !== 'todas'
          ? `?status_etapa=${encodeURIComponent(filtroStatus)}`
          : '';
      const res = await api.get<{ data: Negociacao[] }>(`/api/negociacoes${query}`);
      return (res.data || []) as Negociacao[];
    },
    enabled: !!user,
    placeholderData: (prev) => prev,
  });
}
