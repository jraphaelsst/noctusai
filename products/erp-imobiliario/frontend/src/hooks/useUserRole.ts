import { useUserRoles } from './useUserRoles';

export function useUserRole() {
  const { data: roles, ...rest } = useUserRoles();

  // Se o usuário tem múltiplas roles, prioriza admin
  let role: string | null = null;
  if (roles && roles.length > 0) {
    if (roles.includes('admin')) role = 'admin';
    else if (roles.includes('coordenador')) role = 'coordenador';
    else if (roles.includes('dev')) role = 'dev';
    else role = roles[0];
  }

  return { data: role, ...rest };
}

export function useIsAdmin() {
  const { data: role, isLoading } = useUserRole();
  return {
    isAdmin: role === 'admin',
    isLoading,
  };
}
