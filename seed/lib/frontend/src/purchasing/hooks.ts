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
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { ApiError, type ApiClient } from '../api';
import { errorMessage, keep, signals } from '../organ-kit/query';
import { pageOps } from '../organ-kit/page-ops';
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

  /**
   * The server answers every order write with the whole order, so it is written into that order's detail and into the
   * row of every cached list page (`pageOps`, prefix match) the moment it arrives. A brand-new order has no id until
   * then: its detail is seeded on success, and which list page it lands on is the server's call (background settle).
   * Other order details (an approval can move the siblings) refresh in the background too.
   */
  function usePurchaseOrderMutations() {
    const qc = useQueryClient();
    const orderWrites = (id: string) => [
      { queryKey: purchasingKeys.order(id), commit: (_old: PurchaseOrder | undefined, saved: PurchaseOrder) => saved },
      { queryKey: purchasingKeys.orders, match: 'prefix' as const, commit: (old: unknown, saved: PurchaseOrder) => pageOps.replace(old, id, saved) },
    ];
    const settled = [['purchasing', 'order'] as const];
    const useOrderAction = (action: 'approve' | 'send') =>
      useCacheWriteMutation<PurchaseOrder, string>({
        mutationFn: (id) => unwrap<PurchaseOrder>(api.post(`${BASE}/orders/${id}/${action}`)),
        targets: (id) => orderWrites(id),
        invalidate: [...settled],
      });
    return {
      /** Create (no `id`) or replace a DRAFT (`id`). */
      save: useCacheWriteMutation<PurchaseOrder, PurchaseOrderInput & { id?: string }>({
        mutationFn: ({ id, ...body }) =>
          unwrap<PurchaseOrder>(id ? api.put(`${BASE}/orders/${id}`, body) : api.post(`${BASE}/orders`, body)),
        targets: ({ id }) => (id ? orderWrites(id) : [{ queryKey: purchasingKeys.orders }]),
        invalidate: [...settled],
        onSuccess: (order, vars) => {
          if (!vars.id) qc.setQueryData(purchasingKeys.order(order.id), order);
        },
      }),
      approve: useOrderAction('approve'),
      send: useOrderAction('send'),
      cancel: useCacheWriteMutation<PurchaseOrder, { id: string; reason?: string }>({
        mutationFn: ({ id, reason }) => unwrap<PurchaseOrder>(api.post(`${BASE}/orders/${id}/cancel`, reason ? { reason } : {})),
        targets: ({ id }) => orderWrites(id),
        invalidate: [...settled],
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

  /**
   * A receipt answers with itself plus the order's new status: the order (detail + list rows) takes that status on the
   * spot and a re-posted receipt replaces its row. The receipt LIST is the server's (new row, page, sort), and stock /
   * payables live in other organs, so those refresh in the background / through `onReceived`.
   */
  function useReceiptMutations() {
    const afterReceipt = () => options.onReceived?.();
    return {
      receive: useCacheWriteMutation<PurchaseReceiveResult, PurchaseReceiptInput & { orderId: string }>({
        mutationFn: ({ orderId, ...body }) =>
          unwrap<PurchaseReceiveResult>(api.post(`${BASE}/orders/${orderId}/receipts`, body)),
        targets: ({ orderId }) => [
          {
            queryKey: purchasingKeys.order(orderId),
            commit: (old: PurchaseOrder | undefined, res: PurchaseReceiveResult) =>
              res.order_status ? listOps.merge(old, { status: res.order_status }) : old,
          },
          {
            queryKey: purchasingKeys.orders,
            match: 'prefix',
            commit: (old: unknown, res: PurchaseReceiveResult) =>
              res.order_status ? pageOps.patch(old, orderId, { status: res.order_status }) : old,
          },
          { queryKey: purchasingKeys.receipts },
        ],
        invalidate: [['purchasing', 'order']],
        onSuccess: afterReceipt,
      }),
      /** Re-run the posting legs (stock + payables) of a receipt that did not finish. */
      repost: useCacheWriteMutation<PurchaseReceipt, string>({
        mutationFn: (receiptId) => unwrap<PurchaseReceipt>(api.post(`${BASE}/receipts/${receiptId}/post`)),
        targets: (receiptId) => [
          {
            queryKey: purchasingKeys.receipts,
            match: 'prefix',
            commit: (old: unknown, saved: PurchaseReceipt) => pageOps.replace(old, receiptId, saved),
          },
          { queryKey: purchasingKeys.orders },
        ],
        invalidate: [['purchasing', 'order']],
        onSuccess: afterReceipt,
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
    // the server answers with the whole list: it replaces the cached one. `is_approver` on the settings read may have
    // changed (the caller added / removed themselves), so settings refresh in the background.
    const writes = {
      targets: [{ queryKey: purchasingKeys.approvers, commit: (_old: PurchaseApprover[] | undefined, list: PurchaseApprover[]) => list }],
      invalidate: [purchasingKeys.settings],
    };
    return {
      add: useCacheWriteMutation<PurchaseApprover[], string>({
        mutationFn: (user_id) => unwrap<PurchaseApprover[]>(api.post(`${BASE}/approvers`, { user_id })),
        ...writes,
      }),
      remove: useCacheWriteMutation<PurchaseApprover[], string>({
        mutationFn: (user_id) => unwrap<PurchaseApprover[]>(api.delete(`${BASE}/approvers/${user_id}`)),
        targets: [
          {
            ...writes.targets[0],
            optimistic: (old: PurchaseApprover[] | undefined, user_id: string) => old?.filter((a) => a.user_id !== user_id),
          },
        ],
        invalidate: writes.invalidate,
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
