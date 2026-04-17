import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Campaign {
  id: string;
  nome: string;
  template_id?: string;
  list_id?: string;
  assunto_override?: string;
  remetente_nome?: string;
  remetente_email?: string;
  status: "rascunho" | "agendada" | "enviando" | "enviada" | "pausada" | "cancelada";
  scheduled_at?: string;
  started_at?: string;
  completed_at?: string;
  total_recipients: number;
  total_sent: number;
  total_failed: number;
  created_at: string;
  stats?: CampaignStats;
}

export interface CampaignStats {
  total: number;
  queued: number;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  bounced: number;
  complained: number;
  failed: number;
}

export function useCampaigns(status?: string) {
  const { user } = useAuthStore();
  const params = status ? `?status=${status}` : "";
  return useQuery({
    queryKey: ["campaigns", status],
    queryFn: () => api.get(`/api/campaigns${params}`),
    enabled: !!user,
  });
}

export function useCampaign(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["campaign", id],
    queryFn: () => api.get(`/api/campaigns/${id}`),
    enabled: !!user && !!id,
    refetchInterval: 10000, // poll every 10s for live stats during sending
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Campaign>) => api.post("/api/campaigns", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useUpdateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<Campaign>) =>
      api.patch(`/api/campaigns/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useDeleteCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/campaigns/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useScheduleCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, scheduled_at }: { id: string; scheduled_at: string }) =>
      api.post(`/api/campaigns/${id}/schedule`, { scheduled_at }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useSendCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/campaigns/${id}/send`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function usePauseCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/campaigns/${id}/pause`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useCancelCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/campaigns/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}
