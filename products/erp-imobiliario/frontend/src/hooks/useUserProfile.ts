import { useQuery } from '@tanstack/react-query';
import { supabase, useAuthStore } from '@noctusai/seed/infra';

export function useUserProfile() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['user-profile', user?.id],
    queryFn: async () => {
      if (!user) return null;

      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', user.id)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !!user,
  });
}
