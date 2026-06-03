/**
 * Reports (Relatórios) hooks for Orbity.
 *
 * Endpoints mirrored from backend/app/routers/reports_router.py:
 *   GET    /api/reports               list
 *   POST   /api/reports               create → 201
 *   GET    /api/reports/{id}          get
 *   PATCH  /api/reports/{id}          update
 *   DELETE /api/reports/{id}          delete
 *   GET    /api/reports/{id}/snapshots   list snapshots
 *   POST   /api/reports/{id}/generate   generate snapshot → 201
 *   GET    /api/reports/public/{token}  PUBLIC — no auth
 *
 * Convention: one file per domain entity, TanStack Query throughout.
 * `api` is imported from `@/lib/api` (the local seam).
 *
 * status_pagina key: "relatorios"
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Domain types (mirrors backend schemas/reports.py)
// ---------------------------------------------------------------------------

export type ReportStatus = "draft" | "published";

export interface Report {
  id: string;
  org_id: string;
  client_id: string | null;
  name: string;
  public_token: string;
  period_start: string;
  period_end: string;
  config: Record<string, unknown>;
  status: ReportStatus;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportSnapshot {
  id: string;
  org_id: string;
  report_id: string;
  generated_at: string;
  payload: Record<string, unknown>;
}

export interface PublicReport {
  report_id: string;
  name: string;
  period_start: string;
  period_end: string;
  status: string;
  expires_at: string | null;
  snapshot_id: string | null;
  generated_at: string | null;
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Inbound types (mirrors ReportCreate / ReportUpdate)
// ---------------------------------------------------------------------------

export interface ReportCreate {
  name: string;
  period_start: string;
  period_end: string;
  client_id?: string;
  config?: Record<string, unknown>;
  status?: ReportStatus;
  expires_at?: string;
}

export interface ReportUpdate {
  id: string;
  name?: string;
  period_start?: string;
  period_end?: string;
  client_id?: string;
  config?: Record<string, unknown>;
  status?: ReportStatus;
  expires_at?: string;
}

export interface ReportFilters {
  client_id?: string;
  status?: ReportStatus;
}

// ---------------------------------------------------------------------------
// Reports — list
// ---------------------------------------------------------------------------

export function useReports(filters?: ReportFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["reports", filters],
    queryFn: async () => {
      const result = await api.get<Report[]>("/api/reports", {
        client_id: filters?.client_id,
        status: filters?.status,
      });
      return result;
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Reports — get single
// ---------------------------------------------------------------------------

export function useReport(id: string | null) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["reports", id],
    queryFn: async () => {
      return api.get<Report>(`/api/reports/${id}`);
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Reports — create
// ---------------------------------------------------------------------------

export function useCreateReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ReportCreate) => {
      return api.post<Report>("/api/reports", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Relatório criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar relatório", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Reports — update
// ---------------------------------------------------------------------------

export function useUpdateReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ReportUpdate) => {
      return api.patch<Report>(`/api/reports/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Relatório atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar relatório", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Reports — delete
// ---------------------------------------------------------------------------

export function useDeleteReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(`/api/reports/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Relatório removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover relatório", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Snapshots — list for a report
// ---------------------------------------------------------------------------

export function useReportSnapshots(reportId: string | null) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["report-snapshots", reportId],
    queryFn: async () => {
      return api.get<ReportSnapshot[]>(`/api/reports/${reportId}/snapshots`);
    },
    enabled: !!user && !!reportId,
    staleTime: 2 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Snapshots — generate
// ---------------------------------------------------------------------------

export function useGenerateSnapshot() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (reportId: string) => {
      return api.post<ReportSnapshot>(`/api/reports/${reportId}/generate`, {});
    },
    onSuccess: (_data, reportId) => {
      queryClient.invalidateQueries({ queryKey: ["report-snapshots", reportId] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Snapshot gerado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao gerar snapshot", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Public report — token-gated, no auth required
// ---------------------------------------------------------------------------

export function usePublicReport(token: string | null) {
  return useQuery({
    queryKey: ["public-report", token],
    queryFn: async () => {
      return api.get<PublicReport>(`/api/reports/public/${token}`);
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
