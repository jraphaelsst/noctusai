import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore, api } from '@noctusai/seed/infra';
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Evento {
  id: string;
  titulo: string;
  descricao?: string;
  categoria?: string;
  data_inicio: string;
  data_fim?: string;
  dia_inteiro: boolean;
  local?: string;
  lembrete_minutos?: number;
  cor?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PaginatedEventoResponse {
  data: Evento[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export interface EventoForm {
  titulo: string;
  descricao: string;
  data_inicio: string;
  data_fim: string;
  dia_inteiro: boolean;
  cor: string;
  local: string;
  lembrete_minutos: string;
  categoria: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useAgenda(inicio: string, fim: string, page: number, pageSize: number) {
  const { user } = useAuthStore();

  return useQuery<PaginatedEventoResponse>({
    queryKey: ["agenda", inicio, fim, page],
    queryFn: () => api.get(`/api/schedule?data_inicio=${inicio}&data_fim=${fim}&page=${page}&page_size=${pageSize}`),
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateEvento(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/schedule", body),
    onSuccess: () => {
      toast.success("Evento criado com sucesso");
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
      // `useDashboardTodayEvents` (useDashboard.ts) hits the exact same
      // `/api/schedule` endpoint (today's window) under a DIFFERENT query
      // key ("dashboard-today-events") — a fix-on-contact found while
      // auditing this file for wave-2: the dashboard's "today" widget
      // never refreshed after an agenda CRUD because nothing invalidated
      // its key.
      queryClient.invalidateQueries({ queryKey: ["dashboard-today-events"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao criar evento", { description: err?.message }),
  });
}

export function useUpdateEvento(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/api/schedule/${id}`, body),
    onSuccess: () => {
      toast.success("Evento atualizado");
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
      // See useCreateEvento's comment for why "dashboard-today-events" is here.
      queryClient.invalidateQueries({ queryKey: ["dashboard-today-events"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao atualizar evento", { description: err?.message }),
  });
}

export function useDeleteEvento(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/schedule/${id}`),
    onSuccess: () => {
      toast.success("Evento removido");
      queryClient.invalidateQueries({ queryKey: ["agenda"] });
      // See useCreateEvento's comment for why "dashboard-today-events" is here.
      queryClient.invalidateQueries({ queryKey: ["dashboard-today-events"] });
      onSuccess?.();
    },
    onError: (err: any) => toast.error("Erro ao remover evento", { description: err?.message }),
  });
}
