/**
 * `createClientsHooks(api)` -- TanStack Query hooks for the clients API (`/api/clients`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read returns `showSkeleton =
 * isPending && !data` (first load only) and `isRefreshing`; the list and the agenda keep `placeholderData` across
 * filter / week changes. Personal reads keyed by id (client, its sessions, its finance) carry NO placeholderData:
 * it would show the previous person's data under the new id.
 *
 * 🔴 Writes (`KB § PATTERNS/frontend/mutation-cache-writes.md`): every mutation is a `useCacheWriteMutation` that
 * writes every entry it touches; what only the server can compute converges on the settle refetch:
 *   - session create / edit / delete: the session goes into (or out of) every cached session list it belongs to --
 *     the client's list AND every agenda week holding it -- drawn at once, the server's row committed. The client's
 *     summary and finance are server-derived (the booking is the server's), so they refresh in the background;
 *   - payment: the response carries the refreshed finance -> committed into the client's finance, its summary
 *     (detail + every list row) and the payment status of each of its cached sessions;
 *   - client create / edit / delete and schedules: the row lands in the lists / detail; a schedule regenerates
 *     sessions server-side, so the session family refreshes with it.
 */
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import type { ApiClient } from '../api';
import { infiniteOps, listOps, useCacheWriteMutation } from '../cache-writes';
import { financeKeys } from '../finance/hooks';
import type { FinanceAccount } from '../finance/types';
import { apiErrorCode, errorMessage, signals } from '../organ-kit/query';
import { clientsFilterQuery, paymentStatusOf } from './format';
import type {
  Client,
  ClientFiltersState,
  ClientFinance,
  ClientInput,
  ClientPatch,
  ClientsConfigData,
  ClientsEnvelope,
  ClientsPage,
  PaymentInput,
  PaymentResult,
  Schedule,
  ScheduleInput,
  SchedulePatch,
  Session,
  SessionInput,
  SessionPatch,
  SessionRange,
} from './types';

/** The subset of the seed `ApiClient` the clients hooks need. */
export type ClientsApi = Pick<ApiClient, 'get' | 'post' | 'patch' | 'delete'>;

export interface ClientsHooksOptions {
  /** Base path of the clients router (default `/api/clients`). */
  base?: string;
  /** Base path of the finance organ (its accounts feed the payment dialog; default `/api/finance`). */
  financeBase?: string;
}

export const clientsKeys = {
  all: ['clients'] as const,
  config: ['clients', 'config'] as const,
  tags: ['clients', 'tags'] as const,
  lists: ['clients', 'list'] as const,
  list: (f: ClientFiltersState) => ['clients', 'list', f] as const,
  byLead: (leadId: string) => ['clients', 'by-lead', leadId] as const,
  detail: (id: string) => ['clients', 'detail', id] as const,
  /** Every session list (a client's and every agenda week). */
  sessions: ['clients', 'sessions'] as const,
  clientSessions: (clientId: string, range: SessionRange = {}) => ['clients', 'sessions', 'client', clientId, range] as const,
  agenda: (from: string, to: string) => ['clients', 'sessions', 'range', from, to] as const,
  schedules: (clientId: string) => ['clients', 'schedules', clientId] as const,
  finance: (clientId: string) => ['clients', 'finance', clientId] as const,
};

export { apiErrorCode, errorMessage };

const byName = (a: Client, b: Client) => a.name.localeCompare(b.name, 'pt-BR');
const asc = (a: Session, b: Session) => a.starts_at.localeCompare(b.starts_at);
const desc = (a: Session, b: Session) => b.starts_at.localeCompare(a.starts_at);
const bySlot = (a: Schedule, b: Schedule) => a.weekday - b.weekday || a.time.localeCompare(b.time);
const isUnfiltered = (key: QueryKey) => Object.keys((key[2] as object | undefined) ?? {}).length === 0;

/** Does a session belong in the cached session list `key`? (client list: same client + its range / status filter; agenda: its week.) */
export function sessionBelongs(key: QueryKey, s: Session): boolean {
  const day = s.starts_at.slice(0, 10);
  if (key[2] === 'client') {
    const range = (key[4] as SessionRange | undefined) ?? {};
    return key[3] === s.client_id && (!range.status || range.status === s.status) && (!range.from || day >= range.from) && (!range.to || day <= range.to);
  }
  if (key[2] === 'range') return day >= String(key[3]) && day <= String(key[4]);
  return false;
}

/** The server's session goes where it belongs in the list `key` (sorted like the server), and out of where it no longer does. */
export function placeSession(old: Session[] | undefined, saved: Session, key: QueryKey): Session[] | undefined {
  if (!Array.isArray(old)) return old;
  if (!sessionBelongs(key, saved)) return listOps.remove(old, saved.id);
  return listOps.insertSorted(old, saved, key[2] === 'range' ? asc : desc);
}

/** The first page of an infinite client list, edited by `fn` (a new row's page is the server's call; settle converges). */
function onFirstPage(old: unknown, fn: (rows: Client[]) => Client[] | undefined) {
  return infiniteOps.mapPages(old, (p, i) => (i === 0 ? listOps.within(p as ClientsPage, 'data', fn) : p));
}

export function createClientsHooks(api: ClientsApi, options: ClientsHooksOptions = {}) {
  const BASE = options.base ?? '/api/clients';
  const FIN = options.financeBase ?? '/api/finance';
  const unwrap = async <T,>(p: Promise<ClientsEnvelope<T>>): Promise<T> => (await p).data;

  // ---- reads -------------------------------------------------------------
  function useClientsConfig() {
    const q = useQuery<ClientsConfigData>({
      queryKey: clientsKeys.config,
      queryFn: () => unwrap<ClientsConfigData>(api.get(`${BASE}/config`)),
      staleTime: 5 * 60_000,
    });
    return signals(q);
  }

  function useClientTags() {
    const q = useQuery<string[]>({ queryKey: clientsKeys.tags, queryFn: () => unwrap<string[]>(api.get(`${BASE}/tags`)), placeholderData: keepPreviousData });
    return signals(q);
  }

  function useClientsList(filters: ClientFiltersState = {}, pageSize = 50) {
    const q = useInfiniteQuery<ClientsPage, Error, { pages: ClientsPage[] }, readonly unknown[], string | null>({
      queryKey: clientsKeys.list(filters),
      initialPageParam: null,
      queryFn: ({ pageParam }) =>
        api.get<ClientsPage>(BASE, { ...clientsFilterQuery(filters), limit: pageSize, ...(pageParam ? { cursor: pageParam } : {}) }),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
      placeholderData: keepPreviousData,
    });
    const rows = q.data?.pages.flatMap((p) => p.data) ?? [];
    return {
      ...signals(q as any),
      data: q.data ? rows : undefined,
      hasNextPage: q.hasNextPage,
      isFetchingNextPage: q.isFetchingNextPage,
      fetchNextPage: q.fetchNextPage,
    };
  }

  /** The client converted from a lead (`GET ?lead_id=`): `null` = none (yet). */
  function useClientByLead(leadId: string | null | undefined) {
    const q = useQuery<Client | null>({
      queryKey: clientsKeys.byLead(leadId ?? ''),
      queryFn: async () => (await api.get<ClientsPage>(BASE, { lead_id: leadId, limit: 1 })).data[0] ?? null,
      enabled: !!leadId,
    });
    return signals(q);
  }

  function useClient(id: string | null | undefined) {
    const q = useQuery<Client>({ queryKey: clientsKeys.detail(id ?? ''), queryFn: () => unwrap<Client>(api.get(`${BASE}/${id}`)), enabled: !!id });
    return signals(q);
  }

  /** A client's sessions, newest first (optional `from` / `to` / `status`). */
  function useClientSessions(clientId: string | null | undefined, range: SessionRange = {}) {
    const q = useQuery<Session[]>({
      queryKey: clientsKeys.clientSessions(clientId ?? '', range),
      queryFn: () => unwrap<Session[]>(api.get(`${BASE}/${clientId}/sessions`, { ...range })),
      enabled: !!clientId,
    });
    return signals(q);
  }

  /** Every client's sessions in `[from, to]` (dates, inclusive), oldest first -- the agenda. */
  function useAgendaSessions(from: string, to: string) {
    const q = useQuery<Session[]>({
      queryKey: clientsKeys.agenda(from, to),
      queryFn: () => unwrap<Session[]>(api.get(`${BASE}/sessions`, { from, to })),
      placeholderData: keepPreviousData,
    });
    return signals(q);
  }

  function useSchedules(clientId: string | null | undefined) {
    const q = useQuery<Schedule[]>({
      queryKey: clientsKeys.schedules(clientId ?? ''),
      queryFn: () => unwrap<Schedule[]>(api.get(`${BASE}/${clientId}/schedules`)),
      enabled: !!clientId,
    });
    return signals(q);
  }

  function useClientFinance(clientId: string | null | undefined, enabled = true) {
    const q = useQuery<ClientFinance>({
      queryKey: clientsKeys.finance(clientId ?? ''),
      queryFn: () => unwrap<ClientFinance>(api.get(`${BASE}/${clientId}/finance`)),
      enabled: !!clientId && enabled,
    });
    return signals(q);
  }

  /** The finance organ's active accounts (same cache entry as `createFinanceHooks().useAccounts({ active: true })`). */
  function useFinanceAccounts(enabled = true) {
    const q = useQuery<FinanceAccount[]>({
      queryKey: [...financeKeys.accounts, { active: true }],
      queryFn: () => unwrap<FinanceAccount[]>(api.get(`${FIN}/accounts`, { active: true })),
      enabled,
      staleTime: 60_000,
    });
    return signals(q);
  }

  // ---- client writes -----------------------------------------------------
  /** What a client edit makes stale beyond its own row: tags, the lead lookup, agenda chips (name). */
  const clientDerived: QueryKey[] = [clientsKeys.tags, ['clients', 'by-lead'], clientsKeys.sessions];

  function useCreateClient() {
    const qc = useQueryClient();
    return useCacheWriteMutation<Client, ClientInput>({
      mutationFn: (body) => unwrap<Client>(api.post(BASE, body)),
      targets: [
        { queryKey: clientsKeys.lists, match: 'prefix', predicate: isUnfiltered, commit: (old, saved) => onFirstPage(old, (rows) => listOps.insertSorted(rows, saved, byName)) },
      ],
      invalidate: [clientsKeys.tags],
      onSuccess: (saved) => {
        qc.setQueryData(clientsKeys.detail(saved.id), saved);
      },
    });
  }

  function useUpdateClient() {
    return useCacheWriteMutation<Client, { id: string } & ClientPatch>({
      mutationFn: ({ id, ...body }) => unwrap<Client>(api.patch(`${BASE}/${id}`, body)),
      targets: ({ id, ...changes }) => [
        {
          queryKey: clientsKeys.lists,
          match: 'prefix',
          optimistic: (old: unknown) => infiniteOps.patch(old, id, changes),
          commit: (old: unknown, saved: Client) => infiniteOps.replace(old, id, saved),
        },
        {
          queryKey: clientsKeys.detail(id),
          optimistic: (old: Client | undefined) => listOps.merge(old, changes),
          commit: (old: Client | undefined, saved: Client) => (old === undefined ? undefined : saved),
        },
      ],
      invalidate: clientDerived,
    });
  }

  function useDeleteClient() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/${id}`),
      targets: (id) => [
        { queryKey: clientsKeys.lists, match: 'prefix', optimistic: (old: unknown) => infiniteOps.remove(old, id) },
        { queryKey: clientsKeys.sessions, match: 'prefix', optimistic: (old: unknown) => (Array.isArray(old) ? (old as Session[]).filter((s) => s.client_id !== id) : old) },
        { queryKey: clientsKeys.detail(id) },
      ],
      invalidate: [clientsKeys.tags, ['clients', 'by-lead']],
    });
  }

  // ---- session writes ----------------------------------------------------
  /** A session write changes the client's server-derived summary + finance: they refresh with it. */
  const sessionDerived = (clientId: string): QueryKey[] => [clientsKeys.detail(clientId), clientsKeys.finance(clientId), clientsKeys.lists];

  function useCreateSession() {
    return useCacheWriteMutation<Session, { clientId: string } & SessionInput>({
      mutationFn: ({ clientId, ...body }) => unwrap<Session>(api.post(`${BASE}/${clientId}/sessions`, body)),
      targets: [{ queryKey: clientsKeys.sessions, match: 'prefix', commit: (old: Session[] | undefined, saved: Session, _v, _c, key) => placeSession(old, saved, key!) }],
      invalidate: ({ clientId }) => sessionDerived(clientId),
    });
  }

  /** `client_id` addresses the client's derived caches; it is not sent. */
  function useUpdateSession() {
    return useCacheWriteMutation<Session, { id: string; client_id: string } & SessionPatch>({
      mutationFn: ({ id, client_id: _c, ...body }) => unwrap<Session>(api.patch(`${BASE}/sessions/${id}`, body)),
      targets: ({ id, client_id: _c, ...changes }) => [
        {
          queryKey: clientsKeys.sessions,
          match: 'prefix',
          optimistic: (old: Session[] | undefined) => listOps.patch(old, id, changes),
          commit: (old: Session[] | undefined, saved: Session, _v, _c2, key) => placeSession(old, saved, key!),
        },
      ],
      invalidate: ({ client_id }) => sessionDerived(client_id),
    });
  }

  function useDeleteSession() {
    return useCacheWriteMutation<unknown, { id: string; client_id: string }>({
      mutationFn: ({ id }) => api.delete(`${BASE}/sessions/${id}`),
      targets: ({ id }) => [{ queryKey: clientsKeys.sessions, match: 'prefix', optimistic: (old: Session[] | undefined) => listOps.remove(old, id) }],
      invalidate: ({ client_id }) => sessionDerived(client_id),
    });
  }

  // ---- schedule writes (each regenerates future sessions server-side) -----
  const scheduleDerived = (clientId: string): QueryKey[] => [clientsKeys.sessions, ...sessionDerived(clientId)];

  function useCreateSchedule() {
    return useCacheWriteMutation<Schedule, { clientId: string } & ScheduleInput>({
      mutationFn: ({ clientId, ...body }) => unwrap<Schedule>(api.post(`${BASE}/${clientId}/schedules`, body)),
      targets: ({ clientId }) => [{ queryKey: clientsKeys.schedules(clientId), commit: (old: Schedule[] | undefined, saved: Schedule) => listOps.insertSorted(old, saved, bySlot) }],
      invalidate: ({ clientId }) => scheduleDerived(clientId),
    });
  }

  function useUpdateSchedule() {
    return useCacheWriteMutation<Schedule, { id: string; client_id: string } & SchedulePatch>({
      mutationFn: ({ id, client_id: _c, ...body }) => unwrap<Schedule>(api.patch(`${BASE}/schedules/${id}`, body)),
      targets: ({ id, client_id, ...changes }) => [
        {
          queryKey: clientsKeys.schedules(client_id),
          optimistic: (old: Schedule[] | undefined) => listOps.patch(old, id, changes),
          commit: (old: Schedule[] | undefined, saved: Schedule) => listOps.insertSorted(old, saved, bySlot),
        },
      ],
      invalidate: ({ client_id }) => scheduleDerived(client_id),
    });
  }

  function useDeleteSchedule() {
    return useCacheWriteMutation<unknown, { id: string; client_id: string }>({
      mutationFn: ({ id }) => api.delete(`${BASE}/schedules/${id}`),
      targets: ({ id, client_id }) => [{ queryKey: clientsKeys.schedules(client_id), optimistic: (old: Schedule[] | undefined) => listOps.remove(old, id) }],
      invalidate: ({ client_id }) => scheduleDerived(client_id),
    });
  }

  // ---- payment -----------------------------------------------------------
  /** The finance the server answered, into every place that shows it. */
  function useRegisterPayment() {
    return useCacheWriteMutation<PaymentResult, { clientId: string } & PaymentInput>({
      mutationFn: ({ clientId, ...body }) => unwrap<PaymentResult>(api.post(`${BASE}/${clientId}/payments`, body)),
      targets: ({ clientId }) => {
        const totals = (f: ClientFinance) => ({ open_cents: f.open_cents, overdue_cents: f.overdue_cents, paid_cents: f.paid_cents });
        const withSummary = (c: Client, f: ClientFinance): Client => ({ ...c, summary: { ...c.summary, ...totals(f) } });
        return [
          { queryKey: clientsKeys.finance(clientId), commit: (_old: ClientFinance | undefined, r: PaymentResult) => r.finance },
          { queryKey: clientsKeys.detail(clientId), commit: (old: Client | undefined, r: PaymentResult) => (old ? withSummary(old, r.finance) : old) },
          {
            queryKey: clientsKeys.lists,
            match: 'prefix',
            commit: (old: unknown, r: PaymentResult) => infiniteOps.mapPages(old, (p) => listOps.within(p as ClientsPage, 'data', (rows) => listOps.update(rows, clientId, (c) => withSummary(c, r.finance)))),
          },
          {
            queryKey: clientsKeys.sessions,
            match: 'prefix',
            commit: (old: Session[] | undefined, r: PaymentResult) => {
              if (!Array.isArray(old)) return old;
              const bySession = new Map(r.finance.entries.filter((e) => e.session_id).map((e) => [e.session_id as string, e]));
              return old.map((s) => (s.client_id === clientId && bySession.has(s.id) ? { ...s, payment_status: paymentStatusOf(bySession.get(s.id)) } : s));
            },
          },
        ];
      },
      // The finance organ's own views (receivables, cash flow, DRE) moved too.
      invalidate: [financeKeys.all],
    });
  }

  return {
    useClientsConfig,
    useClientTags,
    useClientsList,
    useClientByLead,
    useClient,
    useClientSessions,
    useAgendaSessions,
    useSchedules,
    useClientFinance,
    useFinanceAccounts,
    useCreateClient,
    useUpdateClient,
    useDeleteClient,
    useCreateSession,
    useUpdateSession,
    useDeleteSession,
    useCreateSchedule,
    useUpdateSchedule,
    useDeleteSchedule,
    useRegisterPayment,
  };
}

export type ClientsHooks = ReturnType<typeof createClientsHooks>;
