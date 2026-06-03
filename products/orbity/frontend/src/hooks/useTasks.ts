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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: TaskCreateData) => {
      const result = await api.post('/api/tasks', data);
      return result as Task;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-tasks'] });
      toast.success('Tarefa criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar tarefa', { description: error.message });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string } & TaskUpdateData) => {
      const result = await api.patch(`/api/tasks/${id}`, data);
      return result as Task;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['orbity-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['orbity-task', data.id] });
      toast.success('Tarefa atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar tarefa', { description: error.message });
    },
  });
}

export function useUpdateTaskStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: TaskStatus }) => {
      const result = await api.patch(`/api/tasks/${id}/status`, { status });
      return result as Task;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['orbity-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['orbity-task', data.id] });
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar status', { description: error.message });
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/tasks/${id}`);
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-tasks'] });
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
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateRoutine() {
  const queryClient = useQueryClient();

  return useMutation({
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string } & RoutineUpdateData) => {
      const result = await api.patch(`/api/routines/${id}`, data);
      return result as Routine;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-routines'] });
      toast.success('Rotina atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar rotina', { description: error.message });
    },
  });
}

export function useDeleteRoutine() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/routines/${id}`);
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-routines'] });
      toast.success('Rotina excluída!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir rotina', { description: error.message });
    },
  });
}

export function useRunDueRoutines() {
  const queryClient = useQueryClient();

  return useMutation({
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
