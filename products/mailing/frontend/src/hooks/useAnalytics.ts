import { useQuery } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface DashboardMetrics {
  total_contacts: number;
  active_contacts: number;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  total_campaigns: number;
}

export interface CampaignAnalytics {
  total: number;
  queued: number;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  bounced: number;
  complained: number;
  failed: number;
  open_rate: number;
  click_rate: number;
}

export function useDashboardMetrics() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => api.get("/api/analytics/dashboard"),
    enabled: !!user,
    staleTime: 30_000,
  });
}

export function useCampaignAnalytics(campaignId: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["analytics", "campaign", campaignId],
    queryFn: () => api.get(`/api/analytics/campaigns/${campaignId}`),
    enabled: !!user && !!campaignId,
    refetchInterval: 15_000,
  });
}
