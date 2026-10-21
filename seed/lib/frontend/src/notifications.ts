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
  type QueryClient,
} from '@tanstack/react-query';
import { useCacheWriteMutation } from './cache-writes';
import { envelopeOps } from './organ-kit/cacheOps';
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
    return useCacheWriteMutation<Notificacao, string>({
      mutationFn: async (notificacaoId) => {
        const result = await api.patch(`/api/notificacoes/${notificacaoId}/ler`);
        return result.data as Notificacao;
      },
      // Read on click in every cached page (a page filtered to "unread only" re-filters on the settle
      // refetch); the unread count is a derived view, so it only refreshes.
      targets: (id) => [
        {
          queryKey: ['notificacoes'],
          match: 'prefix',
          optimistic: (old: any) => envelopeOps.patch<Notificacao>(old, id, { is_read: true }),
          commit: (old: any, saved: Notificacao) => envelopeOps.patch<Notificacao>(old, id, saved),
        },
      ],
      invalidate: [['notificacoes-contagem']],
    });
  }

  function useMarcarTodasComoLidas() {
    return useCacheWriteMutation<unknown, void>({
      mutationFn: async () => {
        return api.post('/api/notificacoes/ler-todas');
      },
      // Everything is read afterwards: draw it on click (every cached page, and the badge at zero).
      targets: [
        {
          queryKey: ['notificacoes'],
          match: 'prefix',
          optimistic: (old: any) =>
            old && Array.isArray(old.data)
              ? { ...old, data: old.data.map((n: Notificacao) => (n.is_read ? n : { ...n, is_read: true })) }
              : old,
        },
        {
          queryKey: ['notificacoes-contagem'],
          optimistic: (old: ContagemNaoLidas | undefined) => (old ? { ...old, nao_lidas: 0 } : old),
        },
      ],
      onSuccess: () => {
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
