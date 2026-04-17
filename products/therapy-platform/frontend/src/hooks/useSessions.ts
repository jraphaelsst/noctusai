import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { SessionStatus } from '@/types/session';

const KEYS = {
  all: ['sessions'] as const,
  status: (id: string) => ['sessions', 'status', id] as const,
  overtime: (id: string) => ['sessions', 'overtime', id] as const,
  token: (id: string) => ['sessions', 'token', id] as const,
};

export function useSessionStatus(appointmentId?: string) {
  const { user } = useAuthStore();
  return useQuery<SessionStatus>({
    queryKey: KEYS.status(appointmentId!),
    queryFn: async () => {
      const res = await api.get(`/api/sessions/${appointmentId}/status`);
      return res.data ?? res;
    },
    enabled: !!user && !!appointmentId,
    staleTime: 2 * 1000,
    refetchInterval: (query) => {
      const status = query.state.data?.video_room_status;
      if (status === 'active' || status === 'paused') return 3000;
      return false;
    },
  });
}

export function useOvertimeInfo(appointmentId?: string, enabled = false) {
  const { user } = useAuthStore();
  return useQuery<{ minutes_remaining: number; overtime_limit: number }>({
    queryKey: KEYS.overtime(appointmentId!),
    queryFn: async () => {
      const res = await api.get(`/api/sessions/${appointmentId}/overtime`);
      return res.data ?? res;
    },
    enabled: !!user && !!appointmentId && enabled,
    staleTime: 10 * 1000,
    refetchInterval: enabled ? 30000 : false,
  });
}

export function useStartSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (appointmentId: string) => {
      return api.post(`/api/sessions/${appointmentId}/start`, {});
    },
    onSuccess: (_data, appointmentId) => {
      qc.invalidateQueries({ queryKey: KEYS.status(appointmentId) });
      qc.invalidateQueries({ queryKey: ['appointments'] });
    },
    onError: () => {
      toast.error('Erro ao iniciar sessao');
    },
  });
}

export function usePauseSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (appointmentId: string) => {
      return api.post(`/api/sessions/${appointmentId}/pause`, {});
    },
    onSuccess: (_data, appointmentId) => {
      qc.invalidateQueries({ queryKey: KEYS.status(appointmentId) });
    },
    onError: () => {
      toast.error('Erro ao pausar sessao');
    },
  });
}

export function useResumeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (appointmentId: string) => {
      return api.post(`/api/sessions/${appointmentId}/resume`, {});
    },
    onSuccess: (_data, appointmentId) => {
      qc.invalidateQueries({ queryKey: KEYS.status(appointmentId) });
    },
    onError: () => {
      toast.error('Erro ao retomar sessao');
    },
  });
}

export function useEndSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ appointmentId, initial_observation }: { appointmentId: string; initial_observation?: string }) => {
      return api.post(`/api/sessions/${appointmentId}/end`, { initial_observation });
    },
    onSuccess: (_data, { appointmentId }) => {
      qc.invalidateQueries({ queryKey: KEYS.status(appointmentId) });
      qc.invalidateQueries({ queryKey: ['appointments'] });
      qc.invalidateQueries({ queryKey: ['journal'] });
    },
    onError: () => {
      toast.error('Erro ao encerrar sessao');
    },
  });
}

export function useReopenSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (appointmentId: string) => {
      return api.post(`/api/sessions/${appointmentId}/reopen`, {});
    },
    onSuccess: (_data, appointmentId) => {
      qc.invalidateQueries({ queryKey: KEYS.status(appointmentId) });
      toast.success('Sessao reaberta');
    },
    onError: () => {
      toast.error('Erro ao reabrir sessao');
    },
  });
}

export function useSessionToken(appointmentId?: string) {
  const { user } = useAuthStore();
  return useQuery<{ token: string; room_name: string }>({
    queryKey: KEYS.token(appointmentId!),
    queryFn: async () => {
      const res = await api.get(`/api/sessions/${appointmentId}/token`);
      return res.data ?? res;
    },
    enabled: !!user && !!appointmentId,
    staleTime: 5 * 60 * 1000,
  });
}
