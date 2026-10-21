/**
 * `createContractsHooks(api)` — TanStack Query hooks for the contracts staff API (`/api/contracts`).
 *
 * Transport: an already-authenticated seed `ApiClient`; `{data}` / `{data, pagination}` envelopes are unwrapped here.
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data` (organ-kit `signals`). The list keeps
 * `placeholderData` across key changes; the by-id read does NOT (it carries the party's name / masked document, and
 * showing the previous contract under a new key would leak it).
 *
 * Errors are never swallowed: queries expose `error`, mutations reject with `ApiError` (409 `aviso_previo_nao_cumprido`,
 * 409 `contrato_vigente_use_aditivo`, 422 ...) so the caller renders it.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCacheWriteMutation, type CacheWriteTarget } from '../cache-writes';
import { envelopeOps } from '../organ-kit/cacheOps';
import { apiErrorCode, errorMessage, keep, signals, type OrganApi } from '../organ-kit/query';
import type {
  Contract, ContractBillingPreviewData, ContractBillingRecord, ContractInput, ContractPatch, ContractReadjustResult,
  ContractsEnvelope, ContractsListParams, ContractsPaginated, ContractTermChanges, ContractTerminateInput, ContractUsageMonth,
  ContractVersion,
} from './types';

export type ContractsApi = OrganApi;

const BASE = '/api/contracts';

export const contractsKeys = {
  all: ['contracts'] as const,
  lists: ['contracts', 'list'] as const,
  list: (params: ContractsListParams) => ['contracts', 'list', params] as const,
  detail: (id: string) => ['contracts', 'detail', id] as const,
  versions: (id: string) => ['contracts', 'versions', id] as const,
  preview: (id: string, count: number) => ['contracts', 'preview', id, count] as const,
  billings: (id: string) => ['contracts', 'billings', id] as const,
  usage: (id: string) => ['contracts', 'usage', id] as const,
};

export { apiErrorCode, errorMessage };

/** The query string of a list request (empty filters are not sent). */
export function listQuery(params: ContractsListParams): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (params.q?.trim()) out.q = params.q.trim();
  if (params.status) out.status = params.status;
  if (params.billing_model) out.billing_model = params.billing_model;
  if (params.party_id) out.party_id = params.party_id;
  if (params.expiring_within_days != null) out.expiring_within_days = params.expiring_within_days;
  if (params.page) out.page = params.page;
  if (params.page_size) out.page_size = params.page_size;
  return out;
}

export function createContractsHooks(api: ContractsApi) {
  const unwrap = async <T,>(p: Promise<ContractsEnvelope<T>>): Promise<T> => (await p).data;

  /** Every other read of one contract (versions, preview, billing, usage) goes stale after a lifecycle mutation. */
  const derivedKeys = (id: string) => [
    ['contracts', 'versions', id], ['contracts', 'preview', id], contractsKeys.billings(id), contractsKeys.usage(id),
  ];

  /**
   * A lifecycle write answers with the refreshed contract: it goes into the detail and into every cached list
   * page that shows it (the lists re-filter on the settle refetch); the derived reads are only invalidated.
   */
  const contractTargets = (id: string): CacheWriteTarget<Contract, any, any>[] => [
    { queryKey: contractsKeys.lists, match: 'prefix', commit: (old: any, saved: Contract) => envelopeOps.patch(old, id, saved) },
    { queryKey: contractsKeys.detail(id), commit: (old: Contract | undefined, saved: Contract) => (old === undefined ? undefined : saved) },
  ];

  function useContracts(params: ContractsListParams = {}) {
    return signals(useQuery<ContractsPaginated<Contract>>({
      queryKey: contractsKeys.list(params),
      queryFn: () => api.get(BASE, listQuery(params)),
      placeholderData: keep,
    }));
  }

  function useContract(id: string | null | undefined) {
    return signals(useQuery<Contract>({
      queryKey: contractsKeys.detail(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}`)),
      enabled: !!id,
    }));
  }

  function useVersions(id: string | null | undefined) {
    return signals(useQuery<ContractVersion[]>({
      queryKey: contractsKeys.versions(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/versions`)),
      enabled: !!id,
    }));
  }

  function useBillingPreview(id: string | null | undefined, count = 6) {
    return signals(useQuery<ContractBillingPreviewData>({
      queryKey: contractsKeys.preview(id ?? '', count),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/billing-preview`, { count })),
      enabled: !!id,
    }));
  }

  function useBillings(id: string | null | undefined) {
    return signals(useQuery<ContractBillingRecord[]>({
      queryKey: contractsKeys.billings(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/billings`)),
      enabled: !!id,
    }));
  }

  function useUsage(id: string | null | undefined) {
    return signals(useQuery<ContractUsageMonth[]>({
      queryKey: contractsKeys.usage(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/usage`)),
      enabled: !!id,
    }));
  }

  function useCreateContract() {
    const qc = useQueryClient();
    return useCacheWriteMutation<Contract, ContractInput>({
      mutationFn: (body) => unwrap<Contract>(api.post(BASE, body)),
      // Placement in a filtered / paged list is the server's call: lists converge on the settle refetch.
      targets: [{ queryKey: contractsKeys.lists, match: 'prefix' }],
      // The new contract's detail is known now — opening it needs no round trip.
      onSuccess: (saved) => {
        qc.setQueryData(contractsKeys.detail(saved.id), saved);
      },
    });
  }

  function useUpdateContract() {
    return useCacheWriteMutation<Contract, { id: string } & ContractPatch>({
      mutationFn: ({ id, ...body }) => unwrap<Contract>(api.patch(`${BASE}/${id}`, body)),
      targets: ({ id }) => contractTargets(id),
      invalidate: ({ id }) => derivedKeys(id),
    });
  }

  function useDeleteContract() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/${id}`),
      targets: (id) => [
        { queryKey: contractsKeys.lists, match: 'prefix', optimistic: (old: any) => envelopeOps.remove(old, id) },
        { queryKey: contractsKeys.detail(id) },
      ],
    });
  }

  /** Lifecycle actions share one shape: POST `/{id}/<action>` -> the refreshed contract. */
  function useAction<TBody extends object | undefined = undefined>(action: string) {
    return useCacheWriteMutation<Contract, { id: string; body?: TBody }>({
      mutationFn: ({ id, body }) => unwrap<Contract>(api.post(`${BASE}/${id}/${action}`, body ?? {})),
      targets: ({ id }) => contractTargets(id),
      invalidate: ({ id }) => derivedKeys(id),
    });
  }

  const useActivateContract = () => useAction('activate');
  const useSuspendContract = () => useAction<{ reason: string }>('suspend');
  const useResumeContract = () => useAction('resume');
  const useTerminateContract = () => useAction<ContractTerminateInput>('terminate');
  const useRenderDocument = () => useAction<{ template?: string | null }>('document');
  const useSyncSignature = () => useAction('signature/sync');
  const useSendSignature = () =>
    useAction<{ signers: { name: string; email: string; cpf: string; role?: string; order?: number }[]; message?: string | null }>('signature');

  function useAmendContract() {
    return useCacheWriteMutation<Contract, { id: string; summary: string; changes: ContractTermChanges; effective_on?: string | null }>({
      mutationFn: ({ id, summary, changes, effective_on }) =>
        unwrap<Contract>(api.post(`${BASE}/${id}/amendments`, { summary, changes, effective_on })),
      targets: ({ id }) => contractTargets(id),
      invalidate: ({ id }) => derivedKeys(id),
    });
  }

  /** `apply=false` simulates (nothing is written); `apply=true` writes a `readjustment` version. */
  function useReadjustContract() {
    return useCacheWriteMutation<ContractReadjustResult, { id: string; percent_bp?: number | null; index?: string | null; apply?: boolean; effective_on?: string | null }>({
      mutationFn: ({ id, ...body }) => unwrap<ContractReadjustResult>(api.post(`${BASE}/${id}/readjust`, body)),
      // Only an APPLIED readjustment changes the contract; a simulation leaves every cached read as it was.
      // The result is a diff, not the contract, so its new amounts are written onto the cached rows.
      targets: ({ id, apply }) => {
        if (!apply) return [];
        const changes = (r: ContractReadjustResult): Partial<Contract> => ({
          amount_cents: r.amount_cents_after,
          excess_rate_cents: r.excess_rate_cents_after,
          readjustment_percent_bp: r.percent_bp,
        });
        return [
          {
            queryKey: contractsKeys.lists,
            match: 'prefix',
            commit: (old: any, r: ContractReadjustResult) => (r.applied ? envelopeOps.patch(old, id, changes(r)) : old),
          },
          {
            queryKey: contractsKeys.detail(id),
            commit: (old: Contract | undefined, r: ContractReadjustResult) => (old && r.applied ? { ...old, ...changes(r) } : old),
          },
        ];
      },
      invalidate: ({ id, apply }) => (apply ? derivedKeys(id) : []),
    });
  }

  function useAddUsage() {
    return useCacheWriteMutation<unknown, { id: string; minutes: number; period?: string | null; description?: string | null }>({
      mutationFn: ({ id, ...body }) => unwrap<unknown>(api.post(`${BASE}/${id}/usage`, body)),
      // The response is not the usage row and the months are server-aggregated: the usage read refetches.
      targets: ({ id }) => [{ queryKey: contractsKeys.usage(id) }],
      invalidate: ({ id }) => [contractsKeys.detail(id), contractsKeys.lists, ...derivedKeys(id)],
    });
  }

  return {
    useContracts, useContract, useVersions, useBillingPreview, useBillings, useUsage,
    useCreateContract, useUpdateContract, useDeleteContract,
    useActivateContract, useSuspendContract, useResumeContract, useTerminateContract,
    useAmendContract, useReadjustContract, useAddUsage, useRenderDocument, useSendSignature, useSyncSignature,
  };
}

export type ContractsHooks = ReturnType<typeof createContractsHooks>;
