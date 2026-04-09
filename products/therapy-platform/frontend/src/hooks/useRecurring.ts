import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';
import type { RecurringSchedule, RecurringFilters } from '@/types/scheduling';

const KEYS = {
  all: ['recurring'] as const,
  list: (filters?: RecurringFilters) => ['recurring', 'list', filters] as const,
  detail: (id: string) => ['recurring', id] as const,
};

export function useRecurringSchedules(filters?: RecurringFilters) {
  const { user } = useAuthStore();
  return useQuery<{ data: RecurringSchedule[]; total: number }>({
    queryKey: KEYS.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.status) params.set('status', filters.status);
      if (filters?.page) params.set('page', String(filters.page));
      if (filters?.page_size) params.set('page_size', String(filters.page_size));
      const qs = params.toString();
      return api.get(`/api/recurring${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useRecurringSchedule(id?: string) {
  const { user } = useAuthStore();
  return useQuery<RecurringSchedule>({
    queryKey: KEYS.detail(id!),
    queryFn: async () => {
      const res = await api.get(`/api/recurring/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 60 * 1000,
  });
}

export function useCreateRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Partial<RecurringSchedule>) => {
      return api.post('/api/recurring', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['appointments'] });
      toast.success('Agendamento recorrente criado');
    },
    onError: () => {
      toast.error('Erro ao criar agendamento recorrente');
    },
  });
}

export function useModifyRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<RecurringSchedule> & { id: string }) => {
      return api.patch(`/api/recurring/${id}`, data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['appointments'] });
      toast.success('Agendamento recorrente atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar agendamento recorrente');
    },
  });
}

function useRecurringAction(action: string, successMsg: string, errorMsg: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string; [key: string]: unknown }) => {
      return api.post(`/api/recurring/${id}/${action}`, Object.keys(body).length ? body : undefined);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['appointments'] });
      toast.success(successMsg);
    },
    onError: () => {
      toast.error(errorMsg);
    },
  });
}

export function useApproveRecurring() {
  return useRecurringAction('approve', 'Agendamento aprovado', 'Erro ao aprovar agendamento');
}

export function useDenyRecurring() {
  return useRecurringAction('deny', 'Agendamento negado', 'Erro ao negar agendamento');
}

export function usePauseRecurring() {
  return useRecurringAction('pause', 'Agendamento pausado', 'Erro ao pausar agendamento');
}

export function useResumeRecurring() {
  return useRecurringAction('resume', 'Agendamento retomado', 'Erro ao retomar agendamento');
}

export function useEndRecurring() {
  return useRecurringAction('end', 'Agendamento encerrado', 'Erro ao encerrar agendamento');
}

export function useSkipOccurrence() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, date }: { id: string; date: string }) => {
      return api.post(`/api/recurring/${id}/skip?date=${date}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['appointments'] });
      toast.success('Sessao pulada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao pular sessao');
    },
  });
}
