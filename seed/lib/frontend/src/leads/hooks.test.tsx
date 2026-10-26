import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api';
import { createLeadsHooks, leadsKeys } from './hooks';
import { board, CONFIG, deferred, env, lead, makeApi, makeClient, wrapperFor } from './testUtils';
import type { Lead, LeadColumn } from './types';

const a = lead({ id: 'a', name: 'A', stage: 'lead' });
const b = lead({ id: 'b', name: 'B', stage: 'lead' });
const c = lead({ id: 'c', name: 'C', stage: 'atendimento' });

function names(client: ReturnType<typeof makeClient>, filters = {}) {
  const cols = client.getQueryData<LeadColumn[]>(leadsKeys.board(filters))!;
  return cols.map((col) => col.cards.map((x) => x.id));
}

describe('read hooks', () => {
  it('config: stages and origins are data from the server', async () => {
    const { result } = renderHook(() => createLeadsHooks(makeApi()).useLeadsConfig(), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual(CONFIG));
    expect(result.current.showSkeleton).toBe(false);
  });

  it('board: skeleton only on the first load; a filter change keeps the old columns (never blanks)', async () => {
    const api = makeApi({
      'GET /api/leads/board': (_p: string, params?: any) => env(params?.origin ? board([], [], []) : board([a, b], [c], [])),
    });
    const hooks = createLeadsHooks(api);
    const { result, rerender } = renderHook(({ f }) => hooks.useLeadsBoard(f), { wrapper: wrapperFor(), initialProps: { f: {} as any } });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.showSkeleton).toBe(false);
    rerender({ f: { origin: 'instagram' } });
    expect(result.current.data).toBeDefined(); // the previous board stays up while the new filter loads
    expect(result.current.showSkeleton).toBe(false);
    await waitFor(() => expect(result.current.data![0].cards).toHaveLength(0));
    expect(api.get).toHaveBeenCalledWith('/api/leads/board', { origin: 'instagram' });
  });

  it('list: pages by cursor and flattens', async () => {
    const api = makeApi({
      'GET /api/leads': (_p: string, params?: any) =>
        params?.cursor ? { data: [b], next_cursor: null } : { data: [a], next_cursor: '1' },
    });
    const { result } = renderHook(() => createLeadsHooks(api).useLeadsList({ q: 'x' }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.data!.map((l) => l.id)).toEqual(['a', 'b']));
    expect(result.current.hasNextPage).toBe(false);
    expect(api.get).toHaveBeenLastCalledWith('/api/leads', { q: 'x', limit: 50, cursor: '1' });
  });

  it('detail: disabled without an id (no skeleton forever)', () => {
    const { result } = renderHook(() => createLeadsHooks(makeApi()).useLead(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
  });
});

describe('useMoveLead', () => {
  function setup(extra: Record<string, unknown> = {}) {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a, b], [c], []));
    client.setQueryData(leadsKeys.board({ q: 'zzz' }), board([a], [], []));
    const api = makeApi(extra);
    const hooks = createLeadsHooks(api);
    const { result } = renderHook(() => hooks.useMoveLead(), { wrapper: wrapperFor(client) });
    return { client, api, result };
  }

  it('moves the card on the drag (before the server answers) in every cached board, and keeps its own stage in sync', async () => {
    const d = deferred<any>();
    const { client, result, api } = setup({ 'POST /api/leads/a/move': () => d.promise });
    act(() => result.current.mutate({ id: 'a', stage: 'atendimento', toIndex: 0 }));
    await waitFor(() => expect(names(client)).toEqual([['b'], ['a', 'c'], []]));
    expect(client.getQueryData<LeadColumn[]>(leadsKeys.board({}))![1].cards[0].stage).toBe('atendimento');
    expect(client.getQueryData<LeadColumn[]>(leadsKeys.board({}))![0].total).toBe(1);
    expect(names(client, { q: 'zzz' })).toEqual([[], ['a'], []]);
    d.resolve(env({ ...a, stage: 'atendimento', position: -1 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/leads/a/move', { stage: 'atendimento', position: 0 });
  });

  it('rolls the card back when the server refuses', async () => {
    const d = deferred<any>();
    const { client, result } = setup({ 'POST /api/leads/a/move': () => d.promise });
    act(() => result.current.mutate({ id: 'a', stage: 'fechado', toIndex: 0 }));
    await waitFor(() => expect(names(client)[2]).toEqual(['a']));
    d.reject(new ApiError(422, 'etapa inválida'));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(names(client)).toEqual([['a', 'b'], ['c'], []]);
  });
});

describe('useUpdateLead', () => {
  it('draws the edit at once, then commits the server row (canonical phone) into board, lists and detail', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a], [], []));
    client.setQueryData(leadsKeys.list({}), { pages: [{ data: [a], next_cursor: null }], pageParams: [null] });
    client.setQueryData(leadsKeys.detail('a'), a);
    const d = deferred<any>();
    const hooks = createLeadsHooks(makeApi({ 'PATCH /api/leads/a': () => d.promise }));
    const { result } = renderHook(() => hooks.useUpdateLead(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ id: 'a', name: 'Ana Maria', phone: '(11) 99457-3387' }));
    await waitFor(() => expect(client.getQueryData<Lead>(leadsKeys.detail('a'))!.name).toBe('Ana Maria'));
    expect(client.getQueryData<LeadColumn[]>(leadsKeys.board({}))![0].cards[0].name).toBe('Ana Maria');
    d.resolve(env({ ...a, name: 'Ana Maria', phone: '+5511994573387' }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData<Lead>(leadsKeys.detail('a'))!.phone).toBe('+5511994573387');
    expect(client.getQueryData<any>(leadsKeys.list({})).pages[0].data[0].phone).toBe('+5511994573387');
  });

  it('a stage change from the form moves the card to the top of the new column once the server answers', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a], [c], []));
    const hooks = createLeadsHooks(makeApi({ 'PATCH /api/leads/a': env({ ...a, stage: 'atendimento' }) }));
    const { result } = renderHook(() => hooks.useUpdateLead(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ id: 'a', stage: 'atendimento' });
    });
    expect(names(client)).toEqual([[], ['a', 'c'], []]);
  });

  it('rolls back an edit the server refuses', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.detail('a'), a);
    const hooks = createLeadsHooks(makeApi({ 'PATCH /api/leads/a': () => Promise.reject(new ApiError(422, 'Telefone inválido')) }));
    const { result } = renderHook(() => hooks.useUpdateLead(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ id: 'a', phone: '12' }).catch(() => undefined);
    });
    expect(client.getQueryData<Lead>(leadsKeys.detail('a'))!.phone).toBe(a.phone);
  });
});

describe('useDeleteLead / useCreateLead', () => {
  it('delete removes the card from every board and list on the click', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a, b], [], []));
    client.setQueryData(leadsKeys.list({}), { pages: [{ data: [a, b], next_cursor: null }], pageParams: [null] });
    const d = deferred<any>();
    const hooks = createLeadsHooks(makeApi({ 'DELETE /api/leads/a': () => d.promise }));
    const { result } = renderHook(() => hooks.useDeleteLead(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate('a'));
    await waitFor(() => expect(names(client)[0]).toEqual(['b']));
    expect(client.getQueryData<any>(leadsKeys.list({})).pages[0].data.map((l: Lead) => l.id)).toEqual(['b']);
    d.resolve(undefined);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('delete is restored when the server fails', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a], [], []));
    const hooks = createLeadsHooks(makeApi({ 'DELETE /api/leads/a': () => Promise.reject(new ApiError(500, 'boom')) }));
    const { result } = renderHook(() => hooks.useDeleteLead(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync('a').catch(() => undefined);
    });
    expect(names(client)[0]).toEqual(['a']);
  });

  it('create puts the server row on top of the UNFILTERED board and list only, and seeds its detail', async () => {
    const client = makeClient();
    client.setQueryData(leadsKeys.board({}), board([a], [], []));
    client.setQueryData(leadsKeys.board({ origin: 'instagram' }), board([], [], []));
    client.setQueryData(leadsKeys.list({}), { pages: [{ data: [a], next_cursor: null }], pageParams: [null] });
    const created = lead({ id: 'n', name: 'Nova', stage: 'lead' });
    const hooks = createLeadsHooks(makeApi({ 'POST /api/leads': env(created) }));
    const { result } = renderHook(() => hooks.useCreateLead(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync({ name: 'Nova' });
    });
    expect(names(client)[0]).toEqual(['n', 'a']);
    expect(client.getQueryData<LeadColumn[]>(leadsKeys.board({}))![0].total).toBe(2);
    expect(names(client, { origin: 'instagram' })[0]).toEqual([]); // a filtered view converges on the refetch
    expect(client.getQueryData<any>(leadsKeys.list({})).pages[0].data.map((l: Lead) => l.id)).toEqual(['n', 'a']);
    expect(client.getQueryData<Lead>(leadsKeys.detail('n'))).toEqual(created);
  });
});
