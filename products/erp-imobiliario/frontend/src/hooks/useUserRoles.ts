import { useQuery } from '@tanstack/react-query';
import { supabase, useAuthStore } from '@noctusai/seed/infra';

export function useUserRoles() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['user-roles', user?.id],
    queryFn: async () => {
      if (!user) return [];

      const { data, error } = await supabase
        .from('user_roles')
        .select('role')
        .eq('user_id', user.id);

      if (error) throw error;
      return data?.map(r => r.role) || [];
    },
    enabled: !!user,
  });
}
