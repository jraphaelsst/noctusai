import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface SenderDomain {
  id: string;
  domain: string;
  status: "pending" | "verified" | "failed";
  dns_records?: Record<string, any>;
  verified_at?: string;
  created_at: string;
}

export function useDomains() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["settings", "domains"],
    queryFn: () => api.get("/api/settings/domains"),
    enabled: !!user,
  });
}

export function useAddDomain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (domain: string) => api.post("/api/settings/domains", { domain }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "domains"] }),
  });
}

export function useVerifyDomain() {
  return useMutation({
    mutationFn: (id: string) => api.get(`/api/settings/domains/${id}/verify`),
  });
}

export function useDeleteDomain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/domains/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "domains"] }),
  });
}
