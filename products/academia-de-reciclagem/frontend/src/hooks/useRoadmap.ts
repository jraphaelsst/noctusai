/**
 * Roadmap + tasks data hooks — contract §A.4, §A.5, §B.4.
 */
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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
  // Phases are a fixed ordered list: the edit is drawn on the click (a failure rolls it
  // back) and replaced by the server's row; session-prep is derived and refreshes.
  return useCacheWriteMutation<Phase, { codigo: string; changes: PhaseUpdateInput }>({
    mutationFn: ({ codigo, changes }) => api.patch<Phase>(`/api/roadmap/${codigo}`, changes),
    targets: ({ codigo, changes }) => [
      {
        queryKey: roadmapKeys.phases,
        optimistic: (old: Envelope<Phase> | undefined) => pageOps.patch(old, codigo, changes, "codigo"),
        commit: (old: Envelope<Phase> | undefined, saved) => pageOps.replace(old, codigo, saved, "codigo"),
      },
    ],
    invalidate: [[...roadmapKeys.sessionPrep]],
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
  // Tasks are listed by codigo and the server allocates codes sequentially, so the new one is the
  // last row of every unpaginated list whose fase/estado filter it satisfies. Session-prep is a
  // server-computed digest: it settles instead.
  return useCacheWriteMutation<Task, TaskCreateInput>({
    mutationFn: (data) => api.post<Task>("/api/tasks", data),
    targets: [
      {
        queryKey: roadmapKeys.tasksAll,
        match: "prefix",
        commit: (old: Envelope<Task> | undefined, saved, _vars, _ctx, queryKey) => {
          const f = (queryKey?.[2] ?? {}) as TaskListParams;
          return (!f.fase || f.fase === saved.fase) && (!f.estado || f.estado === saved.estado)
            ? pageOps.add(old, saved, "append", "codigo")
            : old;
        },
      },
    ],
    invalidate: [roadmapKeys.sessionPrep],
  });
}

export interface TaskUpdateInput {
  estado?: FaseEstado;
  detalhe?: string;
  bloqueada_por?: string;
}

export function useUpdateTask() {
  // The edit is drawn in every cached task list on the click and replaced by the
  // server's row; an estado change that moves the task out of a filtered list, and
  // session-prep, converge on the settle refetch.
  return useCacheWriteMutation<Task, { codigo: string; changes: TaskUpdateInput }>({
    mutationFn: ({ codigo, changes }) => api.patch<Task>(`/api/tasks/${codigo}`, changes),
    targets: ({ codigo, changes }) => [
      {
        queryKey: roadmapKeys.tasksAll,
        match: "prefix",
        optimistic: (old: Envelope<Task> | undefined) => pageOps.patch(old, codigo, changes, "codigo"),
        commit: (old: Envelope<Task> | undefined, saved) => pageOps.replace(old, codigo, saved, "codigo"),
      },
    ],
    invalidate: [[...roadmapKeys.sessionPrep]],
  });
}

export function useSessionPrep() {
  return useQuery({
    queryKey: roadmapKeys.sessionPrep,
    queryFn: () => api.get<SessionPrep>("/api/session-prep"),
  });
}
