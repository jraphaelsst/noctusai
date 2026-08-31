/**
 * useScheduling — react-query hooks for `/api/scheduling/*`.
 *
 * Pilot consumer of `noctusai_lib.domain.scheduling`. See
 * `products/therapy-platform/projects/therapy-scheduling-pilot/PROJECT.md`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

export interface CandidateSlot {
  start_at: string;
  end_at: string;
  duration_minutes: number;
  score: number;
}

export interface BookedAppointment {
  id?: string;
  therapist_id: string;
  patient_id: string;
  clinic_id: string | null;
  scheduled_start: string;
  scheduled_end: string;
  status: string;
  google_event_id: string | null;
}

export interface CandidatesParams {
  therapist_id: string;
  window_start: string;
  window_end: string;
  clinic_id?: string;
  duration_minutes?: number;
}

const KEYS = {
  all: ['scheduling'] as const,
  candidates: (p: CandidatesParams) => ['scheduling', 'candidates', p] as const,
  gcalAuthorize: (therapist_id: string) => ['scheduling', 'gcal-authorize', therapist_id] as const,
};

export function useCandidateSlots(params: CandidatesParams | null) {
  const { user } = useAuthStore();
  return useQuery<{ data: CandidateSlot[] }>({
    queryKey: params ? KEYS.candidates(params) : ['scheduling', 'candidates', 'idle'],
    queryFn: async () => {
      if (!params) throw new Error('useCandidateSlots called with null params');
      const qs = new URLSearchParams({
        therapist_id: params.therapist_id,
        window_start: params.window_start,
        window_end: params.window_end,
        ...(params.clinic_id ? { clinic_id: params.clinic_id } : {}),
        ...(params.duration_minutes ? { duration_minutes: String(params.duration_minutes) } : {}),
      });
      return await api.get(`/api/scheduling/candidates?${qs.toString()}`);
    },
    enabled: !!user && !!params,
    staleTime: 30 * 1000,
    // Window dates + patient/therapist filters change this queryKey; keep the
    // previous window's slots on screen during the transition instead of
    // flashing a skeleton. Not authorisation-scoped across the key change —
    // same therapist_id, only the date window narrows/widens.
    placeholderData: (prev) => prev,
  });
}

export function useBookAppointment() {
  const qc = useQueryClient();
  return useMutation<BookedAppointment, unknown, {
    therapist_id: string;
    patient_id: string;
    clinic_id?: string;
    slot_start: string;
    slot_end: string;
    summary?: string;
  }>({
    mutationFn: async (body) => {
      const res = await api.post('/api/scheduling/appointments', body);
      return res.data ?? res;
    },
    onSuccess: () => {
      toast.success('Sessão agendada');
      qc.invalidateQueries({ queryKey: KEYS.all });
    },
    onError: () => {
      toast.error('Não foi possível agendar a sessão');
    },
  });
}

export function useReschedule() {
  const qc = useQueryClient();
  return useMutation<BookedAppointment, unknown, {
    appointment_id: string;
    slot_start: string;
    slot_end: string;
  }>({
    mutationFn: async ({ appointment_id, slot_start, slot_end }) => {
      const res = await api.patch(`/api/scheduling/appointments/${appointment_id}`, {
        slot_start,
        slot_end,
      });
      return res.data ?? res;
    },
    onSuccess: () => {
      toast.success('Sessão reagendada');
      qc.invalidateQueries({ queryKey: KEYS.all });
    },
    onError: () => {
      toast.error('Não foi possível reagendar');
    },
  });
}

export function useGcalAuthorizeUrl(therapistId: string | undefined) {
  const { user } = useAuthStore();
  return useQuery<{ data: { authorize_url: string; needs_authorization: boolean } }>({
    queryKey: therapistId ? KEYS.gcalAuthorize(therapistId) : ['scheduling', 'gcal-authorize', 'idle'],
    queryFn: async () => {
      return await api.get(`/api/scheduling/gcal/authorize?therapist_id=${therapistId}`);
    },
    enabled: !!user && !!therapistId,
    staleTime: 60 * 1000,
  });
}
