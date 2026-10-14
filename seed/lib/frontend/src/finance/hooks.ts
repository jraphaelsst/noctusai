/**
 * `createFinanceHooks(apiBase | api)` — TanStack Query hooks for the finance API
 * (`/api/finance`, CONTRACT §3 + §10.5). Product-agnostic: the host passes an
 * authenticated seed `ApiClient` (staff UI) or a base URL, and mounts the pages under
 * its own route (e.g. `/admin/financeiro/*`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook
 * returns `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`
 * (the commerce organ's `signals`) — never `isLoading`, never a bare `isFetching` gate.
 * Lists keyed by filters/page keep `placeholderData: (prev) => prev`. Reports keyed by a
 * period do too (same org, same shape). Errors are never swallowed: queries expose `error`,
 * mutations reject with `ApiError` so the caller renders it.
 *
 * Money is integer cents on the wire in both directions.
 */
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import { ApiError, type ApiClient } from '../api';
import { createFetchTransport, errorMessage, keep, signals } from '../organ-kit/query';
import { buildQuery } from './format';
import type {
  AccountBalance,
  AccountInput,
  AccountPatch,
  CashflowReportData,
  AgingReportData,
  FinanceCategoryInput,
  FinanceCategoryPatch,
  CostCenter,
  CostCenterInput,
  CostCenterPatch,
  CsvColumnMap,
  EntryDirection,
  EntryInput,
  EntryPatch,
  EntryStatus,
  FinanceAccount,
  FinanceAttachment,
  FinanceCategory,
  FinanceEntry,
  FinanceEntryDetail,
  FinancePaginated,
  GatewaySyncResult,
  MatchResult,
  MatchStatus,
  Recurrence,
  RecurrenceInput,
  RecurrencePatchInput,
  SettleInput,
  SettleResult,
  StatementImport,
  StatementImportResult,
  StatementLine,
  TransferInput,
  TransferResult,
} from './types';
import type {
  Budget,
  BudgetItemInput,
  BudgetReportData,
  LivroCaixaData,
  MeiMonthlyData,
} from './accountantTypes';
import type {
  AccountantChecklistData,
  DreConfirmInput,
  DreReportData,
  DreSettings,
  DreSettingsInput,
  DreView,
  SimplesBaseData,
} from './dreTypes';

export { errorMessage };
export { apiErrorCode, apiErrorStatus } from '../organ-kit/query';

/** The subset of the seed `ApiClient` the finance hooks need. */
export type FinanceApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete' | 'upload' | 'download'>;

export interface EntryListParams {
  direction?: EntryDirection | '';
  status?: EntryStatus | '';
  overdue?: boolean;
  from?: string;
  to?: string;
  category_id?: string;
  cost_center_id?: string;
  q?: string;
  page?: number;
  page_size?: number;
}
export interface PeriodParams {
  from?: string;
  to?: string;
}
export interface CashflowParams extends PeriodParams {
  account_id?: string;
}
export interface StatementLineParams {
  match_status?: MatchStatus | '';
  page?: number;
  page_size?: number;
}
export interface StatementImportInput {
  account_id: string;
  file: File;
  format?: 'ofx' | 'csv';
  column_map?: CsvColumnMap;
}
export interface DownloadInput {
  path: string;
  params?: Record<string, unknown>;
  filename: string;
}

export const FINANCE_BASE = '/api/finance';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const financeKeys = {
  all: ['finance'] as const,
  accounts: ['finance', 'accounts'] as const,
  balance: (id: string, on?: string) => ['finance', 'balance', id, on ?? 'today'] as const,
  categories: ['finance', 'categories'] as const,
  costCenters: ['finance', 'cost-centers'] as const,
  entries: ['finance', 'entries'] as const,
  entry: (id: string) => ['finance', 'entries', 'detail', id] as const,
  attachments: (entryId: string) => ['finance', 'entries', 'detail', entryId, 'attachments'] as const,
  recurrences: ['finance', 'recurrences'] as const,
  reports: ['finance', 'reports'] as const,
  statements: ['finance', 'statements'] as const,
};

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Plain-fetch transport for a base URL (adds `download` to the commerce transport). */
export function createFinanceTransport(apiBase: string): FinanceApi {
  const base = apiBase.replace(/\/+$/, '');
  return {
    ...createFetchTransport(apiBase),
    download: async (path: string) => {
      const res = await fetch(`${base}${path}`);
      if (!res.ok) throw new ApiError(res.status, `Erro HTTP ${res.status}`);
      return res.blob();
    },
  };
}

export function createFinanceHooks(apiOrBase: string | FinanceApi) {
  const api: FinanceApi = typeof apiOrBase === 'string' ? createFinanceTransport(apiOrBase) : apiOrBase;
  const p = (path: string) => `${FINANCE_BASE}${path}`;

  const data = async <T,>(promise: Promise<{ data: T }>): Promise<T> => (await promise).data;

  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
  }

  // ---- accounts ----------------------------------------------------------
  function useAccounts(params: { active?: boolean } = {}) {
    const q = useQuery<FinanceAccount[]>({
      queryKey: [...financeKeys.accounts, params],
      queryFn: () => data(api.get(p('/accounts'), params.active === undefined ? undefined : { active: params.active })),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useAccountBalances(ids: string[], on?: string) {
    return useQueries({
      queries: ids.map((id) => ({
        queryKey: financeKeys.balance(id, on),
        queryFn: () => data<AccountBalance>(api.get(p(`/accounts/${id}/balance`), on ? { on } : undefined)),
        placeholderData: keep,
      })),
      combine: (results) => ({
        byId: Object.fromEntries(
          results.map((r, i) => [ids[i], r.data] as const).filter(([, d]) => !!d),
        ) as Record<string, AccountBalance>,
        showSkeleton: results.some((r) => r.isPending && !r.data),
        isRefreshing: results.some((r) => r.isFetching && !!r.data),
        isError: results.some((r) => r.isError),
        error: results.find((r) => r.error)?.error ?? null,
        refetch: () => results.forEach((r) => void r.refetch()),
      }),
    });
  }
  function useAccountMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.accounts, ['finance', 'balance'], financeKeys.reports);
    return {
      create: useMutation({
        mutationFn: (b: AccountInput) => data<FinanceAccount>(api.post(p('/accounts'), b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: AccountPatch & { id: string }) =>
          data<FinanceAccount>(api.patch(p(`/accounts/${id}`), b)),
        onSuccess: done,
      }),
    };
  }

  // ---- categories --------------------------------------------------------
  function useCategories() {
    const q = useQuery<FinanceCategory[]>({
      queryKey: financeKeys.categories,
      queryFn: () => data(api.get(p('/categories'))),
    });
    return signals(q);
  }
  function useCategoryMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.categories, financeKeys.reports);
    return {
      create: useMutation({
        mutationFn: (b: FinanceCategoryInput) => data<FinanceCategory>(api.post(p('/categories'), b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: FinanceCategoryPatch & { id: string }) =>
          data<FinanceCategory>(api.patch(p(`/categories/${id}`), b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(p(`/categories/${id}`)),
        onSuccess: done,
      }),
    };
  }

  // ---- cost centers ------------------------------------------------------
  function useCostCenters() {
    const q = useQuery<CostCenter[]>({
      queryKey: financeKeys.costCenters,
      queryFn: () => data(api.get(p('/cost-centers'))),
    });
    return signals(q);
  }
  function useCostCenterMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.costCenters);
    return {
      create: useMutation({
        mutationFn: (b: CostCenterInput) => data<CostCenter>(api.post(p('/cost-centers'), b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: CostCenterPatch & { id: string }) =>
          data<CostCenter>(api.patch(p(`/cost-centers/${id}`), b)),
        onSuccess: done,
      }),
    };
  }

  // ---- entries -----------------------------------------------------------
  function useEntries(params: EntryListParams = {}) {
    const q = useQuery<FinancePaginated<FinanceEntry>>({
      queryKey: [...financeKeys.entries, 'list', params],
      queryFn: () => api.get(p('/entries'), params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useEntry(id: string | null | undefined) {
    // No placeholderData: id-keyed detail must not show another entry's settlements.
    const q = useQuery<FinanceEntryDetail>({
      queryKey: financeKeys.entry(id ?? ''),
      queryFn: () => data(api.get(p(`/entries/${id}`))),
      enabled: !!id,
    });
    return signals(q);
  }
  /** Anything that changes money must refresh lists, the entry, balances and every report. */
  function useMoneyInvalidate() {
    const inv = useInvalidate();
    return () => inv(financeKeys.entries, ['finance', 'balance'], financeKeys.reports, financeKeys.statements);
  }
  function useEntryMutations() {
    const done = useMoneyInvalidate();
    return {
      /** Always answers a LIST (one element, or the whole installment group). */
      create: useMutation({
        mutationFn: (b: EntryInput) => data<FinanceEntry[]>(api.post(p('/entries'), b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: EntryPatch & { id: string }) =>
          data<FinanceEntry>(api.patch(p(`/entries/${id}`), b)),
        onSuccess: done,
      }),
      cancel: useMutation({
        mutationFn: (id: string) => data<FinanceEntry>(api.post(p(`/entries/${id}/cancel`), {})),
        onSuccess: done,
      }),
      settle: useMutation({
        mutationFn: ({ id, ...b }: SettleInput & { id: string }) =>
          data<SettleResult>(api.post(p(`/entries/${id}/settlements`), b)),
        onSuccess: done,
      }),
      reverse: useMutation({
        mutationFn: ({ settlementId, reason }: { settlementId: string; reason: string }) =>
          data<SettleResult>(api.post(p(`/settlements/${settlementId}/reverse`), { reason })),
        onSuccess: done,
      }),
    };
  }

  // ---- attachments -------------------------------------------------------
  function useAttachments(entryId: string | null | undefined) {
    const q = useQuery<FinanceAttachment[]>({
      queryKey: financeKeys.attachments(entryId ?? ''),
      queryFn: () => data(api.get(p(`/entries/${entryId}/attachments`))),
      enabled: !!entryId,
    });
    return signals(q);
  }
  function useAttachmentMutations(entryId: string) {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.attachments(entryId), financeKeys.entry(entryId));
    return {
      upload: useMutation({
        mutationFn: (file: File) => {
          const form = new FormData();
          form.append('file', file);
          return data<FinanceAttachment>(api.upload(p(`/entries/${entryId}/attachments`), form));
        },
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (attachmentId: string) => api.delete(p(`/attachments/${attachmentId}`)),
        onSuccess: done,
      }),
    };
  }

  // ---- recurrences + transfers ------------------------------------------
  function useRecurrences() {
    const q = useQuery<Recurrence[]>({
      queryKey: financeKeys.recurrences,
      queryFn: () => data(api.get(p('/recurrences'))),
    });
    return signals(q);
  }
  function useRecurrenceMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.recurrences);
    return {
      create: useMutation({
        mutationFn: (b: RecurrenceInput) => data<Recurrence>(api.post(p('/recurrences'), b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: RecurrencePatchInput & { id: string }) =>
          data<Recurrence>(api.patch(p(`/recurrences/${id}`), b)),
        onSuccess: done,
      }),
    };
  }
  function useTransfer() {
    const done = useMoneyInvalidate();
    return useMutation({
      mutationFn: (b: TransferInput) => data<TransferResult>(api.post(p('/transfers'), b)),
      onSuccess: done,
    });
  }

  // ---- reports -----------------------------------------------------------
  function useCashflow(params: CashflowParams = {}) {
    const q = useQuery<CashflowReportData>({
      queryKey: [...financeKeys.reports, 'cashflow', params],
      queryFn: () => data(api.get(p('/reports/cashflow'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useAging(asOf?: string) {
    const q = useQuery<AgingReportData>({
      queryKey: [...financeKeys.reports, 'aging', asOf ?? 'today'],
      queryFn: () => data(api.get(p('/reports/aging'), asOf ? { as_of: asOf } : undefined)),
      placeholderData: keep,
    });
    return signals(q);
  }

  // ---- DRE (CONTRACT §10 / §10.5 / §11) ---------------------------------------------------
  function useDre(params: PeriodParams & { view?: DreView } = {}) {
    const q = useQuery<DreReportData>({
      queryKey: [...financeKeys.reports, 'dre', params],
      queryFn: () => data(api.get(p('/reports/dre'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useSimplesBase(params: PeriodParams = {}) {
    const q = useQuery<SimplesBaseData>({
      queryKey: [...financeKeys.reports, 'simples-base', params],
      queryFn: () => data(api.get(p('/reports/simples-base'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useAccountantChecklist() {
    const q = useQuery<AccountantChecklistData>({
      queryKey: [...financeKeys.reports, 'accountant-checklist'],
      queryFn: () => data(api.get(p('/accountant-checklist'))),
    });
    return signals(q);
  }
  function useDreSettings() {
    const q = useQuery<DreSettings>({
      queryKey: [...financeKeys.reports, 'dre-settings'],
      queryFn: () => data(api.get(p('/dre-settings'))),
    });
    return signals(q);
  }
  function useDreSettingsMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.reports);
    return {
      save: useMutation({
        mutationFn: (b: DreSettingsInput) => data<DreSettings>(api.put(p('/dre-settings'), b)),
        onSuccess: done,
      }),
      /** Confirm (or un-confirm) choices: the backend has no /confirm route, it is `PUT` with `confirmations`. */
      confirm: useMutation({
        mutationFn: ({ fields, note, confirmed = true }: DreConfirmInput) =>
          data<DreSettings>(
            api.put(p('/dre-settings'), {
              confirmations: Object.fromEntries(fields.map((f) => [f, { confirmed, note: note ?? null }])),
            }),
          ),
        onSuccess: done,
      }),
    };
  }

  // ---- budgets, Livro Caixa, MEI monthly (E21) -----------------------------------------------
  function useBudgetReport(params: PeriodParams = {}) {
    const q = useQuery<BudgetReportData>({
      queryKey: [...financeKeys.reports, 'budget', params],
      queryFn: () => data(api.get(p('/reports/budget'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useBudgetMutations() {
    const inv = useInvalidate();
    const done = () => inv(financeKeys.reports);
    return {
      save: useMutation({
        mutationFn: (items: BudgetItemInput[]) => data<Budget[]>(api.put(p('/budgets'), { items })),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(p(`/budgets/${id}`)),
        onSuccess: done,
      }),
    };
  }
  function useBudgets(params: PeriodParams = {}) {
    const q = useQuery<Budget[]>({
      queryKey: [...financeKeys.reports, 'budgets', params],
      queryFn: () => data(api.get(p('/budgets'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useLivroCaixa(params: PeriodParams & { page?: number; page_size?: number } = {}) {
    const q = useQuery<LivroCaixaData>({
      queryKey: [...financeKeys.reports, 'livro-caixa', params],
      queryFn: () => data(api.get(p('/reports/livro-caixa'), params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  /** `month` = any day of the month (`YYYY-MM-DD`). */
  function useMeiMonthly(month: string) {
    const q = useQuery<MeiMonthlyData>({
      queryKey: [...financeKeys.reports, 'mei-monthly', month],
      queryFn: () => data(api.get(p('/reports/mei-monthly'), { month })),
      placeholderData: keep,
    });
    return signals(q);
  }

  // ---- reconciliation ----------------------------------------------------
  function useStatements(params: { account_id?: string; page?: number } = {}) {
    const q = useQuery<FinancePaginated<StatementImport>>({
      queryKey: [...financeKeys.statements, 'list', params],
      queryFn: () => api.get(p('/statements'), params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useStatementLines(importId: string | null | undefined, params: StatementLineParams = {}) {
    const q = useQuery<FinancePaginated<StatementLine>>({
      queryKey: [...financeKeys.statements, 'lines', importId ?? '', params],
      queryFn: () => api.get(p(`/statements/${importId}/lines`), params),
      enabled: !!importId,
      // Keep the rows only while paging/filtering the SAME import; another import's lines under a new
      // import's header would be a lie.
      placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[3] === (importId ?? '') ? prev : undefined),
    });
    return signals(q);
  }
  function useReconciliationMutations() {
    const done = useMoneyInvalidate();
    return {
      importStatement: useMutation({
        mutationFn: ({ account_id, file, format, column_map }: StatementImportInput) => {
          const form = new FormData();
          form.append('account_id', account_id);
          form.append('file', file);
          if (format) form.append('format', format);
          if (column_map) form.append('column_map', JSON.stringify(column_map));
          return data<StatementImportResult>(api.upload(p('/statements'), form));
        },
        onSuccess: done,
      }),
      match: useMutation({
        mutationFn: ({ lineId, entryId }: { lineId: string; entryId: string }) =>
          data<MatchResult>(api.post(p(`/statement-lines/${lineId}/match`), { entry_id: entryId })),
        onSuccess: done,
      }),
      ignore: useMutation({
        mutationFn: (lineId: string) => data<StatementLine>(api.post(p(`/statement-lines/${lineId}/ignore`), {})),
        onSuccess: done,
      }),
      gatewaySync: useMutation({
        mutationFn: ({ accountId, since }: { accountId: string; since?: string }) =>
          data<GatewaySyncResult>(api.post(p(`/accounts/${accountId}/gateway-sync`), since ? { since } : {})),
        onSuccess: done,
      }),
    };
  }

  // ---- exports (admin or the accountant read grant) ---------------------------------------------------
  function useExport() {
    return useMutation({
      mutationFn: async ({ path, params, filename }: DownloadInput) => {
        const blob = await api.download(`${path}${buildQuery(params)}`);
        saveBlob(blob, filename);
      },
    });
  }

  return {
    useAccounts,
    useAccountBalances,
    useAccountMutations,
    useCategories,
    useCategoryMutations,
    useCostCenters,
    useCostCenterMutations,
    useEntries,
    useEntry,
    useEntryMutations,
    useAttachments,
    useAttachmentMutations,
    useRecurrences,
    useRecurrenceMutations,
    useTransfer,
    useCashflow,
    useAging,
    useDre,
    useSimplesBase,
    useBudgetReport,
    useBudgetMutations,
    useBudgets,
    useLivroCaixa,
    useMeiMonthly,
    useAccountantChecklist,
    useDreSettings,
    useDreSettingsMutations,
    useStatements,
    useStatementLines,
    useReconciliationMutations,
    useExport,
  };
}

export type FinanceHooks = ReturnType<typeof createFinanceHooks>;

/** Export endpoints (paths relative to the API root) shared by `ExportsPanel` and the accountant checklist. */
export const FINANCE_EXPORT_PATHS = {
  entries: `${FINANCE_BASE}/exports/entries.csv`,
  ledger: `${FINANCE_BASE}/exports/ledger.ofx`,
  dre: `${FINANCE_BASE}/exports/dre.csv`,
  livroCaixaCsv: `${FINANCE_BASE}/exports/livro-caixa.csv`,
  livroCaixaPdf: `${FINANCE_BASE}/exports/livro-caixa.pdf`,
  meiCsv: `${FINANCE_BASE}/exports/mei-monthly.csv`,
  meiPdf: `${FINANCE_BASE}/exports/mei-monthly.pdf`,
  dominio: `${FINANCE_BASE}/exports/dominio.txt`,
} as const;
