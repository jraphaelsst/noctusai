/**
 * useCrm — TanStack Query hooks for /api/crm/* (Orbity CRM).
 *
 * Backend contract (crm_router.py):
 *   GET    /api/crm/funil                → FunilStage[] (kanban grouped)
 *   GET    /api/crm/stages               → Stage[]
 *   POST   /api/crm/stages/seed-defaults → Stage[] (idempotent; self-serve
 *                                          "criar etapas padrão" action)
 *   GET    /api/crm/leads                → LeadListResponse
 *   POST   /api/crm/leads                → LeadOut 201
 *   GET    /api/crm/leads/{id}           → LeadOut
 *   PATCH  /api/crm/leads/{id}           → LeadOut
 *   DELETE /api/crm/leads/{id}           → {ok, id}
 *   PATCH  /api/crm/leads/{id}/stage     → LeadOut (move kanban card)
 *   GET    /api/crm/leads/{id}/activities → ActivityOut[]
 *   POST   /api/crm/leads/{id}/activities → ActivityOut 201
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";

// ─── Types (mirror backend schemas/crm.py) ──────────────────────────────────

export type Temperature = "cold" | "warm" | "hot";

export interface Lead {
  id: string;
  org_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  source: string | null;
  stage_id: string | null;
  temperature: Temperature | null;
  qualification_score: number | null;
  qualification_source: string | null;
  value: number | null;
  owner_id: string | null;
  next_contact: string | null;
  client_id: string | null;
  custom_fields: Record<string, unknown>;
  tags: string[];
  won_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Stage {
  id: string;
  org_id: string;
  name: string;
  position: number;
  color: string | null;
  created_at: string;
}

export interface FunilStage {
  stage: Stage;
  leads: Lead[];
}

export interface LeadListResponse {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
}

export interface Activity {
  id: string;
  org_id: string;
  lead_id: string;
  type: string;
  note: string | null;
  created_by: string | null;
  created_at: string;
}

export interface LeadCreate {
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  source?: string;
  stage_id?: string;
  value?: number;
  owner_id?: string;
  next_contact?: string;
  client_id?: string;
  custom_fields?: Record<string, unknown>;
  tags?: string[];
}

export interface LeadUpdate extends Partial<LeadCreate> {
  qualification_source?: string;
}

export interface ActivityCreate {
  type: string;
  note?: string;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

export const crmKeys = {
  all: ["crm"] as const,
  funil: () => ["crm", "funil"] as const,
  stages: () => ["crm", "stages"] as const,
  leads: (params?: Record<string, unknown>) =>
    ["crm", "leads", params] as const,
  lead: (id: string) => ["crm", "lead", id] as const,
  activities: (leadId: string) => ["crm", "activities", leadId] as const,
};

// ─── Funil (kanban) ──────────────────────────────────────────────────────────

export function useFunil() {
  return useQuery({
    queryKey: crmKeys.funil(),
    queryFn: async () => {
      const result = await api.get<FunilStage[]>("/api/crm/funil");
      return result;
    },
    staleTime: 60 * 1000,
  });
}

// ─── Stages ──────────────────────────────────────────────────────────────────

export function useStages() {
  return useQuery({
    queryKey: crmKeys.stages(),
    queryFn: async () => {
      const result = await api.get<Stage[]>("/api/crm/stages");
      return result;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// ─── Seed default stages (self-serve empty-state action) ───────────────────

export function useSeedDefaultStages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<Stage[]>("/api/crm/stages/seed-defaults"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.funil() });
      qc.invalidateQueries({ queryKey: crmKeys.stages() });
      toast.success("Etapas padrão criadas");
    },
    onError: () => {
      toast.error("Falha ao criar etapas padrão");
    },
  });
}

// ─── Leads list ──────────────────────────────────────────────────────────────

export function useLeads(
  params: {
    stage_id?: string;
    owner_id?: string;
    source?: string;
    temperature?: Temperature;
    page?: number;
    page_size?: number;
  } = {}
) {
  return useQuery({
    queryKey: crmKeys.leads(params as Record<string, unknown>),
    queryFn: async () => {
      const result = await api.get<LeadListResponse>("/api/crm/leads", params);
      return result;
    },
    staleTime: 60 * 1000,
  });
}

// ─── Lead detail ─────────────────────────────────────────────────────────────

export function useLead(id?: string) {
  return useQuery({
    queryKey: crmKeys.lead(id ?? ""),
    queryFn: async () => {
      const result = await api.get<Lead>(`/api/crm/leads/${id}`);
      return result;
    },
    enabled: !!id,
    staleTime: 2 * 60 * 1000,
  });
}

// ─── Create lead ─────────────────────────────────────────────────────────────

export function useCreateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadCreate) =>
      api.post<Lead>("/api/crm/leads", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.funil() });
      qc.invalidateQueries({ queryKey: ["crm", "leads"] });
      toast.success("Lead criado com sucesso");
    },
    onError: () => {
      toast.error("Falha ao criar lead");
    },
  });
}

// ─── Update lead ─────────────────────────────────────────────────────────────

export function useUpdateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: LeadUpdate }) =>
      api.patch<Lead>(`/api/crm/leads/${id}`, data),
    onSuccess: (_result, variables) => {
      qc.invalidateQueries({ queryKey: crmKeys.funil() });
      qc.invalidateQueries({ queryKey: crmKeys.lead(variables.id) });
      toast.success("Lead atualizado");
    },
    onError: () => {
      toast.error("Falha ao atualizar lead");
    },
  });
}

// ─── Delete lead ─────────────────────────────────────────────────────────────

export function useDeleteLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.delete<{ ok: boolean; id: string }>(`/api/crm/leads/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.funil() });
      qc.invalidateQueries({ queryKey: ["crm", "leads"] });
      toast.success("Lead removido");
    },
    onError: () => {
      toast.error("Falha ao remover lead");
    },
  });
}

// ─── Move stage (kanban drag) ────────────────────────────────────────────────

export function useMoveLeadStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stage_id }: { id: string; stage_id: string }) =>
      api.patch<Lead>(`/api/crm/leads/${id}/stage`, { stage_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.funil() });
      toast.success("Lead movido");
    },
    onError: () => {
      toast.error("Falha ao mover lead");
    },
  });
}

// ─── Activities ──────────────────────────────────────────────────────────────

export function useLeadActivities(leadId?: string) {
  return useQuery({
    queryKey: crmKeys.activities(leadId ?? ""),
    queryFn: async () => {
      const result = await api.get<Activity[]>(
        `/api/crm/leads/${leadId}/activities`
      );
      return result;
    },
    enabled: !!leadId,
    staleTime: 60 * 1000,
  });
}

export function useAddActivity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      payload,
    }: {
      leadId: string;
      payload: ActivityCreate;
    }) =>
      api.post<Activity>(
        `/api/crm/leads/${leadId}/activities`,
        payload
      ),
    onSuccess: (_result, variables) => {
      qc.invalidateQueries({
        queryKey: crmKeys.activities(variables.leadId),
      });
      toast.success("Atividade registrada");
    },
    onError: () => {
      toast.error("Falha ao registrar atividade");
    },
  });
}
