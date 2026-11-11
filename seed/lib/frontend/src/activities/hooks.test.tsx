/** Cache contract of the activities hooks: loading signals, what each write puts in the cache, rollback, error copy. */
import { describe, expect, it } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { activitiesErrorMessage, activitiesKeys, createActivitiesHooks } from './hooks';
import { activity, ENTITY, makeApi, makeClient, OTHER_ENTITY, page, type as type_, wrapperFor } from './testUtils';

const OPEN = { entity_kind: 'lead', entity_id: ENTITY, status: 'open' as const };

function setup(routes: Record<string, unknown> = {}) {
  const api = makeApi({ 'GET /api/activities/types': { data: [type_()] }, ...routes });
  const client = makeClient();
  const hooks = createActivitiesHooks(api);
  return { api, client, hooks, wrapper: wrapperFor(client) };
}

describe('loading signals', () => {
  it('a disabled list (no entity yet) is idle, never a skeleton', () => {
    const { hooks, wrapper } = setup();
    const { result } = renderHook(() => hooks.useActivities(null), { wrapper });
    expect(result.current.showSkeleton).toBe(false);
  });

  it('first load is a skeleton, a refetch over data is only isRefreshing', async () => {
    const { hooks, wrapper, api } = setup({ 'GET /api/activities': page([activity()]) });
    const { result } = renderHook(() => hooks.useActivities(OPEN), { wrapper });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);
    await act(async () => {
      void result.current.refetch();
    });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it("another card's tasks are never shown under this card's key (no placeholder across entities)", async () => {
    const { hooks, wrapper } = setup({
      'GET /api/activities': (_p: string, params?: { entity_id?: string }) =>
        params?.entity_id === ENTITY ? page([activity()]) : new Promise(() => undefined),
    });
    const { result, rerender } = renderHook(({ id }) => hooks.useActivities({ ...OPEN, entity_id: id }), { wrapper, initialProps: { id: ENTITY } });
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    rerender({ id: OTHER_ENTITY });
    expect(result.current.data).toBeUndefined();
    expect(result.current.showSkeleton).toBe(true);
  });
});

describe('writes put what they know into the cache', () => {
  it('create draws the server row into THIS card\'s open list (sorted by due) and not into another card\'s', async () => {
    const mine = page([activity({ id: 'a-late', due_at: '2030-06-01T00:00:00Z' })]);
    const other = page([activity({ id: 'z1', entity_id: OTHER_ENTITY })]);
    const saved = activity({ id: 'a-new', due_at: '2030-01-01T00:00:00Z', title: 'Nova' });
    const { hooks, wrapper, api, client } = setup({ 'POST /api/activities': { data: saved } });
    client.setQueryData([...activitiesKeys.list, OPEN], mine);
    client.setQueryData([...activitiesKeys.list, { ...OPEN, entity_id: OTHER_ENTITY }], other);
    api.route('GET /api/activities', () => new Promise(() => undefined)); // the settle refetch never answers: the cache write alone must be right
    const { result } = renderHook(() => hooks.useActivityMutations(), { wrapper });
    await act(async () => {
      await result.current.create.mutateAsync({ entity_kind: 'lead', entity_id: ENTITY, type_slug: 'tarefa', title: 'Nova', due_at: saved.due_at });
    });
    const open = client.getQueryData<ReturnType<typeof page<ReturnType<typeof activity>>>>([...activitiesKeys.list, OPEN])!;
    expect(open.data.map((r) => r.id)).toEqual(['a-new', 'a-late']);
    expect(open.pagination.total).toBe(2);
    const foreign = client.getQueryData<typeof other>([...activitiesKeys.list, { ...OPEN, entity_id: OTHER_ENTITY }])!;
    expect(foreign.data.map((r) => r.id)).toEqual(['z1']);
  });

  it('complete is drawn done on the click (before the server answers) and rolls back when refused', async () => {
    const { hooks, wrapper, api, client } = setup();
    client.setQueryData([...activitiesKeys.list, OPEN], page([activity()]));
    client.setQueryData([...activitiesKeys.mine, {}], page([activity()]));
    let reject!: (e: unknown) => void;
    api.route('POST /api/activities/a1/complete', () => new Promise((_, r) => (reject = r)));
    api.route('GET /api/activities', () => new Promise(() => undefined));
    const { result } = renderHook(() => hooks.useActivityMutations(), { wrapper });
    let p!: Promise<unknown>;
    act(() => {
      p = result.current.complete.mutateAsync({ id: 'a1' }).catch(() => undefined);
    });
    await waitFor(() => expect(client.getQueryData<any>([...activitiesKeys.list, OPEN]).data[0].done_at).toBeTruthy());
    expect(client.getQueryData<any>([...activitiesKeys.mine, {}]).data[0].outcome).toBe('realizada');
    reject(new ApiError(409, 'closed', { error: { code: 'atividade_encerrada' } }));
    await act(async () => {
      await p;
    });
    expect(client.getQueryData<any>([...activitiesKeys.list, OPEN]).data[0].done_at).toBeNull();
  });

  it('the server row replaces the optimistic one (reassign, reschedule, edit, reopen, cancel hit the right verb)', async () => {
    const { hooks, wrapper, api, client } = setup();
    client.setQueryData([...activitiesKeys.list, OPEN], page([activity()]));
    api.route('GET /api/activities', () => new Promise(() => undefined));
    for (const [verb, body] of [
      ['reassign', { assignee_id: 'u2' }],
      ['reschedule', { due_at: '2031-01-01T00:00:00Z' }],
      ['reopen', {}],
      ['cancel', {}],
    ] as const) api.route(`POST /api/activities/a1/${verb}`, { data: activity({ title: `server-${verb}` }) });
    api.route('PATCH /api/activities/a1', { data: activity({ title: 'server-edit' }) });
    const { result } = renderHook(() => hooks.useActivityMutations(), { wrapper });
    await act(async () => {
      await result.current.reassign.mutateAsync({ id: 'a1', assignee_id: 'u2' });
    });
    expect(api.post).toHaveBeenLastCalledWith('/api/activities/a1/reassign', { assignee_id: 'u2' });
    expect(client.getQueryData<any>([...activitiesKeys.list, OPEN]).data[0].title).toBe('server-reassign');
    await act(async () => {
      await result.current.reschedule.mutateAsync({ id: 'a1', due_at: '2031-01-01T00:00:00Z' });
      await result.current.reopen.mutateAsync({ id: 'a1' });
      await result.current.cancel.mutateAsync({ id: 'a1' });
      await result.current.edit.mutateAsync({ id: 'a1', title: 'x' });
    });
    expect(api.patch).toHaveBeenLastCalledWith('/api/activities/a1', { title: 'x' });
    expect(client.getQueryData<any>([...activitiesKeys.list, OPEN]).data[0].title).toBe('server-edit');
  });
});

describe('error copy', () => {
  it('maps the stable backend codes to pt-BR and falls back to the server message', () => {
    expect(activitiesErrorMessage(new ApiError(409, 'x', { error: { code: 'atividade_encerrada' } }))).toBe('A atividade já foi encerrada (concluída ou cancelada).');
    expect(activitiesErrorMessage(new ApiError(422, 'x', { error: { code: 'responsavel_invalido' } }))).toMatch(/membro ativo/);
    expect(activitiesErrorMessage(new Error('rede caiu'))).toBe('rede caiu');
  });
});
