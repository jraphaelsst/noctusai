/**
 * Roadmap + tasks data hooks — contract §A.4, §A.5, §B.4.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Envelope } from "@/lib/types";
import type { OpenQuestion } from "@/hooks/usePerguntas";

export type FaseEstado = "pendente" | "em-andamento" | "concluida" | "cancelada";

export const FASE_ESTADOS: FaseEstado[] = [
  "pendente",
  "em-andamento",
  "concluida",
  "cancelada",
];

export interface Phase {
  codigo: string;
  titulo: string;
  objetivo: string;
  concluida_quando: string;
  estado: FaseEstado;
  ordem: number;
}

export interface Task {
  codigo: string;
  titulo: string;
  fase: string;
  detalhe: string | null;
  estado: FaseEstado;
  bloqueada_por: string | null;
}

export interface SessionPrep {
  fase_atual: Phase | null;
  proximas: Task[];
  bloqueadas: Task[];
  perguntas_abertas: number;
  perguntas_bloqueantes: OpenQuestion[];
}

const roadmapKeys = {
  phases: ["roadmap", "phases"] as const,
  tasks: (params: TaskListParams) => ["roadmap", "tasks", params] as const,
  tasksAll: ["roadmap", "tasks"] as const,
  sessionPrep: ["roadmap", "session-prep"] as const,
};

export function usePhases() {
  return useQuery({
    queryKey: roadmapKeys.phases,
    queryFn: () => api.get<Envelope<Phase>>("/api/roadmap"),
  });
}

export interface PhaseUpdateInput {
  estado?: FaseEstado;
  titulo?: string;
  objetivo?: string;
  concluida_quando?: string;
}

export function useUpdatePhase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ codigo, changes }: { codigo: string; changes: PhaseUpdateInput }) =>
      api.patch<Phase>(`/api/roadmap/${codigo}`, changes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roadmapKeys.phases });
      qc.invalidateQueries({ queryKey: roadmapKeys.sessionPrep });
    },
  });
}

export interface TaskListParams {
  fase?: string;
  estado?: string;
}

export function useTasks(params: TaskListParams = {}) {
  return useQuery({
    queryKey: roadmapKeys.tasks(params),
    queryFn: () => api.get<Envelope<Task>>("/api/tasks", params as Record<string, unknown>),
    placeholderData: keepPreviousData,
  });
}

export interface TaskCreateInput {
  titulo: string;
  fase: string;
  detalhe?: string;
  bloqueada_por?: string;
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TaskCreateInput) => api.post<Task>("/api/tasks", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roadmapKeys.tasksAll });
      qc.invalidateQueries({ queryKey: roadmapKeys.sessionPrep });
    },
  });
}

export interface TaskUpdateInput {
  estado?: FaseEstado;
  detalhe?: string;
  bloqueada_por?: string;
}

export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ codigo, changes }: { codigo: string; changes: TaskUpdateInput }) =>
      api.patch<Task>(`/api/tasks/${codigo}`, changes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roadmapKeys.tasksAll });
      qc.invalidateQueries({ queryKey: roadmapKeys.sessionPrep });
    },
  });
}

export function useSessionPrep() {
  return useQuery({
    queryKey: roadmapKeys.sessionPrep,
    queryFn: () => api.get<SessionPrep>("/api/session-prep"),
  });
}
