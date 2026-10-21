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
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { envelopeOps } from '../organ-kit/cacheOps';
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
  Settlement,
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

  /** For the mutations that cannot place their answer (see each `noc-allow`): refresh by key. */
  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
  }

  /** Insert-or-replace by id: the server's row lands where the cached list already has it, else at the end. */
  const upsert = <T extends { id: string }>(old: T[] | undefined, row: T): T[] | undefined => listOps.replace(old, row.id, row);

  /** Prefix of every cached entries LIST page (details and attachments share the `entries` family but not this). */
  const entriesLists = [...financeKeys.entries, 'list'] as const;
  const entryDetails = [...financeKeys.entries, 'detail'] as const;
  /** Prefix of every cached statement-lines page. */
  const statementLines = [...financeKeys.statements, 'lines'] as const;

  /** A detail object is the only non-array under the `detail` prefix whose `id` can match. */
  const isEntryDetail = (old: unknown, id: string): old is FinanceEntryDetail =>
    !!old && typeof old === 'object' && !Array.isArray(old) && (old as { id?: unknown }).id === id;

  /**
   * One server-answered entry goes into every cached list page that shows it AND the cached detail
   * (merged: the detail keeps its settlements/attachments). Whether a NEW entry belongs on a page of a
   * filtered / paged list is the server's call — creates and bulk imports are the only places that cannot
   * be placed (see their `noc-allow`).
   */
  const entryCommitTargets = <TData,>(pick: (r: TData) => FinanceEntry, settlementOf?: (r: TData) => Settlement) => [
    {
      queryKey: entriesLists,
      match: 'prefix' as const,
      commit: (old: any, r: TData) => {
        const e = pick(r);
        return envelopeOps.patch(old, e.id, e);
      },
    },
    {
      queryKey: entryDetails,
      match: 'prefix' as const,
      commit: (old: any, r: TData) => {
        const e = pick(r);
        if (!isEntryDetail(old, e.id)) return old;
        const st = settlementOf?.(r);
        return { ...old, ...e, ...(st ? { settlements: upsert(old.settlements, st) } : {}) };
      },
    },
  ];

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
    // Balances and reports are derived views: they refresh, the account lists are written.
    const derived = [['finance', 'balance'], financeKeys.reports] as QueryKey[];
    return {
      // The unfiltered list (`useAccounts()` with no params) gets the server's row; a list filtered by
      // `active` can't know whether it belongs, so it converges on the settle refetch.
      create: useCacheWriteMutation<FinanceAccount, AccountInput>({
        mutationFn: (b) => data<FinanceAccount>(api.post(p('/accounts'), b)),
        targets: [{ queryKey: [...financeKeys.accounts, {}], commit: (old: FinanceAccount[] | undefined, saved) => upsert(old, saved) }],
        invalidate: [financeKeys.accounts, ...derived],
      }),
      update: useCacheWriteMutation<FinanceAccount, AccountPatch & { id: string }>({
        mutationFn: ({ id, ...b }) => data<FinanceAccount>(api.patch(p(`/accounts/${id}`), b)),
        targets: ({ id }) => [
          { queryKey: financeKeys.accounts, match: 'prefix', commit: (old: FinanceAccount[] | undefined, saved) => listOps.patch(old, id, saved) },
        ],
        invalidate: derived,
      }),
      /** Hard delete: only an account nothing references; otherwise 409 `conta_em_uso` (deactivate instead). */
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(p(`/accounts/${id}`)),
        targets: (id) => [
          { queryKey: financeKeys.accounts, match: 'prefix', optimistic: (old: FinanceAccount[] | undefined) => listOps.remove(old, id) },
        ],
        invalidate: derived,
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
    const derived = [financeKeys.reports] as QueryKey[];
    return {
      create: useCacheWriteMutation<FinanceCategory, FinanceCategoryInput>({
        mutationFn: (b) => data<FinanceCategory>(api.post(p('/categories'), b)),
        targets: [{ queryKey: financeKeys.categories, commit: (old: FinanceCategory[] | undefined, saved) => upsert(old, saved) }],
        invalidate: derived,
      }),
      update: useCacheWriteMutation<FinanceCategory, FinanceCategoryPatch & { id: string }>({
        mutationFn: ({ id, ...b }) => data<FinanceCategory>(api.patch(p(`/categories/${id}`), b)),
        targets: ({ id }) => [
          { queryKey: financeKeys.categories, commit: (old: FinanceCategory[] | undefined, saved) => listOps.patch(old, id, saved) },
        ],
        invalidate: derived,
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(p(`/categories/${id}`)),
        targets: (id) => [
          { queryKey: financeKeys.categories, optimistic: (old: FinanceCategory[] | undefined) => listOps.remove(old, id) },
        ],
        invalidate: derived,
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
    return {
      create: useCacheWriteMutation<CostCenter, CostCenterInput>({
        mutationFn: (b) => data<CostCenter>(api.post(p('/cost-centers'), b)),
        targets: [{ queryKey: financeKeys.costCenters, commit: (old: CostCenter[] | undefined, saved) => upsert(old, saved) }],
      }),
      update: useCacheWriteMutation<CostCenter, CostCenterPatch & { id: string }>({
        mutationFn: ({ id, ...b }) => data<CostCenter>(api.patch(p(`/cost-centers/${id}`), b)),
        targets: ({ id }) => [
          { queryKey: financeKeys.costCenters, commit: (old: CostCenter[] | undefined, saved) => listOps.patch(old, id, saved) },
        ],
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
  /** Anything that changes money refreshes the derived views: balances, every report, the reconciliation. */
  const moneyDerived = [financeKeys.entries, ['finance', 'balance'], financeKeys.reports, financeKeys.statements] as QueryKey[];
  const settleTargets = entryCommitTargets<SettleResult>((r) => r.entry, (r) => r.settlement);
  function useEntryMutations() {
    const moneyDone = useMoneyInvalidate();
    return {
      /** Always answers a LIST (one element, or the whole installment group). */
      create: useMutation({ // noc-allow: invalidate-only — a new entry (or a whole installment group) lands on whichever page of whichever filtered / paged list the SERVER orders it into; the answer carries no list position
        mutationFn: (b: EntryInput) => data<FinanceEntry[]>(api.post(p('/entries'), b)),
        onSuccess: moneyDone,
      }),
      update: useCacheWriteMutation<FinanceEntry, EntryPatch & { id: string }>({
        mutationFn: ({ id, ...b }) => data<FinanceEntry>(api.patch(p(`/entries/${id}`), b)),
        targets: entryCommitTargets<FinanceEntry>((e) => e),
        invalidate: moneyDerived,
      }),
      cancel: useCacheWriteMutation<FinanceEntry, string>({
        mutationFn: (id) => data<FinanceEntry>(api.post(p(`/entries/${id}/cancel`), {})),
        targets: entryCommitTargets<FinanceEntry>((e) => e),
        invalidate: moneyDerived,
      }),
      /** Hard delete ("lançado por engano"): only when the detail says `deletable`; else 409 (cancel instead). */
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(p(`/entries/${id}`)),
        targets: (id) => [{ queryKey: entriesLists, match: 'prefix', optimistic: (old: any) => envelopeOps.remove(old, id) }],
        invalidate: moneyDerived,
      }),
      settle: useCacheWriteMutation<SettleResult, SettleInput & { id: string }>({
        mutationFn: ({ id, ...b }) => data<SettleResult>(api.post(p(`/entries/${id}/settlements`), b)),
        targets: settleTargets,
        invalidate: moneyDerived,
      }),
      reverse: useCacheWriteMutation<SettleResult, { settlementId: string; reason: string }>({
        mutationFn: ({ settlementId, reason }) =>
          data<SettleResult>(api.post(p(`/settlements/${settlementId}/reverse`), { reason })),
        targets: settleTargets,
        invalidate: moneyDerived,
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
    // The entry detail carries a trimmed attachments summary: it refreshes, the attachments list is written.
    const derived = [financeKeys.entry(entryId)] as QueryKey[];
    return {
      upload: useCacheWriteMutation<FinanceAttachment, File>({
        mutationFn: (file) => {
          const form = new FormData();
          form.append('file', file);
          return data<FinanceAttachment>(api.upload(p(`/entries/${entryId}/attachments`), form));
        },
        targets: [{ queryKey: financeKeys.attachments(entryId), commit: (old: FinanceAttachment[] | undefined, saved) => upsert(old, saved) }],
        invalidate: derived,
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (attachmentId) => api.delete(p(`/attachments/${attachmentId}`)),
        targets: (attachmentId) => [
          { queryKey: financeKeys.attachments(entryId), optimistic: (old: FinanceAttachment[] | undefined) => listOps.remove(old, attachmentId) },
        ],
        invalidate: derived,
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
    return {
      create: useCacheWriteMutation<Recurrence, RecurrenceInput>({
        mutationFn: (b) => data<Recurrence>(api.post(p('/recurrences'), b)),
        targets: [{ queryKey: financeKeys.recurrences, commit: (old: Recurrence[] | undefined, saved) => upsert(old, saved) }],
      }),
      update: useCacheWriteMutation<Recurrence, RecurrencePatchInput & { id: string }>({
        mutationFn: ({ id, ...b }) => data<Recurrence>(api.patch(p(`/recurrences/${id}`), b)),
        targets: ({ id }) => [
          { queryKey: financeKeys.recurrences, commit: (old: Recurrence[] | undefined, saved) => listOps.patch(old, id, saved) },
        ],
      }),
    };
  }
  function useTransfer() {
    const done = useMoneyInvalidate();
    return useMutation({ // noc-allow: invalidate-only — a transfer books two ledger rows and moves two balances; the answer is the transfer group, not a cached row, and balances / entries / reports are derived views
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
    // The answer IS the settings read; the DRE and the accountant checklist derive from it and refresh.
    const settingsKey = [...financeKeys.reports, 'dre-settings'] as QueryKey;
    const targets = [{ queryKey: settingsKey, commit: (_old: DreSettings | undefined, saved: DreSettings) => saved }];
    const derived = [financeKeys.reports];
    return {
      save: useCacheWriteMutation<DreSettings, DreSettingsInput>({
        mutationFn: (b) => data<DreSettings>(api.put(p('/dre-settings'), b)),
        targets,
        invalidate: derived,
      }),
      /** Confirm (or un-confirm) choices: the backend has no /confirm route, it is `PUT` with `confirmations`. */
      confirm: useCacheWriteMutation<DreSettings, DreConfirmInput>({
        mutationFn: ({ fields, note, confirmed = true }) =>
          data<DreSettings>(
            api.put(p('/dre-settings'), {
              confirmations: Object.fromEntries(fields.map((f) => [f, { confirmed, note: note ?? null }])),
            }),
          ),
        targets,
        invalidate: derived,
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
    // The budget report is a derived view (it refreshes); the budgets lists are keyed by period, so the
    // saved rows are merged into every cached period list that already holds that month.
    const derived = [financeKeys.reports];
    const budgetLists = [...financeKeys.reports, 'budgets'] as QueryKey;
    return {
      save: useCacheWriteMutation<Budget[], BudgetItemInput[]>({
        mutationFn: (items) => data<Budget[]>(api.put(p('/budgets'), { items })),
        targets: [
          {
            queryKey: budgetLists,
            match: 'prefix',
            commit: (old: Budget[] | undefined, saved) =>
              Array.isArray(old) ? saved.reduce<Budget[]>((acc, b) => (acc.some((x) => x.id === b.id) ? listOps.patch(acc, b.id, b)! : acc), old) : old,
          },
        ],
        invalidate: derived,
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(p(`/budgets/${id}`)),
        targets: (id) => [{ queryKey: budgetLists, match: 'prefix', optimistic: (old: Budget[] | undefined) => listOps.remove(old, id) }],
        invalidate: derived,
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
    const lineTarget = (pick: (r: any) => StatementLine) => ({
      queryKey: statementLines,
      match: 'prefix' as const,
      commit: (old: any, r: any) => {
        const l = pick(r);
        return envelopeOps.patch(old, l.id, l);
      },
    });
    return {
      importStatement: useMutation({ // noc-allow: invalidate-only — a statement import creates an import record plus N lines and suggestions the server computes; the answer is a count summary, not rows
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
      // The matched line and the entry it now settles come back: both land in the cached pages.
      match: useCacheWriteMutation<MatchResult, { lineId: string; entryId: string }>({
        mutationFn: ({ lineId, entryId }) =>
          data<MatchResult>(api.post(p(`/statement-lines/${lineId}/match`), { entry_id: entryId })),
        targets: [lineTarget((r: MatchResult) => r.line), ...entryCommitTargets<MatchResult>((r) => r.entry)],
        invalidate: moneyDerived,
      }),
      ignore: useCacheWriteMutation<StatementLine, string>({
        mutationFn: (lineId) => data<StatementLine>(api.post(p(`/statement-lines/${lineId}/ignore`), {})),
        targets: [lineTarget((l: StatementLine) => l)],
        invalidate: moneyDerived,
      }),
      gatewaySync: useMutation({ // noc-allow: invalidate-only — a gateway sync books fees / transfers in bulk and returns a review summary, not the booked rows
        mutationFn: ({ accountId, since }: { accountId: string; since?: string }) =>
          data<GatewaySyncResult>(api.post(p(`/accounts/${accountId}/gateway-sync`), since ? { since } : {})),
        onSuccess: done,
      }),
    };
  }

  // ---- exports (admin or the accountant read grant) ---------------------------------------------------
  function useExport() {
    return useMutation({ // noc-allow: invalidate-only — a file download: it reads and writes nothing any cached query shows
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
