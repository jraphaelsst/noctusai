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
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
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

// ─── Funil cache edits (used by the lead mutations below) ───────────────────

/** Apply `edit` to the lead `id` wherever it sits in the funil; `null` drops it. */
function editFunilLead(
  funil: FunilStage[] | undefined,
  id: string,
  edit: (lead: Lead) => Lead | null
): FunilStage[] | undefined {
  return funil?.map((fs) => ({
    ...fs,
    leads: fs.leads.flatMap((l) => {
      if (l.id !== id) return [l];
      const next = edit(l);
      return next ? [next] : [];
    }),
  }));
}

/** Put `lead` in its stage's column (removing it from any other column first). */
function placeFunilLead(funil: FunilStage[] | undefined, lead: Lead): FunilStage[] | undefined {
  const without = editFunilLead(funil, lead.id, () => null);
  return without?.map((fs) =>
    fs.stage.id === lead.stage_id ? { ...fs, leads: [...fs.leads, lead] } : fs
  );
}

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
  return useCacheWriteMutation<Stage[], void>({
    mutationFn: () =>
      api.post<Stage[]>("/api/crm/stages/seed-defaults"),
    // The stages list is exactly what the server answers with; the funil (stages with
    // their leads) is a derived view and refreshes in the background.
    targets: [{ queryKey: crmKeys.stages(), commit: (_old: Stage[] | undefined, stages) => stages }],
    invalidate: [crmKeys.funil()],
    onSuccess: () => {
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
  // The server picks the stage when none is sent (the org's first stage), so the
  // card is placed from the server's answer, not drawn optimistically.
  return useCacheWriteMutation<Lead, LeadCreate>({
    mutationFn: (payload) => api.post<Lead>("/api/crm/leads", payload),
    targets: [
      {
        queryKey: crmKeys.funil(),
        commit: (old: FunilStage[] | undefined, lead) => placeFunilLead(old, lead),
      },
    ],
    invalidate: [["crm", "leads"], ["orbity-lead-options"]],
    onSuccess: () => {
      toast.success("Lead criado com sucesso");
    },
    onError: () => {
      toast.error("Falha ao criar lead");
    },
  });
}

// ─── Update lead ─────────────────────────────────────────────────────────────

export function useUpdateLead() {
  return useCacheWriteMutation<Lead, { id: string; data: LeadUpdate }>({
    mutationFn: ({ id, data }) => api.patch<Lead>(`/api/crm/leads/${id}`, data),
    targets: ({ id }) => [
      {
        queryKey: crmKeys.funil(),
        commit: (old: FunilStage[] | undefined, lead) => placeFunilLead(old, lead),
      },
      {
        queryKey: crmKeys.lead(id),
        commit: (_old: Lead | undefined, lead) => lead,
      },
    ],
    invalidate: [["crm", "leads"], ["orbity-lead-options"]],
    onSuccess: () => {
      toast.success("Lead atualizado");
    },
    onError: () => {
      toast.error("Falha ao atualizar lead");
    },
  });
}

// ─── Delete lead ─────────────────────────────────────────────────────────────

export function useDeleteLead() {
  return useCacheWriteMutation<{ ok: boolean; id: string }, string>({
    mutationFn: (id) => api.delete<{ ok: boolean; id: string }>(`/api/crm/leads/${id}`),
    targets: [
      {
        queryKey: crmKeys.funil(),
        optimistic: (old: FunilStage[] | undefined, id) => editFunilLead(old, id, () => null),
      },
    ],
    invalidate: [["crm", "leads"], ["orbity-lead-options"]],
    onSuccess: () => {
      toast.success("Lead removido");
    },
    onError: () => {
      toast.error("Falha ao remover lead");
    },
  });
}

// ─── Move stage (kanban drag) ────────────────────────────────────────────────

export function useMoveLeadStage() {
  // Optimistic — a kanban drag must land instantly; without this the card
  // snaps back to its old column for a full round-trip before the funil
  // refetch lands. A failure rolls the funil back to its pre-drag snapshot.
  return useCacheWriteMutation<Lead, { id: string; stage_id: string }>({
    mutationFn: ({ id, stage_id }) => api.patch<Lead>(`/api/crm/leads/${id}/stage`, { stage_id }),
    targets: ({ id }) => [
      {
        queryKey: crmKeys.funil(),
        optimistic: (old: FunilStage[] | undefined, { stage_id }) => {
          const lead = old?.flatMap((fs) => fs.leads).find((l) => l.id === id);
          return lead ? placeFunilLead(old, { ...lead, stage_id }) : old;
        },
        commit: (old: FunilStage[] | undefined, lead) => placeFunilLead(old, lead),
      },
      {
        queryKey: crmKeys.lead(id),
        commit: (_old: Lead | undefined, lead) => lead,
      },
    ],
    onSuccess: () => {
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
  // The note shows the instant it is saved and is swapped for the server's row
  // when the POST answers — never a list that says "Nenhuma atividade" under a
  // toast that says "Atividade registrada".
  return useCacheWriteMutation<Activity, { leadId: string; payload: ActivityCreate }>({
    mutationFn: ({ leadId, payload }) =>
      api.post<Activity>(`/api/crm/leads/${leadId}/activities`, payload),
    targets: ({ leadId }) => [
      {
        queryKey: crmKeys.activities(leadId),
        // The API lists activities newest first (created_at desc): the new note
        // goes on top and stays there when the server row and the refetch land.
        optimistic: (old: Activity[] | undefined, { payload }, { tempId }) =>
          listOps.prepend(old, {
            id: tempId,
            org_id: "",
            lead_id: leadId,
            type: payload.type,
            note: payload.note ?? null,
            created_by: null,
            created_at: new Date().toISOString(),
          }),
        commit: (old: Activity[] | undefined, saved, _vars, { tempId }) =>
          listOps.replace(old, tempId, saved, "prepend"),
      },
    ],
    onSuccess: () => {
      toast.success("Atividade registrada");
    },
    onError: () => {
      toast.error("Falha ao registrar atividade");
    },
  });
}
