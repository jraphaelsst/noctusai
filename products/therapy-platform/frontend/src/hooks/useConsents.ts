import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

export type ConsentScope = 'recording' | 'transcription' | 'ai_summary' | 'longitudinal';

export interface ConsentRecord {
  id: string;
  appointment_id: string;
  patient_id: string;
  therapist_id: string;
  scope: ConsentScope;
  policy_version: string;
  purpose_text: string;
  actor_user_id: string;
  granted_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  revoke_reason: string | null;
}

const KEYS = {
  byAppointment: (id: string) => ['consents', 'appointment', id] as const,
};

const DEFAULT_RECORDING_PURPOSE =
  'Consentimento para gravação de áudio da sessão. ' +
  'Áudios são processados de forma segura e excluídos automaticamente após geração do resumo.';

export const CONSENT_POLICY_VERSION = 'v1';

// `appointmentId` can change while a consuming session/history view stays
// mounted (switching between appointments). `placeholderData` is NOT used
// here on purpose: this is the LGPD consent audit trail for a specific
// appointment (recording/transcription/AI-summary consent state).
// Keeping the previous appointment's consent grants on screen while the
// next appointment's load would show one appointment's consent status
// attributed to another — a compliance-relevant exposure bug, not a UX
// nicety. Appointment switches show a loading state instead.
// Per `KB § PATTERNS/frontend/lying-loading-state.md` § Key-changing queries.
export function useConsents(appointmentId?: string) {
  const { user } = useAuthStore();
  return useQuery<ConsentRecord[]>({
    queryKey: KEYS.byAppointment(appointmentId!),
    queryFn: async () => {
      const res = await api.get(`/api/consents/${appointmentId}`);
      return (res.data ?? res) as ConsentRecord[];
    },
    enabled: !!user && !!appointmentId,
    staleTime: 30 * 1000,
  });
}

export function getActiveConsent(records: ConsentRecord[] | undefined, scope: ConsentScope): ConsentRecord | undefined {
  return records?.find((r) => r.scope === scope && r.revoked_at === null);
}

export function useGrantConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      appointment_id: string;
      scope: ConsentScope;
      policy_version?: string;
      purpose_text?: string;
    }) => {
      const body = {
        appointment_id: input.appointment_id,
        scope: input.scope,
        policy_version: input.policy_version ?? CONSENT_POLICY_VERSION,
        purpose_text: input.purpose_text ?? DEFAULT_RECORDING_PURPOSE,
      };
      return api.post('/api/consents/grant', body);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: KEYS.byAppointment(vars.appointment_id) });
    },
    onError: () => {
      toast.error('Erro ao registrar consentimento');
    },
  });
}

export function useRevokeConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { appointment_id: string; scope: ConsentScope; reason?: string }) => {
      return api.post('/api/consents/revoke', input);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: KEYS.byAppointment(vars.appointment_id) });
      toast.success('Consentimento revogado');
    },
    onError: () => {
      toast.error('Erro ao revogar consentimento');
    },
  });
}
