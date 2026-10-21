/**
 * `createFinanceReminderHooks(apiBase | api)` — TanStack Query hooks for the billing-reminders API
 * (`/api/finance/reminders`). Same contract as `createFinanceHooks`: read hooks return `showSkeleton = isPending && !data`
 * and `isRefreshing = isFetching && !!data` (never `isLoading`); the paged log keeps `placeholderData`; mutations
 * reject with `ApiError` so the caller renders the server's pt-BR message.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
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
    return useCacheWriteMutation<ReminderSettings, { enabled?: boolean; timezone?: string }>({
      mutationFn: (b) => data<ReminderSettings>(api.put(p('/settings'), b)),
      // The answer IS the settings read. Enabling for the first time also seeds the default rules and
      // flips what the preview returns: those are server-derived, so the whole family settles.
      targets: [{ queryKey: reminderKeys.settings, commit: (_old: ReminderSettings | undefined, saved) => saved }],
      invalidate: [reminderKeys.all],
    });
  }

  function useReminderRules() {
    return signals(useQuery<ReminderRule[]>({ queryKey: reminderKeys.rules, queryFn: () => data(api.get(p('/rules'))) }));
  }
  function useReminderRuleMutations() {
    // The preview (who would be reminded) derives from the rules: it refreshes, the rules list is written.
    const derived = [reminderKeys.preview];
    return {
      create: useCacheWriteMutation<ReminderRule, ReminderRuleInput>({
        mutationFn: (b) => data<ReminderRule>(api.post(p('/rules'), b)),
        targets: [{ queryKey: reminderKeys.rules, commit: (old: ReminderRule[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
        invalidate: derived,
      }),
      update: useCacheWriteMutation<ReminderRule, ReminderRulePatch & { id: string }>({
        mutationFn: ({ id, ...b }) => data<ReminderRule>(api.patch(p(`/rules/${id}`), b)),
        targets: ({ id }) => [
          { queryKey: reminderKeys.rules, commit: (old: ReminderRule[] | undefined, saved) => listOps.patch(old, id, saved) },
        ],
        invalidate: derived,
      }),
      remove: useCacheWriteMutation<void, string>({
        mutationFn: async (id) => {
          await api.delete(p(`/rules/${id}`));
        },
        targets: (id) => [
          { queryKey: reminderKeys.rules, optimistic: (old: ReminderRule[] | undefined) => listOps.remove(old, id) },
        ],
        invalidate: derived,
      }),
      // The server seeds whichever defaults are missing and answers with the rules it created.
      addDefaults: useCacheWriteMutation<ReminderRule[], void>({
        mutationFn: () => data<ReminderRule[]>(api.post(p('/rules/defaults'))),
        targets: [
          {
            queryKey: reminderKeys.rules,
            commit: (old: ReminderRule[] | undefined, created) =>
              Array.isArray(old) ? created.reduce<ReminderRule[]>((acc, r) => listOps.replace(acc, r.id, r) ?? acc, old) : old,
          },
        ],
        invalidate: derived,
      }),
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
    return useMutation({ // noc-allow: invalidate-only — the preview is a server-computed view of who would be reminded; the answer is just the opt-out flag, not a row of that view
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
