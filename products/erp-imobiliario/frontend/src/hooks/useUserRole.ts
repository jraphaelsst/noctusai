import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';

export function useUserRole() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['user-role', user?.id],
    queryFn: async () => {
      if (!user) return null;

      const { data, error } = await supabase
        .from('user_roles')
        .select('role')
        .eq('user_id', user.id);

      if (error) throw error;
      
      // Se o usuário tem múltiplas roles, prioriza admin
      if (!data || data.length === 0) return null;
      
      const roles = data.map(r => r.role);
      if (roles.includes('admin')) return 'admin';
      if (roles.includes('coordenador')) return 'coordenador';
      if (roles.includes('dev')) return 'dev';
      return roles[0];
    },
    enabled: !!user,
  });
}

export function useIsAdmin() {
  const { data: role, isLoading } = useUserRole();
  return {
    isAdmin: role === 'admin',
    isLoading,
  };
}
