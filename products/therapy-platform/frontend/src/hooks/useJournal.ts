import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type {
  SessionRecord,
  SessionSummaryVersion,
  AudioSegment,
  SessionObservation,
  PatientSessionNote,
} from '@/types/session';

const KEYS = {
  all: ['journal'] as const,
  sessions: (page: number, pageSize: number) => ['journal', 'sessions', page, pageSize] as const,
  detail: (id: string) => ['journal', 'detail', id] as const,
  versions: (id: string) => ['journal', 'versions', id] as const,
  audio: (id: string) => ['journal', 'audio', id] as const,
  observations: (id: string) => ['observations', id] as const,
  patientNotes: (id: string) => ['patient-notes', id] as const,
};

export function useSessionJournal(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: SessionRecord[]; total: number }>({
    queryKey: KEYS.sessions(page, pageSize),
    queryFn: async () => {
      const res = await api.get(`/api/journal/sessions?page=${page}&page_size=${pageSize}`);
      return res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useSessionDetail(sessionRecordId?: string) {
  const { user } = useAuthStore();
  return useQuery<SessionRecord & { latest_clinical?: SessionSummaryVersion; latest_base?: SessionSummaryVersion }>({
    queryKey: KEYS.detail(sessionRecordId!),
    queryFn: async () => {
      const res = await api.get(`/api/journal/sessions/${sessionRecordId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!sessionRecordId,
    staleTime: 30 * 1000,
  });
}

export function useSessionVersions(sessionRecordId?: string) {
  const { user } = useAuthStore();
  return useQuery<SessionSummaryVersion[]>({
    queryKey: KEYS.versions(sessionRecordId!),
    queryFn: async () => {
      const res = await api.get(`/api/journal/sessions/${sessionRecordId}/versions`);
      return res.data ?? res;
    },
    enabled: !!user && !!sessionRecordId,
    staleTime: 30 * 1000,
  });
}

export function useSessionAudio(sessionRecordId?: string) {
  const { user } = useAuthStore();
  return useQuery<AudioSegment[]>({
    queryKey: KEYS.audio(sessionRecordId!),
    queryFn: async () => {
      const res = await api.get(`/api/journal/sessions/${sessionRecordId}/audio`);
      return res.data ?? res;
    },
    enabled: !!user && !!sessionRecordId,
    staleTime: 60 * 1000,
  });
}

// ── Observations ──────────────────────────────────────────────

export function useObservations(sessionRecordId?: string) {
  const { user } = useAuthStore();
  return useQuery<SessionObservation[]>({
    queryKey: KEYS.observations(sessionRecordId!),
    queryFn: async () => {
      const res = await api.get(`/api/observations/session/${sessionRecordId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!sessionRecordId,
    staleTime: 30 * 1000,
  });
}

export function useCreateObservation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { session_record_id: string; observation_text: string }) => {
      return api.post('/api/observations', data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.observations(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.detail(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Observacao adicionada');
    },
    onError: () => {
      toast.error('Erro ao adicionar observacao');
    },
  });
}

export function useUpdateObservation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, observation_text, session_record_id }: { id: string; observation_text: string; session_record_id: string }) => {
      return api.patch(`/api/observations/${id}`, { observation_text });
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.observations(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.detail(variables.session_record_id) });
      toast.success('Observacao atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar observacao');
    },
  });
}

export function useDeleteObservation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, session_record_id }: { id: string; session_record_id: string }) => {
      return api.delete(`/api/observations/${id}`);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.observations(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.detail(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Observacao removida');
    },
    onError: () => {
      toast.error('Erro ao remover observacao');
    },
  });
}

// ── Patient Notes ──────────────────────────────────────────────

export function usePatientNotes(sessionRecordId?: string) {
  const { user } = useAuthStore();
  return useQuery<PatientSessionNote[]>({
    queryKey: KEYS.patientNotes(sessionRecordId!),
    queryFn: async () => {
      const res = await api.get(`/api/patient-notes/session/${sessionRecordId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!sessionRecordId,
    staleTime: 30 * 1000,
  });
}

export function useCreatePatientNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { session_record_id: string; note_text: string }) => {
      return api.post('/api/patient-notes', data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.patientNotes(variables.session_record_id) });
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Anotacao salva');
    },
    onError: () => {
      toast.error('Erro ao salvar anotacao');
    },
  });
}

export function useUpdatePatientNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, note_text, session_record_id }: { id: string; note_text: string; session_record_id: string }) => {
      return api.patch(`/api/patient-notes/${id}`, { note_text });
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.patientNotes(variables.session_record_id) });
      toast.success('Anotacao atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar anotacao');
    },
  });
}
