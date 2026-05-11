import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { MatchResult } from '@/types';

const KEYS = {
  all: ['therapy-matching'] as const,
  results: (patientId: string) => ['therapy-matching', 'results', patientId] as const,
};

export function useMatchResults(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<MatchResult[]>({
    queryKey: KEYS.results(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/matching/results/${patientId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!patientId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useEmbedProfile() {
  const qc = useQueryClient();
  return useMutation({
    // The unified backend endpoint (POST /api/matching/embed) infers identity
    // + role from the JWT; `role` is only required for admin invocations. The
    // patient onboarding flow leaves the body empty.
    mutationFn: async (body?: { role?: 'terapeuta' | 'paciente' }) => {
      return api.post('/api/matching/embed', body ?? {});
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Perfil processado para matching');
    },
    onError: () => {
      toast.error('Erro ao processar perfil');
    },
  });
}
