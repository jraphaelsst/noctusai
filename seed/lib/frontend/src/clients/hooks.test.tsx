import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api';
import { financeKeys } from '../finance/hooks';
import { clientsKeys, createClientsHooks } from './hooks';
import { client, CONFIG, deferred, env, finance, makeApi, makeClient, schedule, session, wrapperFor } from './testUtils';
import type { Client, ClientFinance, Schedule, Session } from './types';

const ana = client({ id: 'c1', name: 'Ana' });
const bia = client({ id: 'c2', name: 'Bia' });
const page = (...rows: Client[]) => ({ pages: [{ data: rows, next_cursor: null }], pageParams: [null] });
const listRows = (qc: ReturnType<typeof makeClient>, f = {}) =>
  (qc.getQueryData<{ pages: { data: Client[] }[] }>(clientsKeys.list(f))?.pages ?? []).flatMap((p) => p.data);

describe('read hooks', () => {
  it('config is data from the server', async () => {
    const { result } = renderHook(() => createClientsHooks(makeApi()).useClientsConfig(), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual(CONFIG));
  });

  it('list: filters and cursor go to the server; pages flatten', async () => {
    const api = makeApi({ 'GET /api/clients': (_p: string, params?: any) => (params?.cursor ? { data: [bia], next_cursor: null } : { data: [ana], next_cursor: 'n1' }) });
    const { result } = renderHook(() => createClientsHooks(api).useClientsList({ status: 'ativo', tag: 'vip' }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(api.get).toHaveBeenCalledWith('/api/clients', { status: 'ativo', tag: 'vip', limit: 50 });
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.data!.map((c) => c.id)).toEqual(['c1', 'c2']));
  });

  it('by-lead resolves the converted client (or null)', async () => {
    const api = makeApi({ 'GET /api/clients': (_p: string, params?: any) => ({ data: params?.lead_id === 'l1' ? [ana] : [], next_cursor: null }) });
    const hooks = createClientsHooks(api);
    const { result, rerender } = renderHook(({ id }) => hooks.useClientByLead(id), { wrapper: wrapperFor(), initialProps: { id: 'l1' } });
    await waitFor(() => expect(result.current.data?.id).toBe('c1'));
    expect(api.get).toHaveBeenCalledWith('/api/clients', { lead_id: 'l1', limit: 1 });
    rerender({ id: 'l2' });
    await waitFor(() => expect(result.current.data).toBeNull());
  });

  it('agenda: one range per week; the previous week stays on screen while the next loads', async () => {
    const d = deferred<any>();
    const api = makeApi({ 'GET /api/clients/sessions': (_p: string, params?: any) => (params.from === '2026-11-09' ? d.promise : env([session()])) });
    const hooks = createClientsHooks(api);
    const { result, rerender } = renderHook(({ from, to }) => hooks.useAgendaSessions(from, to), {
      wrapper: wrapperFor(),
      initialProps: { from: '2026-11-02', to: '2026-11-08' },
    });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    rerender({ from: '2026-11-09', to: '2026-11-15' });
    expect(result.current.data).toHaveLength(1);
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).toHaveBeenCalledWith('/api/clients/sessions', { from: '2026-11-09', to: '2026-11-15' });
  });

  it('finance accounts share the finance organ cache entry', async () => {
    const qc = makeClient();
    const api = makeApi({ 'GET /api/finance/accounts': env([{ id: 'a1', name: 'Caixa' }]) });
    const { result } = renderHook(() => createClientsHooks(api).useFinanceAccounts(), { wrapper: wrapperFor(qc) });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(qc.getQueryData([...financeKeys.accounts, { active: true }])).toEqual([{ id: 'a1', name: 'Caixa' }]);
  });
});

describe('session writes', () => {
  function seeded() {
    const qc = makeClient();
    const s1 = session({ id: 's1', starts_at: '2026-11-03T14:00:00-03:00' });
    const s0 = session({ id: 's0', starts_at: '2026-10-27T14:00:00-03:00', status: 'realizada' });
    qc.setQueryData(clientsKeys.clientSessions('c1'), [s1, s0]);
    qc.setQueryData(clientsKeys.agenda('2026-11-02', '2026-11-08'), [s1]);
    qc.setQueryData(clientsKeys.agenda('2026-11-09', '2026-11-15'), []);
    qc.setQueryData(clientsKeys.detail('c1'), ana);
    qc.setQueryData(clientsKeys.finance('c1'), finance());
    return { qc, s1, s0 };
  }

  it('a status change is drawn at once in the client list AND the agenda; the server row is committed; summary + finance refresh', async () => {
    const { qc, s1 } = seeded();
    const d = deferred<any>();
    const api = makeApi({ 'PATCH /api/clients/sessions/s1': () => d.promise });
    const { result } = renderHook(() => createClientsHooks(api).useUpdateSession(), { wrapper: wrapperFor(qc) });
    act(() => result.current.mutate({ id: 's1', client_id: 'c1', status: 'realizada' }));
    await waitFor(() => expect(qc.getQueryData<Session[]>(clientsKeys.clientSessions('c1'))![0].status).toBe('realizada'));
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))![0].status).toBe('realizada');
    expect(api.patch).toHaveBeenCalledWith('/api/clients/sessions/s1', { status: 'realizada' }); // client_id is not sent
    await act(async () => d.resolve(env({ ...s1, status: 'realizada', entry_id: 'e1', payment_status: 'open' })));
    await waitFor(() => expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))![0].payment_status).toBe('open'));
    expect(qc.getQueryState(clientsKeys.finance('c1'))!.isInvalidated).toBe(true);
    expect(qc.getQueryState(clientsKeys.detail('c1'))!.isInvalidated).toBe(true);
  });

  it('a refused change rolls back everywhere', async () => {
    const { qc } = seeded();
    const api = makeApi({ 'PATCH /api/clients/sessions/s1': () => Promise.reject(new ApiError(409, 'x', { error: { code: 'SESSAO_COM_PAGAMENTO' } })) });
    const { result } = renderHook(() => createClientsHooks(api).useUpdateSession(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ id: 's1', client_id: 'c1', status: 'cancelada' }).catch(() => undefined);
    });
    expect(qc.getQueryData<Session[]>(clientsKeys.clientSessions('c1'))![0].status).toBe('agendada');
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))![0].status).toBe('agendada');
  });

  it('moving a session to another week takes it out of the old week and into the new one', async () => {
    const { qc, s1 } = seeded();
    const moved = { ...s1, starts_at: '2026-11-10T14:00:00-03:00' };
    const api = makeApi({ 'PATCH /api/clients/sessions/s1': env(moved) });
    const { result } = renderHook(() => createClientsHooks(api).useUpdateSession(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ id: 's1', client_id: 'c1', starts_at: moved.starts_at });
    });
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))).toEqual([]);
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-09', '2026-11-15'))!.map((s) => s.id)).toEqual(['s1']);
  });

  it('create places the session newest-first in the client list and into its agenda week only', async () => {
    const { qc } = seeded();
    const created = session({ id: 's2', starts_at: '2026-11-05T10:00:00-03:00' });
    const api = makeApi({ 'POST /api/clients/c1/sessions': env(created) });
    const { result } = renderHook(() => createClientsHooks(api).useCreateSession(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ clientId: 'c1', starts_at: created.starts_at });
    });
    expect(api.post).toHaveBeenCalledWith('/api/clients/c1/sessions', { starts_at: created.starts_at });
    expect(qc.getQueryData<Session[]>(clientsKeys.clientSessions('c1'))!.map((s) => s.id)).toEqual(['s2', 's1', 's0']);
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))!.map((s) => s.id)).toEqual(['s1', 's2']);
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-09', '2026-11-15'))).toEqual([]);
  });

  it('delete removes the session on the click', async () => {
    const { qc } = seeded();
    const d = deferred<any>();
    const api = makeApi({ 'DELETE /api/clients/sessions/s1': () => d.promise });
    const { result } = renderHook(() => createClientsHooks(api).useDeleteSession(), { wrapper: wrapperFor(qc) });
    act(() => result.current.mutate({ id: 's1', client_id: 'c1' }));
    await waitFor(() => expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))).toEqual([]));
    expect(qc.getQueryData<Session[]>(clientsKeys.clientSessions('c1'))!.map((s) => s.id)).toEqual(['s0']);
  });
});

describe('payment', () => {
  it('commits the returned finance into the finance, the summary (detail + list) and the session payment chips', async () => {
    const qc = makeClient();
    const s1 = session({ id: 's1', status: 'realizada', entry_id: 'e1', payment_status: 'open' });
    qc.setQueryData(clientsKeys.clientSessions('c1'), [s1]);
    qc.setQueryData(clientsKeys.agenda('2026-11-02', '2026-11-08'), [s1]);
    qc.setQueryData(clientsKeys.detail('c1'), client({ summary: { ...ana.summary, open_cents: 20000 } }));
    qc.setQueryData(clientsKeys.list({}), page(client({ summary: { ...ana.summary, open_cents: 20000 } }), bia));
    const after: ClientFinance = finance({
      open_cents: 0,
      paid_cents: 20000,
      entries: [{ entry_id: 'e1', session_id: 's1', description: 'Sessão', amount_cents: 20000, settled_cents: 20000, due_date: '2026-11-03', status: 'paid', overdue: false }],
    });
    const api = makeApi({ 'POST /api/clients/c1/payments': env({ settlement_ids: ['st1'], finance: after }) });
    const { result } = renderHook(() => createClientsHooks(api).useRegisterPayment(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ clientId: 'c1', amount_cents: 20000, paid_on: '2026-11-03', account_id: 'a1', method: 'pix' });
    });
    expect(api.post).toHaveBeenCalledWith('/api/clients/c1/payments', { amount_cents: 20000, paid_on: '2026-11-03', account_id: 'a1', method: 'pix' });
    expect(qc.getQueryData(clientsKeys.finance('c1'))).toEqual(after);
    expect(qc.getQueryData<Client>(clientsKeys.detail('c1'))!.summary).toMatchObject({ open_cents: 0, paid_cents: 20000 });
    expect(listRows(qc)[0].summary).toMatchObject({ open_cents: 0, paid_cents: 20000 });
    expect(listRows(qc)[1].summary.paid_cents).toBe(0);
    expect(qc.getQueryData<Session[]>(clientsKeys.clientSessions('c1'))![0].payment_status).toBe('paid');
    expect(qc.getQueryData<Session[]>(clientsKeys.agenda('2026-11-02', '2026-11-08'))![0].payment_status).toBe('paid');
  });
});

describe('client + schedule writes', () => {
  it('create lands in the unfiltered list in name order (not in a filtered one) and seeds the detail', async () => {
    const qc = makeClient();
    qc.setQueryData(clientsKeys.list({}), page(ana, client({ id: 'c3', name: 'Carla' })));
    qc.setQueryData(clientsKeys.list({ tag: 'vip' }), page(ana));
    const api = makeApi({ 'POST /api/clients': env(bia) });
    const { result } = renderHook(() => createClientsHooks(api).useCreateClient(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ name: 'Bia' });
    });
    expect(listRows(qc).map((c) => c.name)).toEqual(['Ana', 'Bia', 'Carla']);
    expect(listRows(qc, { tag: 'vip' }).map((c) => c.name)).toEqual(['Ana']);
    expect(qc.getQueryData(clientsKeys.detail('c2'))).toEqual(bia);
  });

  it('update draws the change in the list and the detail, then commits the server row', async () => {
    const qc = makeClient();
    qc.setQueryData(clientsKeys.list({}), page(ana));
    qc.setQueryData(clientsKeys.detail('c1'), ana);
    const d = deferred<any>();
    const api = makeApi({ 'PATCH /api/clients/c1': () => d.promise });
    const { result } = renderHook(() => createClientsHooks(api).useUpdateClient(), { wrapper: wrapperFor(qc) });
    act(() => result.current.mutate({ id: 'c1', status: 'encerrado' }));
    await waitFor(() => expect(listRows(qc)[0].status).toBe('encerrado'));
    expect(qc.getQueryData<Client>(clientsKeys.detail('c1'))!.status).toBe('encerrado');
    await act(async () => d.resolve(env({ ...ana, status: 'encerrado', phone: '+5511900000000' })));
    await waitFor(() => expect(qc.getQueryData<Client>(clientsKeys.detail('c1'))!.phone).toBe('+5511900000000'));
  });

  it('delete removes the client from every list on the click', async () => {
    const qc = makeClient();
    qc.setQueryData(clientsKeys.list({}), page(ana, bia));
    const d = deferred<any>();
    const api = makeApi({ 'DELETE /api/clients/c1': () => d.promise });
    const { result } = renderHook(() => createClientsHooks(api).useDeleteClient(), { wrapper: wrapperFor(qc) });
    act(() => result.current.mutate('c1'));
    await waitFor(() => expect(listRows(qc).map((c) => c.id)).toEqual(['c2']));
  });

  it('schedule create lands in slot order and regenerates the sessions', async () => {
    const qc = makeClient();
    qc.setQueryData(clientsKeys.schedules('c1'), [schedule({ id: 'h1', weekday: 3 })]);
    qc.setQueryData(clientsKeys.clientSessions('c1'), []);
    const api = makeApi({ 'POST /api/clients/c1/schedules': env(schedule({ id: 'h2', weekday: 0, time: '09:00' })) });
    const { result } = renderHook(() => createClientsHooks(api).useCreateSchedule(), { wrapper: wrapperFor(qc) });
    await act(async () => {
      await result.current.mutateAsync({ clientId: 'c1', weekday: 0, time: '09:00' });
    });
    expect(qc.getQueryData<Schedule[]>(clientsKeys.schedules('c1'))!.map((s) => s.id)).toEqual(['h2', 'h1']);
    expect(qc.getQueryState(clientsKeys.clientSessions('c1'))!.isInvalidated).toBe(true);
  });

  it('pausing a slot is drawn at once', async () => {
    const qc = makeClient();
    qc.setQueryData(clientsKeys.schedules('c1'), [schedule()]);
    const d = deferred<any>();
    const api = makeApi({ 'PATCH /api/clients/schedules/h1': () => d.promise });
    const { result } = renderHook(() => createClientsHooks(api).useUpdateSchedule(), { wrapper: wrapperFor(qc) });
    act(() => result.current.mutate({ id: 'h1', client_id: 'c1', active: false }));
    await waitFor(() => expect(qc.getQueryData<Schedule[]>(clientsKeys.schedules('c1'))![0].active).toBe(false));
    expect(api.patch).toHaveBeenCalledWith('/api/clients/schedules/h1', { active: false });
  });
});
