import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { MoodEntry, MoodAnalytics } from '@/types';

const KEYS = {
  all: ['mood'] as const,
  list: (filters?: { page?: number; page_size?: number }) => ['mood', 'list', filters] as const,
  analytics: ['mood', 'analytics'] as const,
};

export function useMoodEntries(filters?: { page?: number; page_size?: number }) {
  const { user } = useAuthStore();
  return useQuery<{ data: MoodEntry[]; total: number }>({
    queryKey: KEYS.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.page) params.set('page', String(filters.page));
      if (filters?.page_size) params.set('page_size', String(filters.page_size));
      const qs = params.toString();
      const res = await api.get(`/api/mood${qs ? `?${qs}` : ''}`);
      return res;
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useMoodAnalytics() {
  const { user } = useAuthStore();
  return useQuery<MoodAnalytics>({
    queryKey: KEYS.analytics,
    queryFn: async () => {
      const res = await api.get('/api/mood/analytics');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateMoodEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      rating: number;
      emocoes?: string[];
      nota?: string;
      data: string;
    }) => {
      return api.post('/api/mood', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Humor registrado');
    },
    onError: () => {
      toast.error('Erro ao registrar humor');
    },
  });
}
