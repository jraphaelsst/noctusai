import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
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
    mutationFn: async (data: { patient_id: string }) => {
      return api.post('/api/matching/embed', data);
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
