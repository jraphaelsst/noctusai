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
 * import { createCrudHooks } from '@noctusai/lib/hooks';
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
import { useQuery } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from './cache-writes';
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

  // Writes follow the cache-write contract (KB § PATTERNS/frontend/mutation-cache-writes.md):
  // the change is on screen before / the moment the server answers; the background
  // refetch after settle only refreshes it. Lists are reached by prefix (`[resource]`
  // covers every `[resource, params]` list); `listOps` leave non-array entries alone,
  // and the `[resource, id]` detail is written by an exact target.
  const settle = invalidates;

  function useCreate() {
    return useCacheWriteMutation<T & { id: string }, Partial<T>>({
      mutationFn: (data) => api.post(apiPath, data),
      // The unfiltered list gets the server's row; filtered lists can't know whether it
      // belongs to them, so they converge on the settle refetch.
      targets: [{
        queryKey: [resource, undefined],
        commit: (old: (T & { id: string })[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      }],
      invalidate: [[resource], ...settle],
      onSuccess: () => {
        toast.success(`${singularName} criado(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao criar ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  function useUpdate() {
    return useCacheWriteMutation<T & { id: string }, { id: string } & Partial<T>>({
      mutationFn: ({ id, ...data }) => api.patch(`${apiPath}/${id}`, data),
      targets: ({ id }) => [
        {
          queryKey: [resource],
          match: 'prefix',
          optimistic: (old: any, { id: _id, ...changes }) => listOps.patch(old, id, changes as any),
          commit: (old: any, saved) => (Array.isArray(old) ? listOps.patch(old, id, saved as any) : old),
        },
        {
          queryKey: [resource, id],
          optimistic: (old: any, { id: _id, ...changes }) => listOps.merge(old, changes),
          commit: (old: any, saved) => (old === undefined ? undefined : saved),
        },
      ],
      invalidate: settle,
      onSuccess: () => {
        toast.success(`${singularName} atualizado(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao atualizar ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  function useDelete() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${apiPath}/${id}`),
      targets: [{
        queryKey: [resource],
        match: 'prefix',
        optimistic: (old: any, id) => listOps.remove(old, id),
      }],
      invalidate: settle,
      onSuccess: () => {
        toast.success(`${singularName} excluido(a) com sucesso`);
      },
      onError: (error: Error) => {
        toast.error(`Erro ao excluir ${singularName.toLowerCase()}`, { description: error.message });
      },
    });
  }

  return { useList, useOne, useCreate, useUpdate, useDelete };
}
