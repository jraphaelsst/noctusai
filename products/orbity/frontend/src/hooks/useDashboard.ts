/**
 * Dashboard KPI hooks — compose EXISTING endpoints only (no BE additions).
 * Each KPI is its own query so one failure never blanks the row.
 */
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { useFunil } from '@/hooks/useCrm';
import { useTasks } from '@/hooks/useTasks';
import { useCashFlow } from '@/hooks/useFinancial';
import { useAgendaEvents } from '@/hooks/useAgenda';
import { agendaWindow } from '@/lib/dashboardKpis';

export function useActiveClientCount() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ['orbity-dashboard-clients'],
    queryFn: async () => {
      const res = await api.get<{ total: number }>('/api/clients', {
        active_only: true,
        page: 1,
        page_size: 1,
      });
      return res.total;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useDashboardKpis() {
  const month = format(new Date(), 'yyyy-MM');
  const { from, to } = agendaWindow();
  return {
    month,
    clients: useActiveClientCount(),
    funil: useFunil(),
    tasks: useTasks(),
    cashFlow: useCashFlow(month),
    agenda: useAgendaEvents({ from, to }),
  };
}
