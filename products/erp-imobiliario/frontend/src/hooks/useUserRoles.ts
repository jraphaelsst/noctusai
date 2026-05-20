import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

export function useUserRoles() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['user-roles', user?.id],
    queryFn: async () => {
      if (!user) return [];
      // Backend route /api/profiles/me/roles replaces the prior supabase.from('user_roles') bypass
      // (Pattern D resolution, Phase 4, 2026-05-20). Backend returns role names array.
      const res = await api.get<{ data: string[] }>('/api/profiles/me/roles');
      return res.data || [];
    },
    enabled: !!user,
  });
}
