import { useQuery } from '@tanstack/react-query';
import { supabase, useAuthStore } from '@noctusai/seed/infra';
import { useIsAdmin } from '@/hooks/useUserRole';
import { Negociacao, StatusNegociacao } from '@/types/imoveis';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useNegociacoes(filtroStatus: StatusNegociacao | 'todas') {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['negociacoes', user?.id, filtroStatus],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('negociacoes')
        .select('*')
        .order('created_at', { ascending: false });

      if (!isAdmin) {
        query = query.or(`cliente_proprietario_id.eq.${user.id},cliente_ofertante_id.eq.${user.id}`);
      }

      if (filtroStatus !== 'todas') {
        query = query.eq('status_etapa', filtroStatus);
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as Negociacao[];
    },
    enabled: !!user,
  });
}
