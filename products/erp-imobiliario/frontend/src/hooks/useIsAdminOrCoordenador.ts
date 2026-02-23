import { useUserRole } from './useUserRole';

export function useIsAdminOrCoordenador() {
  const { data: userRole, isLoading } = useUserRole();
  
  const isAdminOrCoordenador = userRole === 'admin' || userRole === 'coordenador';
  
  return { isAdminOrCoordenador, isLoading };
}
