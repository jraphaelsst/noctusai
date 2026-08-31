import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { AvailabilitySlot, BookableSlot } from '@/types/scheduling';

const KEYS = {
  slots: (therapistId?: string) => ['availability', therapistId] as const,
  bookable: (therapistId: string, start: string, end: string) =>
    ['availability', 'bookable', therapistId, start, end] as const,
};

export function useAvailabilitySlots(therapistId?: string) {
  const { user } = useAuthStore();
  return useQuery<AvailabilitySlot[]>({
    queryKey: KEYS.slots(therapistId),
    queryFn: async () => {
      const params = therapistId ? `?therapist_id=${therapistId}` : '';
      const res = await api.get(`/api/availability${params}`);
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBookableSlots(therapistId: string, startDate: string, endDate: string) {
  const { user } = useAuthStore();
  return useQuery<BookableSlot[]>({
    queryKey: KEYS.bookable(therapistId, startDate, endDate),
    queryFn: async () => {
      const res = await api.get(
        `/api/availability/bookable/${therapistId}?start_date=${startDate}&end_date=${endDate}`
      );
      return res.data ?? res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user && !!therapistId && !!startDate && !!endDate,
    staleTime: 30 * 1000,
  });
}

export function useCreateSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Partial<AvailabilitySlot>) => {
      return api.post('/api/availability', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] });
      toast.success('Horario adicionado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao adicionar horario');
    },
  });
}

export function useUpdateSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<AvailabilitySlot> & { id: string }) => {
      return api.patch(`/api/availability/${id}`, data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] });
      toast.success('Horario atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar horario');
    },
  });
}

export function useDeleteSlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/availability/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] });
      toast.success('Horario removido');
    },
    onError: () => {
      toast.error('Erro ao remover horario');
    },
  });
}

export function useBlockDates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { start_date: string; end_date: string; reason?: string }) => {
      return api.post('/api/availability/block', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability'] });
      toast.success('Datas bloqueadas com sucesso');
    },
    onError: () => {
      toast.error('Erro ao bloquear datas');
    },
  });
}
