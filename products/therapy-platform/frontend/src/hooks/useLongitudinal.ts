import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type { ClinicalLongitudinal, PatientLongitudinal } from '@/types/session';

const KEYS = {
  clinicalLatest: (patientId: string) => ['longitudinal', 'clinical', patientId] as const,
  clinicalVersions: (patientId: string) => ['longitudinal', 'clinical', patientId, 'versions'] as const,
  patientLatest: ['longitudinal', 'personal'] as const,
  patientVersions: ['longitudinal', 'personal', 'versions'] as const,
};

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
