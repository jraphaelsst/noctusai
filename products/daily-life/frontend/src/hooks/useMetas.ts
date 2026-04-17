import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore, api } from '@noctusai/seed/infra';
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Meta {
  id: string;
  titulo: string;
  descricao?: string;
  tipo: "meta" | "habito";
  categoria?: string;
  meta_valor?: number;
  valor_atual: number;
  unidade?: string;
  frequencia?: "diario" | "semanal" | "mensal";
  data_limite?: string;
  status: "ativa" | "concluida" | "pausada" | "cancelada";
  created_at: string;
}

export interface MetaForm {
  titulo: string;
  descricao: string;
  tipo: "meta" | "habito";
  categoria: string;
  meta_valor: string;
  unidade: string;
  frequencia: string;
  data_limite: string;
  status: "ativa" | "concluida" | "pausada" | "cancelada";
}

export interface CheckIn {
  id: string;
  meta_id: string;
  data: string;
  valor: number;
  nota?: string;
  created_at: string;
}

export interface CheckInForm {
  data: string;
  valor: string;
  nota: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useMetas(
  page: number,
  filters: { tipo?: string; status?: string },
) {
  const { user } = useAuthStore();

  const buildParams = () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (filters.tipo) params.set("tipo", filters.tipo);
    if (filters.status) params.set("status", filters.status);
    return params.toString();
  };

  return useQuery({
    queryKey: ["metas", page, filters.tipo, filters.status],
    queryFn: () => api.get<{ data: Meta[]; total: number }>(`/api/goals?${buildParams()}`),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCheckins(goalId: string | null) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["checkins", goalId],
    queryFn: () => api.get<{ data: CheckIn[] }>(`/api/goals/${goalId}/checkins?page=1&page_size=10`),
    enabled: !!user && !!goalId,
    staleTime: 30 * 1000,
  });
}

export function useCreateMeta(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/goals", body),
    onSuccess: () => {
      toast.success("Meta criada com sucesso");
      qc.invalidateQueries({ queryKey: ["metas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao criar meta", { description: err?.message }),
  });
}

export function useUpdateMeta(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch(`/api/goals/${id}`, body),
    onSuccess: () => {
      toast.success("Meta atualizada");
      qc.invalidateQueries({ queryKey: ["metas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao atualizar meta", { description: err?.message }),
  });
}

export function useDeleteMeta(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/goals/${id}`),
    onSuccess: () => {
      toast.success("Meta removida");
      qc.invalidateQueries({ queryKey: ["metas"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao remover meta", { description: err?.message }),
  });
}

export function useCheckinMeta(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ goalId, body }: { goalId: string; body: Record<string, unknown> }) =>
      api.post(`/api/goals/${goalId}/checkin`, body),
    onSuccess: (_data, vars) => {
      toast.success("Check-in registrado");
      qc.invalidateQueries({ queryKey: ["metas"] });
      qc.invalidateQueries({ queryKey: ["checkins", vars.goalId] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao registrar check-in", { description: err?.message }),
  });
}
