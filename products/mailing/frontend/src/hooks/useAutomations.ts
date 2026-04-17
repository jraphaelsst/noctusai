import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Automation {
  id: string;
  nome: string;
  descricao?: string;
  trigger_type: string;
  trigger_config: Record<string, any>;
  status: "rascunho" | "ativa" | "pausada";
  created_at: string;
  steps?: AutomationStep[];
}

export interface AutomationStep {
  id: string;
  automation_id: string;
  posicao: number;
  tipo: "send_email" | "wait" | "condition" | "add_tag" | "remove_tag" | "move_to_list" | "webhook";
  config: Record<string, any>;
}

export function useAutomations(status?: string) {
  const { user } = useAuthStore();
  const params = status ? `?status=${status}` : "";
  return useQuery({
    queryKey: ["automations", status],
    queryFn: () => api.get(`/api/automations${params}`),
    enabled: !!user,
  });
}

export function useAutomation(id: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["automation", id],
    queryFn: () => api.get(`/api/automations/${id}`),
    enabled: !!user && !!id,
  });
}

export function useCreateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Automation>) => api.post("/api/automations", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
}

export function useUpdateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<Automation>) =>
      api.patch(`/api/automations/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
}

export function useDeleteAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/automations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
}

export function useActivateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/automations/${id}/activate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
}

export function usePauseAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/automations/${id}/pause`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
}

export function useAddStep() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ automationId, ...data }: { automationId: string; tipo: string; config: Record<string, any> }) =>
      api.post(`/api/automations/${automationId}/steps`, data),
    onSuccess: (_, { automationId }) => qc.invalidateQueries({ queryKey: ["automation", automationId] }),
  });
}

export function useDeleteStep() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ automationId, stepId }: { automationId: string; stepId: string }) =>
      api.delete(`/api/automations/${automationId}/steps/${stepId}`),
    onSuccess: (_, { automationId }) => qc.invalidateQueries({ queryKey: ["automation", automationId] }),
  });
}

export function useEnrollContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ automationId, contactIds }: { automationId: string; contactIds: string[] }) =>
      api.post(`/api/automations/${automationId}/enroll`, { contact_ids: contactIds }),
    onSuccess: (_, { automationId }) => qc.invalidateQueries({ queryKey: ["automation", automationId] }),
  });
}

export function useEnrollments(automationId: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["enrollments", automationId],
    queryFn: () => api.get(`/api/automations/${automationId}/enrollments`),
    enabled: !!user && !!automationId,
  });
}
