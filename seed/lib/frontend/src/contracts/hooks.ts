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
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
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

  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));
  }

  /** Every read of one contract (detail, versions, billing) goes stale after a lifecycle mutation. */
  function useAfterChange() {
    const inv = useInvalidate();
    return (id: string) => inv(contractsKeys.lists, contractsKeys.detail(id), ['contracts', 'versions', id], ['contracts', 'preview', id], contractsKeys.billings(id), contractsKeys.usage(id));
  }

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
    const inv = useInvalidate();
    return useMutation({
      mutationFn: (body: ContractInput) => unwrap<Contract>(api.post(BASE, body)),
      onSuccess: () => inv(contractsKeys.lists),
    });
  }

  function useUpdateContract() {
    const after = useAfterChange();
    return useMutation({
      mutationFn: ({ id, ...body }: { id: string } & ContractPatch) => unwrap<Contract>(api.patch(`${BASE}/${id}`, body)),
      onSuccess: (_c, vars) => after(vars.id),
    });
  }

  function useDeleteContract() {
    const inv = useInvalidate();
    return useMutation({
      mutationFn: (id: string) => api.delete(`${BASE}/${id}`),
      onSuccess: (_r, id) => inv(contractsKeys.lists, contractsKeys.detail(id)),
    });
  }

  /** Lifecycle actions share one shape: POST `/{id}/<action>` -> the refreshed contract. */
  function useAction<TBody extends object | undefined = undefined>(action: string) {
    const after = useAfterChange();
    return useMutation({
      mutationFn: ({ id, body }: { id: string; body?: TBody }) => unwrap<Contract>(api.post(`${BASE}/${id}/${action}`, body ?? {})),
      onSuccess: (_c, vars) => after(vars.id),
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
    const after = useAfterChange();
    return useMutation({
      mutationFn: ({ id, summary, changes, effective_on }: { id: string; summary: string; changes: ContractTermChanges; effective_on?: string | null }) =>
        unwrap<Contract>(api.post(`${BASE}/${id}/amendments`, { summary, changes, effective_on })),
      onSuccess: (_c, vars) => after(vars.id),
    });
  }

  /** `apply=false` simulates (nothing is written); `apply=true` writes a `readjustment` version. */
  function useReadjustContract() {
    const after = useAfterChange();
    return useMutation({
      mutationFn: ({ id, ...body }: { id: string; percent_bp?: number | null; index?: string | null; apply?: boolean; effective_on?: string | null }) =>
        unwrap<ContractReadjustResult>(api.post(`${BASE}/${id}/readjust`, body)),
      onSuccess: (result, vars) => (result.applied ? after(vars.id) : undefined),
    });
  }

  function useAddUsage() {
    const after = useAfterChange();
    return useMutation({
      mutationFn: ({ id, ...body }: { id: string; minutes: number; period?: string | null; description?: string | null }) =>
        unwrap<unknown>(api.post(`${BASE}/${id}/usage`, body)),
      onSuccess: (_r, vars) => after(vars.id),
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
