import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { Appointment, AppointmentFilters } from '@/types/scheduling';

const KEYS = {
  all: ['appointments'] as const,
  list: (filters?: AppointmentFilters) => ['appointments', 'list', filters] as const,
  detail: (id: string) => ['appointments', id] as const,
};

export function useAppointments(filters?: AppointmentFilters) {
  const { user } = useAuthStore();
  return useQuery<{ data: Appointment[]; total: number }>({
    queryKey: KEYS.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.status) params.set('status', filters.status);
      if (filters?.date_start) params.set('date_start', filters.date_start);
      if (filters?.date_end) params.set('date_end', filters.date_end);
      if (filters?.page) params.set('page', String(filters.page));
      if (filters?.page_size) params.set('page_size', String(filters.page_size));
      const qs = params.toString();
      const res = await api.get(`/api/appointments${qs ? `?${qs}` : ''}`);
      return res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useAppointment(id?: string) {
  const { user } = useAuthStore();
  return useQuery<Appointment>({
    queryKey: KEYS.detail(id!),
    queryFn: async () => {
      const res = await api.get(`/api/appointments/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 10 * 1000,
  });
}

export function useCreateAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      therapist_id: string;
      scheduled_start: string;
      scheduled_end: string;
      clinic_id?: string;
      recurring?: {
        frequency: string;
        end_condition: string;
        end_after_n?: number;
        end_on_date?: string;
      };
    }) => {
      return api.post('/api/appointments', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['availability'] });
      qc.invalidateQueries({ queryKey: ['recurring'] });
      toast.success('Sessao agendada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao agendar sessao');
    },
  });
}

export function useCancelAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason?: string }) => {
      return api.post(`/api/appointments/${id}/cancel`, { reason });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Sessao cancelada');
    },
    onError: () => {
      toast.error('Erro ao cancelar sessao');
    },
  });
}
