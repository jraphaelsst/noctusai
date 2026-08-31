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
  const { data: role, isLoading, isPending, isFetching } = useUserRole();
  return {
    isAdmin: role === 'admin',
    // isLoading kept for existing non-render consumers (useEffect gates,
    // disabled= props); a RENDER branch must use isPending && !data (here:
    // role === null while isPending) — never isLoading — per
    // KB § PATTERNS/frontend/lying-loading-state.md.
    isLoading,
    isPending,
    isFetching,
    roleData: role,
  };
}
