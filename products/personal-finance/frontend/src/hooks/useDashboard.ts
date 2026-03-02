import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";
import type { DashboardKPIs, DashboardResumo } from "@/types";

export function useDashboardKPIs() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["dashboard", "kpis"],
    queryFn: async () => {
      const result = await api.get("/api/dashboard/kpis");
      return result.data as DashboardKPIs;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useDashboardResumo() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["dashboard", "resumo"],
    queryFn: async () => {
      const result = await api.get("/api/dashboard/resumo");
      return result.data as DashboardResumo;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}
