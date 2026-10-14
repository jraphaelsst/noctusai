/**
 * `createPurchasingHooks(api)` — TanStack Query hooks for the purchasing API (`/api/purchasing`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data`
 * (indicator only). Never `isLoading`, never a bare `isFetching` gate. Lists whose key changes keep
 * `placeholderData: (prev) => prev`; the id-keyed order detail does not (another order's lines never show under a new id).
 *
 * Mutations reject with `ApiError` (the caller renders it; `purchasingErrorMessage` maps the stable codes) and invalidate
 * every read they can change. A receive also changes stock + payables, so hosts that mount those organs pass
 * `onReceived` to invalidate their own keys (`inventoryKeys.all`, the finance entries key).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ApiClient } from '../api';
import { errorMessage, keep, signals } from '../organ-kit/query';
import { defaultPurchasingT, type PurchasingTranslate } from './i18n';
import type {
  PurchaseApprover,
  PurchaseOrder,
  PurchaseOrderInput,
  PurchaseOrderListParams,
  PurchaseReceipt,
  PurchaseReceiptInput,
  PurchaseReceiptListParams,
  PurchaseReceiveResult,
  PurchasingEnvelope,
  PurchasingPaginated,
  PurchasingSettings,
} from './types';

export type PurchasingApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete'>;

const BASE = '/api/purchasing';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const purchasingKeys = {
  all: ['purchasing'] as const,
  orders: ['purchasing', 'orders'] as const,
  order: (id: string) => ['purchasing', 'order', id] as const,
  receipts: ['purchasing', 'receipts'] as const,
  settings: ['purchasing', 'settings'] as const,
  approvers: ['purchasing', 'approvers'] as const,
};

/** pt-BR copy for the stable backend error codes; falls back to the server message. */
export function purchasingErrorMessage(err: unknown, t: PurchasingTranslate = defaultPurchasingT): string {
  if (err instanceof ApiError && err.code) {
    const mapped = t(`error.${err.code}`);
    if (mapped !== `error.${err.code}`) return mapped;
  }
  return errorMessage(err);
}

function query(params: object): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') out[k] = v as string | number | boolean;
  return out;
}

export interface PurchasingHookOptions {
  /** Called after a receipt posted: invalidate the stock / finance reads of the organs you mounted. */
  onReceived?: () => void | Promise<unknown>;
}

export function createPurchasingHooks(api: PurchasingApi, options: PurchasingHookOptions = {}) {
  const unwrap = async <T,>(p: Promise<PurchasingEnvelope<T>>): Promise<T> => (await p).data;

  function useInvalidateOrders() {
    const qc = useQueryClient();
    return () => Promise.all([qc.invalidateQueries({ queryKey: purchasingKeys.orders }), qc.invalidateQueries({ queryKey: ['purchasing', 'order'] })]);
  }

  function usePurchaseOrders(params: PurchaseOrderListParams = {}) {
    const q = useQuery<PurchasingPaginated<PurchaseOrder>>({
      queryKey: [...purchasingKeys.orders, params],
      queryFn: () => api.get(`${BASE}/orders`, query(params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  function usePurchaseOrder(id: string | null | undefined) {
    const q = useQuery<PurchaseOrder>({
      queryKey: purchasingKeys.order(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/orders/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }

  function usePurchaseOrderMutations() {
    const qc = useQueryClient();
    const invalidate = useInvalidateOrders();
    const refreshed = async (order: PurchaseOrder) => {
      qc.setQueryData(purchasingKeys.order(order.id), order);
      await invalidate();
      return order;
    };
    const useOrderAction = (action: 'approve' | 'send') => useMutation({
      mutationFn: (id: string) => unwrap<PurchaseOrder>(api.post(`${BASE}/orders/${id}/${action}`)),
      onSuccess: refreshed,
    });
    return {
      /** Create (no `id`) or replace a DRAFT (`id`). */
      save: useMutation({
        mutationFn: ({ id, ...body }: PurchaseOrderInput & { id?: string }) =>
          unwrap<PurchaseOrder>(id ? api.put(`${BASE}/orders/${id}`, body) : api.post(`${BASE}/orders`, body)),
        onSuccess: refreshed,
      }),
      approve: useOrderAction('approve'),
      send: useOrderAction('send'),
      cancel: useMutation({
        mutationFn: ({ id, reason }: { id: string; reason?: string }) => unwrap<PurchaseOrder>(api.post(`${BASE}/orders/${id}/cancel`, reason ? { reason } : {})),
        onSuccess: refreshed,
      }),
    };
  }

  function usePurchaseReceipts(params: PurchaseReceiptListParams = {}) {
    const q = useQuery<PurchasingPaginated<PurchaseReceipt>>({
      queryKey: [...purchasingKeys.receipts, params],
      queryFn: () => api.get(`${BASE}/receipts`, query(params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  function useReceiptMutations() {
    const invalidate = useInvalidateOrders();
    const qc = useQueryClient();
    const done = async () => {
      await Promise.all([invalidate(), qc.invalidateQueries({ queryKey: purchasingKeys.receipts })]);
      await options.onReceived?.();
    };
    return {
      receive: useMutation({
        mutationFn: ({ orderId, ...body }: PurchaseReceiptInput & { orderId: string }) =>
          unwrap<PurchaseReceiveResult>(api.post(`${BASE}/orders/${orderId}/receipts`, body)),
        onSuccess: done,
      }),
      /** Re-run the posting legs (stock + payables) of a receipt that did not finish. */
      repost: useMutation({
        mutationFn: (receiptId: string) => unwrap<PurchaseReceipt>(api.post(`${BASE}/receipts/${receiptId}/post`)),
        onSuccess: done,
      }),
    };
  }

  function usePurchasingSettings() {
    const q = useQuery<PurchasingSettings>({
      queryKey: purchasingKeys.settings,
      queryFn: () => unwrap(api.get(`${BASE}/settings`)),
    });
    return signals(q);
  }

  function useSetPurchasingSettings() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (approval_threshold_cents: number | null) => unwrap<PurchasingSettings>(api.put(`${BASE}/settings`, { approval_threshold_cents })),
      onSuccess: (data) => {
        qc.setQueryData(purchasingKeys.settings, data);
      },
      // moving the limit is an APPROVER's act (the API answers 403 `sem_permissao_limite` otherwise) and starts a cooldown.
    });
  }

  /** The org's approver list (org admins only -- the API refuses everyone else). */
  function usePurchaseApprovers(enabled = true) {
    const q = useQuery<PurchaseApprover[]>({
      queryKey: purchasingKeys.approvers,
      queryFn: () => unwrap(api.get(`${BASE}/approvers`)),
      enabled,
    });
    return signals(q);
  }

  function usePurchaseApproverMutations() {
    const qc = useQueryClient();
    const done = (list: PurchaseApprover[]) => {
      qc.setQueryData(purchasingKeys.approvers, list);
      // `is_approver` on the settings read may have changed (the caller added / removed themselves).
      return qc.invalidateQueries({ queryKey: purchasingKeys.settings });
    };
    return {
      add: useMutation({
        mutationFn: (user_id: string) => unwrap<PurchaseApprover[]>(api.post(`${BASE}/approvers`, { user_id })),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (user_id: string) => unwrap<PurchaseApprover[]>(api.delete(`${BASE}/approvers/${user_id}`)),
        onSuccess: done,
      }),
    };
  }

  return {
    usePurchaseApprovers,
    usePurchaseApproverMutations,
    usePurchaseOrders,
    usePurchaseOrder,
    usePurchaseOrderMutations,
    usePurchaseReceipts,
    useReceiptMutations,
    usePurchasingSettings,
    useSetPurchasingSettings,
  };
}

export type PurchasingHooks = ReturnType<typeof createPurchasingHooks>;
