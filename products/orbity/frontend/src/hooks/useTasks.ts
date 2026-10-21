/**
 * Tasks + Routines hooks for Orbity.
 *
 * Mirrors the ERP TanStack Query hook shape (useQuery/useMutation + toast).
 * Hooks are the ONLY place useQuery/useMutation appears — never in page
 * components directly (per engineer-seed protocol).
 *
 * Backend contract: products/orbity/backend/app/schemas/tasks.py
 *   TaskStatus  : "todo" | "doing" | "done" | "canceled"
 *   TaskPriority: "low" | "med" | "high"
 *   RoutineCadence: "daily" | "weekly" | "monthly"
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listOps, pageOps, useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types — mirror backend schemas/tasks.py
// ---------------------------------------------------------------------------

export type TaskStatus = 'todo' | 'doing' | 'done' | 'canceled';
export type TaskPriority = 'low' | 'med' | 'high';
export type RoutineCadence = 'daily' | 'weekly' | 'monthly';

export interface Task {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  assignee_user_id: string | null;
  client_id: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
}

export interface Routine {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  cadence: RoutineCadence;
  next_run: string;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee_user_id?: string;
  client_id?: string;
  page?: number;
  page_size?: number;
}

export interface TaskCreateData {
  title: string;
  description?: string;
  assignee_user_id?: string;
  client_id?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string;
}

export interface TaskUpdateData extends Partial<TaskCreateData> {
  completed_at?: string;
}

export interface RoutineCreateData {
  title: string;
  description?: string;
  cadence: RoutineCadence;
  next_run: string;
  active?: boolean;
}

export interface RoutineUpdateData {
  title?: string;
  description?: string;
  cadence?: RoutineCadence;
  next_run?: string;
  active?: boolean;
}

// ---------------------------------------------------------------------------
// Task hooks
// ---------------------------------------------------------------------------

export function useTasks(filters?: TaskFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['orbity-tasks', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 200,
      };
      if (filters?.status) params['status'] = filters.status;
      if (filters?.priority) params['priority'] = filters.priority;
      if (filters?.assignee_user_id) params['assignee_user_id'] = filters.assignee_user_id;
      if (filters?.client_id) params['client_id'] = filters.client_id;

      const result = await api.get('/api/tasks', params);
      // Backend returns { items, total, page, page_size }
      return result as TaskListResponse;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useTask(id?: string) {
  return useQuery({
    queryKey: ['orbity-task', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/tasks/${id}`);
      return result as Task;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateTask() {
  // Tasks are listed newest first (created_at desc): the new task goes on top of the
  // unfiltered list; filtered lists converge on the settle.
  return useCacheWriteMutation<Task, TaskCreateData>({
    mutationFn: async (data) => {
      const result = await api.post('/api/tasks', data);
      return result as Task;
    },
    targets: [
      {
        queryKey: ['orbity-tasks', undefined],
        commit: (old: TaskListResponse | undefined, saved) => pageOps.prependNewest(old, saved),
      },
      { queryKey: ['orbity-tasks'], match: 'prefix' },
    ],
    onSuccess: () => {
      toast.success('Tarefa criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar tarefa', { description: error.message });
    },
  });
}

export function useUpdateTask() {
  return useCacheWriteMutation<Task, { id: string } & TaskUpdateData>({
    mutationFn: async ({ id, ...data }) => {
      const result = await api.patch(`/api/tasks/${id}`, data);
      return result as Task;
    },
    targets: ({ id }) => [
      {
        queryKey: ['orbity-tasks'],
        match: 'prefix',
        commit: (old: TaskListResponse | undefined, saved) => pageOps.replace(old, id, saved),
      },
      { queryKey: ['orbity-task', id], commit: (_old: Task | null | undefined, saved) => saved },
    ],
    onSuccess: () => {
      toast.success('Tarefa atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar tarefa', { description: error.message });
    },
  });
}

export function useUpdateTaskStatus() {
  // Optimistic — a status-select change lands instantly on the card instead of
  // waiting a round-trip; a failure rolls every touched '['orbity-tasks', ...]'
  // filter variant plus the single-task cache back to their snapshots.
  return useCacheWriteMutation<Task, { id: string; status: TaskStatus }>({
    mutationFn: async ({ id, status }) => {
      const result = await api.patch(`/api/tasks/${id}/status`, { status });
      return result as Task;
    },
    targets: ({ id, status }) => [
      {
        queryKey: ['orbity-tasks'],
        match: 'prefix',
        optimistic: (old: TaskListResponse | undefined) => pageOps.patch(old, id, { status }),
        commit: (old: TaskListResponse | undefined, saved) => pageOps.replace(old, id, saved),
      },
      {
        queryKey: ['orbity-task', id],
        optimistic: (old: Task | null | undefined) => (old ? listOps.merge(old, { status }) : undefined),
        commit: (_old: Task | null | undefined, saved) => saved,
      },
    ],
    onError: (error: Error) => {
      toast.error('Erro ao atualizar status', { description: error.message });
    },
  });
}

export function useDeleteTask() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (id) => {
      await api.delete(`/api/tasks/${id}`);
      return id;
    },
    targets: (id) => [
      {
        queryKey: ['orbity-tasks'],
        match: 'prefix',
        optimistic: (old: TaskListResponse | undefined) => pageOps.remove(old, id),
      },
      { queryKey: ['orbity-task', id] },
    ],
    onSuccess: () => {
      toast.success('Tarefa excluída!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir tarefa', { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Routine hooks
// ---------------------------------------------------------------------------

export function useRoutines(activeOnly?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['orbity-routines', { activeOnly }],
    queryFn: async () => {
      const result = await api.get('/api/routines', {
        active_only: activeOnly ?? false,
      });
      return result as Routine[];
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateRoutine() {
  const queryClient = useQueryClient();

  return useMutation({ // noc-allow: invalidate-only — routines are ordered by next_run, which the server computes from the cadence; the new routine's position is not knowable client-side
    mutationFn: async (data: RoutineCreateData) => {
      const result = await api.post('/api/routines', data);
      return result as Routine;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-routines'] });
      toast.success('Rotina criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar rotina', { description: error.message });
    },
  });
}

export function useUpdateRoutine() {
  return useCacheWriteMutation<Routine, { id: string } & RoutineUpdateData>({
    mutationFn: async ({ id, ...data }) => {
      const result = await api.patch(`/api/routines/${id}`, data);
      return result as Routine;
    },
    // In place: a cadence change moves next_run (and so the sort position) — the
    // settle refetch re-sorts, the row is already correct meanwhile.
    targets: ({ id }) => [
      {
        queryKey: ['orbity-routines'],
        match: 'prefix',
        commit: (old: Routine[] | undefined, saved) => listOps.patch(old, id, saved),
      },
    ],
    onSuccess: () => {
      toast.success('Rotina atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar rotina', { description: error.message });
    },
  });
}

export function useDeleteRoutine() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (id) => {
      await api.delete(`/api/routines/${id}`);
      return id;
    },
    targets: [
      {
        queryKey: ['orbity-routines'],
        match: 'prefix',
        optimistic: (old: Routine[] | undefined, id) => listOps.remove(old, id),
      },
    ],
    onSuccess: () => {
      toast.success('Rotina excluída!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir rotina', { description: error.message });
    },
  });
}

export function useRunDueRoutines() {
  const queryClient = useQueryClient();

  return useMutation({ // noc-allow: invalidate-only — run-due spawns tasks and advances each routine's next_run server-side; which routines moved (and where they re-sort) is not knowable client-side
    mutationFn: async () => {
      const result = await api.post('/api/routines/run-due', {});
      return result as { spawned: number; tasks: Task[] };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['orbity-routines'] });
      queryClient.invalidateQueries({ queryKey: ['orbity-tasks'] });
      toast.success(`${data.spawned} tarefa(s) gerada(s) pelas rotinas!`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao executar rotinas', { description: error.message });
    },
  });
}
