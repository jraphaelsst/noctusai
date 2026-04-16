import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api-client";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Tarefa {
  id: string;
  titulo: string;
  descricao?: string;
  prioridade: "alta" | "media" | "baixa";
  status: "pendente" | "em_progresso" | "concluida" | "cancelada";
  categoria?: string;
  data_vencimento?: string;
  created_at: string;
}

export interface TarefaForm {
  titulo: string;
  descricao: string;
  prioridade: "alta" | "media" | "baixa";
  categoria: string;
  data_vencimento: string;
  status: "pendente" | "em_progresso" | "concluida" | "cancelada";
}

export interface TarefaStats {
  total: number;
  pendentes: number;
  em_progresso: number;
  concluidas: number;
  canceladas: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useTarefas(
  page: number,
  filters: { status?: string; prioridade?: string; categoria?: string },
) {
  const { user } = useAuthStore();

  const buildParams = () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (filters.status) params.set("status", filters.status);
    if (filters.prioridade) params.set("prioridade", filters.prioridade);
    if (filters.categoria) params.set("categoria", filters.categoria);
    return params.toString();
  };

  return useQuery({
    queryKey: ["tarefas", page, filters.status, filters.prioridade, filters.categoria],
    queryFn: () => api.get<{ data: Tarefa[]; total: number; page: number; page_size: number }>(`/api/tasks?${buildParams()}`),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useTarefaStats() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["tarefas-stats"],
    queryFn: () => api.get<{ data: TarefaStats }>("/api/tasks/stats/resumo"),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateTarefa(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (body: Partial<TarefaForm>) => api.post("/api/tasks", body),
    onSuccess: () => {
      toast.success("Tarefa criada com sucesso");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao criar tarefa", { description: err?.message }),
  });
}

export function useUpdateTarefa(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch(`/api/tasks/${id}`, body),
    onSuccess: () => {
      toast.success("Tarefa atualizada");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao atualizar tarefa", { description: err?.message }),
  });
}

export function useDeleteTarefa(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/tasks/${id}`),
    onSuccess: () => {
      toast.success("Tarefa removida");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao remover tarefa", { description: err?.message }),
  });
}
