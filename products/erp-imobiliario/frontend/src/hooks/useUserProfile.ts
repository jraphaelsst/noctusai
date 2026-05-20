import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

export function useUserProfile() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['user-profile', user?.id],
    queryFn: async () => {
      if (!user) return null;
      // Backend route /api/profiles/me replaces the prior supabase.from('profiles') bypass
      // (Pattern D resolution, Phase 4, 2026-05-20). RLS still gates the row.
      const res = await api.get<{ data: any }>('/api/profiles/me');
      return res.data;
    },
    enabled: !!user,
  });
}
