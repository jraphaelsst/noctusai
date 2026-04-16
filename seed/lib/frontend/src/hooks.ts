/**
 * Generic CRUD hook factory for NoctusAI products.
 *
 * This creates a set of TanStack Query hooks (useList, useOne, useCreate,
 * useUpdate, useDelete) for any resource.  Individual product hooks can be
 * migrated to use this factory in a separate task; for now it is provided
 * as infrastructure.
 *
 * Usage example:
 * ```ts
 * import { createCrudHooks } from '@noctusai/shared/hooks';
 * import { api } from '@/lib/api-client';
 * import { useAuthStore } from '@/store/authStore';
 *
 * const clienteHooks = createCrudHooks({
 *   resource: 'clientes',
 *   apiPath: '/api/clientes',
 *   singularName: 'Cliente',
 *   api,
 *   getUser: () => useAuthStore.getState().user,
 *   staleTime: 3 * 60 * 1000,
 *   invalidates: [['dashboard']],
 * });
 *
 * export const useClientes = clienteHooks.useList;
 * export const useCliente = clienteHooks.useOne;
 * export const useCreateCliente = clienteHooks.useCreate;
 * export const useUpdateCliente = clienteHooks.useUpdate;
 * export const useDeleteCliente = clienteHooks.useDelete;
 * ```
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApiClient } from './api';

export interface CrudHookOptions<T = any> {
  /** Query key prefix (e.g. 'clientes') */
  resource: string;
  /** API path (e.g. '/api/clientes') */
  apiPath: string;
  /** Human-readable singular name for toast messages (e.g. 'Cliente') */
  singularName: string;
  /** The product's api client instance */
  api: ApiClient;
  /** Returns the current user (null when unauthenticated). Used for `enabled` guard. */
  getUser: () => any;
  /** Extra query keys to invalidate on mutations */
  invalidates?: string[][];
  /** Stale time in ms (default 5 min) */
  staleTime?: number;
}

export function createCrudHooks<T = any>(options: CrudHookOptions<T>) {
  const {
    resource,
    apiPath,
    singularName,
    api,
    getUser,
    invalidates = [],
    staleTime = 5 * 60 * 1000,
  } = options;

  function useList(params?: Record<string, any>) {
    const user = getUser();
    return useQuery({
      queryKey: [resource, params],
      queryFn: () => api.get(apiPath, params),
      enabled: !!user,
      staleTime,
    });
  }

  function useOne(id?: string) {
    const user = getUser();
    return useQuery({
      queryKey: [resource, id],
      queryFn: () => api.get(`${apiPath}/${id}`),
      enabled: !!user && !!id,
      staleTime,
    });
  }

  function useCreate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (data: Partial<T>) => api.post(apiPath, data),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: [resource] });
        invalidates.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
        toast.success(`${singularName} criado(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao criar ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  function useUpdate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: ({ id, ...data }: { id: string } & Partial<T>) =>
        api.patch(`${apiPath}/${id}`, data),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: [resource] });
        invalidates.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
        toast.success(`${singularName} atualizado(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao atualizar ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  function useDelete() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => api.delete(`${apiPath}/${id}`),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: [resource] });
        invalidates.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
        toast.success(`${singularName} excluido(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao excluir ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  return { useList, useOne, useCreate, useUpdate, useDelete };
}
