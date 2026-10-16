/**
 * `createFinanceReminderHooks(apiBase | api)` — TanStack Query hooks for the billing-reminders API
 * (`/api/finance/reminders`). Same contract as `createFinanceHooks`: read hooks return `showSkeleton = isPending && !data`
 * and `isRefreshing = isFetching && !!data` (never `isLoading`); the paged log keeps `placeholderData`; mutations
 * reject with `ApiError` so the caller renders the server's pt-BR message.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createFetchTransport, keep, signals, type OrganApi } from '../organ-kit/query';
import type {
  ReminderLogRow,
  ReminderLogStatus,
  ReminderPreview,
  ReminderRule,
  ReminderRuleInput,
  ReminderRulePatch,
  ReminderSettings,
} from './reminderTypes';
import type { FinancePaginated } from './types';

export const REMINDERS_BASE = '/api/finance/reminders';

export const reminderKeys = {
  all: ['finance', 'reminders'] as const,
  settings: ['finance', 'reminders', 'settings'] as const,
  rules: ['finance', 'reminders', 'rules'] as const,
  log: ['finance', 'reminders', 'log'] as const,
  preview: ['finance', 'reminders', 'preview'] as const,
};

export interface ReminderLogParams {
  status?: ReminderLogStatus | '';
  page?: number;
  page_size?: number;
}

export function createFinanceReminderHooks(apiOrBase: string | OrganApi) {
  const api: OrganApi = typeof apiOrBase === 'string' ? createFetchTransport(apiOrBase) : apiOrBase;
  const p = (path: string) => `${REMINDERS_BASE}${path}`;
  const data = async <T,>(promise: Promise<{ data: T }>): Promise<T> => (await promise).data;

  function useReminderSettings() {
    return signals(useQuery<ReminderSettings>({ queryKey: reminderKeys.settings, queryFn: () => data(api.get(p('/settings'))) }));
  }
  function useSaveReminderSettings() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (b: { enabled?: boolean; timezone?: string }) => data<ReminderSettings>(api.put(p('/settings'), b)),
      // Enabling for the first time seeds the default rules, and flips what the preview returns.
      onSuccess: () => qc.invalidateQueries({ queryKey: reminderKeys.all }),
    });
  }

  function useReminderRules() {
    return signals(useQuery<ReminderRule[]>({ queryKey: reminderKeys.rules, queryFn: () => data(api.get(p('/rules'))) }));
  }
  function useReminderRuleMutations() {
    const qc = useQueryClient();
    const done = () => Promise.all([qc.invalidateQueries({ queryKey: reminderKeys.rules }), qc.invalidateQueries({ queryKey: reminderKeys.preview })]);
    return {
      create: useMutation({ mutationFn: (b: ReminderRuleInput) => data<ReminderRule>(api.post(p('/rules'), b)), onSuccess: done }),
      update: useMutation({
        mutationFn: ({ id, ...b }: ReminderRulePatch & { id: string }) => data<ReminderRule>(api.patch(p(`/rules/${id}`), b)),
        onSuccess: done,
      }),
      remove: useMutation({ mutationFn: (id: string) => api.delete(p(`/rules/${id}`)), onSuccess: done }),
      addDefaults: useMutation({ mutationFn: () => data<ReminderRule[]>(api.post(p('/rules/defaults'))), onSuccess: done }),
    };
  }

  function useReminderLog(params: ReminderLogParams = {}) {
    return signals(
      useQuery<FinancePaginated<ReminderLogRow>>({
        queryKey: [...reminderKeys.log, params],
        queryFn: () => api.get(p('/log'), { ...params }),
        placeholderData: keep,
      }),
    );
  }

  function useReminderPreview(on?: string) {
    return signals(
      useQuery<ReminderPreview>({
        queryKey: [...reminderKeys.preview, on ?? 'today'],
        queryFn: () => data(api.get(p('/preview'), on ? { on } : undefined)),
        placeholderData: keep,
      }),
    );
  }

  function useReceivableOptOut() {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: ({ entryId, optOut }: { entryId: string; optOut: boolean }) =>
        data<{ entry_id: string; reminders_opt_out: boolean }>(api.put(p(`/receivables/${entryId}/opt-out`), { opt_out: optOut })),
      onSuccess: () => qc.invalidateQueries({ queryKey: reminderKeys.preview }),
    });
  }

  return {
    useReminderSettings,
    useSaveReminderSettings,
    useReminderRules,
    useReminderRuleMutations,
    useReminderLog,
    useReminderPreview,
    useReceivableOptOut,
  };
}

export type FinanceReminderHooks = ReturnType<typeof createFinanceReminderHooks>;
