/**
 * Core Notificações — typed client + react-query hooks for `/api/admin/notifications`
 * (every owner-facing notification the products declare, its on/off switch, 30-day send stats).
 *
 * The HTTP client arrives through `NotificationCatalogApiContext` (default: the app's `api`) so tests render the
 * page with a fake client. Switch writes are cache writes (optimistic flip, the server row on settle).
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import { api } from './api';
import type { HttpClient } from './billing';

export type SendStatus = 'sent' | 'partial' | 'failed' | 'suppressed' | 'no_recipient';

export interface NotificationKindRow {
  product: string;
  kind: string;
  titulo: string;
  descricao: string;
  gatilho: string;
  canais: string[];
  enabled: boolean;
  toggled_at: string | null;
  registered_at: string | null;
  last_seen_at: string | null;
  counts_30d: Record<SendStatus, number>;
  last_dispatch: { status: SendStatus; at: string } | null;
  last_sent_at: string | null;
}

export interface NotificationProduct {
  product: string;
  kinds: NotificationKindRow[];
  enabled_count: number;
  total: number;
}

export interface NotificationCatalog {
  window_days: number;
  sends_truncated: boolean;
  products: NotificationProduct[];
}

export interface NotificationSend {
  id: number;
  product: string;
  kind: string;
  org_id: string | null;
  status: SendStatus;
  recipients: number;
  delivered: number;
  reason: string | null;
  created_at: string;
}

export function createNotificationCatalogApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  return {
    catalog: () => unwrap<NotificationCatalog>(http.get('/api/admin/notifications')),
    sends: (product: string, kind: string) =>
      unwrap<NotificationSend[]>(
        http.get(
          `/api/admin/notifications/sends?product=${encodeURIComponent(product)}&kind=${encodeURIComponent(kind)}&limit=20`,
        ),
      ),
    switchKind: (product: string, kind: string, enabled: boolean) =>
      unwrap<{ enabled: boolean }>(
        http.patch(`/api/admin/notifications/${encodeURIComponent(product)}/${encodeURIComponent(kind)}`, { enabled }),
      ),
    switchProduct: (product: string, enabled: boolean) =>
      unwrap<{ enabled: boolean }>(http.patch(`/api/admin/notifications/${encodeURIComponent(product)}`, { enabled })),
  };
}

export type NotificationCatalogApi = ReturnType<typeof createNotificationCatalogApi>;

const NotificationCatalogApiContext = createContext<NotificationCatalogApi>(createNotificationCatalogApi(api));

export function NotificationCatalogApiProvider({ value, children }: { value: NotificationCatalogApi; children: ReactNode }) {
  return createElement(NotificationCatalogApiContext.Provider, { value }, children);
}

function useNotificationCatalogApi(): NotificationCatalogApi {
  return useContext(NotificationCatalogApiContext);
}

export const notificationKeys = {
  all: ['admin', 'notifications'] as const,
  catalog: ['admin', 'notifications', 'catalog'] as const,
  sends: (product: string, kind: string) => ['admin', 'notifications', 'sends', product, kind] as const,
};

export function useNotificationCatalog() {
  const a = useNotificationCatalogApi();
  // poll-budget: 120s (admin catalog page); ~5 calls/tick; worst 3600/day per open tab; hidden=paused
  return useQuery({ queryKey: notificationKeys.catalog, queryFn: a.catalog, refetchInterval: 120_000 });
}

export function useNotificationSends(product: string, kind: string, enabled: boolean) {
  const a = useNotificationCatalogApi();
  return useQuery({ queryKey: notificationKeys.sends(product, kind), queryFn: () => a.sends(product, kind), enabled });
}

function flip(old: NotificationCatalog | undefined, product: string, kind: string | null, enabled: boolean, at?: string) {
  if (!old) return old;
  return {
    ...old,
    products: old.products.map((p) => {
      if (p.product !== product) return p;
      const kinds = p.kinds.map((k) =>
        kind === null || k.kind === kind ? { ...k, enabled, toggled_at: at ?? k.toggled_at } : k,
      );
      return { ...p, kinds, enabled_count: kinds.filter((k) => k.enabled).length };
    }),
  };
}

export function useSwitchNotification() {
  const a = useNotificationCatalogApi();
  return useCacheWriteMutation<{ enabled: boolean }, { product: string; kind: string | null; enabled: boolean }>({
    mutationFn: (v) => (v.kind === null ? a.switchProduct(v.product, v.enabled) : a.switchKind(v.product, v.kind, v.enabled)),
    targets: (v) => [
      {
        queryKey: notificationKeys.catalog,
        optimistic: (old: NotificationCatalog | undefined) => flip(old, v.product, v.kind, v.enabled),
        commit: (old: NotificationCatalog | undefined, saved) =>
          flip(old, v.product, v.kind, saved.enabled, new Date().toISOString()),
      },
    ],
  });
}
