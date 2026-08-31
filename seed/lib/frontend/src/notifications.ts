/**
 * Shared notification types and hook factories for all NoctusAI products.
 *
 * Every product's frontend should use these factories to create notification
 * hooks, ensuring a consistent API across the platform. Notifications live
 * in the core `public.notifications` table; each product's backend proxies
 * them via `/api/notificacoes` with Portuguese field names.
 *
 * Usage in a product:
 *   import { createNotificationHooks } from '@noctusai/lib/notifications';
 *   import { api } from '@/lib/api-client';
 *   import { useAuthStore } from '@/store/authStore';
 *   export const {
 *     useNotificacoes,
 *     useContagemNaoLidas,
 *     useMarcarComoLida,
 *     useMarcarTodasComoLidas,
 *   } = createNotificationHooks(api, useAuthStore);
 */
import {
  keepPreviousData,
  useQuery,
  useMutation,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApiClient } from './api';
import { useAuthReady } from './auth';

// ── Types ──────────────────────────────────────────────────────────

export interface Notificacao {
  id: string;
  org_id: string;
  user_id: string;
  tipo: string;
  titulo: string;
  mensagem?: string | null;
  is_read: boolean;
  link?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ContagemNaoLidas {
  nao_lidas: number;
}

// ── Hook Factory ───────────────────────────────────────────────────

export function createNotificationHooks(
  api: ApiClient,
  useAuthStore: () => { user: unknown },
) {
  function useNotificacoes(page = 1, pageSize = 20, apenasNaoLidas = false) {
    const { user } = useAuthStore();
    const authReady = useAuthReady();

    return useQuery({
      queryKey: ['notificacoes', page, pageSize, apenasNaoLidas],
      queryFn: async () => {
        const params = new URLSearchParams({
          page: String(page),
          page_size: String(pageSize),
        });
        if (apenasNaoLidas) params.set('apenas_nao_lidas', 'true');
        const result = await api.get(`/api/notificacoes?${params}`);
        return {
          data: (result.data || []) as Notificacao[],
          pagination: result.pagination,
        };
      },
      // Gate on auth-ready AND a user: the first fetch must not race
      // ahead of the restored session (else 401 → spurious
      // "servidor indisponível" toast on every standalone page load).
      enabled: authReady && !!user,
      staleTime: 30 * 1000,
      // Keyed on `page` — paging forward/back is a key change, so `data`
      // would otherwise go `undefined` for a tick and the notification list
      // would blank every page click instead of just updating in place.
      placeholderData: keepPreviousData,
    });
  }

  function useContagemNaoLidas() {
    const { user } = useAuthStore();
    const authReady = useAuthReady();

    return useQuery({
      queryKey: ['notificacoes-contagem'],
      queryFn: async () => {
        const result = await api.get('/api/notificacoes/contagem');
        return result as ContagemNaoLidas;
      },
      enabled: authReady && !!user,
      refetchInterval: 30000,
      staleTime: 30 * 1000,
    });
  }

  function useMarcarComoLida() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async (notificacaoId: string) => {
        const result = await api.patch(`/api/notificacoes/${notificacaoId}/ler`);
        return result.data as Notificacao;
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['notificacoes'] });
        queryClient.invalidateQueries({ queryKey: ['notificacoes-contagem'] });
      },
    });
  }

  function useMarcarTodasComoLidas() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async () => {
        return api.post('/api/notificacoes/ler-todas');
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['notificacoes'] });
        queryClient.invalidateQueries({ queryKey: ['notificacoes-contagem'] });
        toast.success('Todas as notificações marcadas como lidas');
      },
    });
  }

  return {
    useNotificacoes,
    useContagemNaoLidas,
    useMarcarComoLida,
    useMarcarTodasComoLidas,
  };
}
