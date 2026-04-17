import { useQuery } from "@tanstack/react-query";
import { useAuthStore, api } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TaskStats {
  total: number;
  pendente: number;
  em_progresso: number;
  concluida: number;
  cancelada: number;
}

export interface MetricsResume {
  dias_analisados: number;
  score_medio: number | null;
  total_tarefas_concluidas: number;
  total_checkins: number;
  streak_dias: number;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useDashboardTaskStats() {
  const { user } = useAuthStore();

  return useQuery<{ data: TaskStats }>({
    queryKey: ["dashboard-task-stats"],
    queryFn: () => api.get("/api/tasks/stats/resumo"),
    enabled: !!user,
    staleTime: 60_000,
  });
}

export function useDashboardMetrics() {
  const { user } = useAuthStore();

  return useQuery<{ data: MetricsResume }>({
    queryKey: ["dashboard-metrics"],
    queryFn: () => api.get("/api/metricas/resumo?dias=7"),
    enabled: !!user,
    staleTime: 60_000,
  });
}

export function useDashboardTodayEvents() {
  const { user } = useAuthStore();

  return useQuery<{ data: any[]; pagination: any }>({
    queryKey: ["dashboard-today-events"],
    queryFn: () => {
      const today = new Date().toISOString().slice(0, 10);
      const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
      return api.get(`/api/schedule?data_inicio=${today}T00:00:00&data_fim=${tomorrow}T00:00:00&page_size=10`);
    },
    enabled: !!user,
    staleTime: 60_000,
  });
}
