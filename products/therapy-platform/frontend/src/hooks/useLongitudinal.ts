import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type { ClinicalLongitudinal, PatientLongitudinal } from '@/types/session';

const KEYS = {
  clinicalLatest: (patientId: string) => ['longitudinal', 'clinical', patientId] as const,
  clinicalVersions: (patientId: string) => ['longitudinal', 'clinical', patientId, 'versions'] as const,
  patientLatest: ['longitudinal', 'personal'] as const,
  patientVersions: ['longitudinal', 'personal', 'versions'] as const,
};

// `patientId` comes from the route (PatientProfile.tsx) and can change
// via in-app navigation between patient profiles without a full remount.
// `placeholderData` is NOT used here on purpose: this is a clinical
// longitudinal analysis (therapist-facing psych summary) of a specific
// patient. Keeping the previous patient's analysis on screen while the
// next patient's loads would show one patient's clinical summary
// attributed to another — a cross-patient exposure bug, not a UX nicety.
// Patient switches show a skeleton instead.
// Per `KB § PATTERNS/frontend/lying-loading-state.md` § Key-changing queries.
export function useClinicalLongitudinal(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<ClinicalLongitudinal>({
    queryKey: KEYS.clinicalLatest(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/longitudinal/clinical/${patientId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!patientId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useClinicalLongitudinalVersions(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<ClinicalLongitudinal[]>({
    queryKey: KEYS.clinicalVersions(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/longitudinal/clinical/${patientId}/versions`);
      return res.data ?? res;
    },
    enabled: !!user && !!patientId,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatientLongitudinal() {
  const { user } = useAuthStore();
  return useQuery<PatientLongitudinal>({
    queryKey: KEYS.patientLatest,
    queryFn: async () => {
      const res = await api.get('/api/longitudinal/personal');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatientLongitudinalVersions() {
  const { user } = useAuthStore();
  return useQuery<PatientLongitudinal[]>({
    queryKey: KEYS.patientVersions,
    queryFn: async () => {
      const res = await api.get('/api/longitudinal/personal/versions');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}
