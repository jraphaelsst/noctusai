import { describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { isOptimistic, listOps, useCacheWriteMutation } from './cache-writes';

type Note = { id: string; text: string };
const KEY = ['notes', 'lead-1'];

function setup(initial?: Note[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  if (initial) qc.setQueryData(KEY, initial);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function useAddNote(fn: (text: string) => Promise<Note>, opts: { optimistic?: boolean } = {}) {
  return useCacheWriteMutation<Note, string>({
    mutationFn: fn,
    targets: [
      {
        queryKey: KEY,
        optimistic: opts.optimistic === false ? undefined : (old: Note[] | undefined, text, { tempId }) => listOps.append(old, { id: tempId, text }),
        commit: (old: Note[] | undefined, saved, _text, { tempId }) => listOps.replace(old, tempId, saved),
      },
    ],
  });
}

describe('useCacheWriteMutation', () => {
  it('draws the row before the server answers, then swaps in the server row', async () => {
    const { qc, wrapper } = setup([{ id: 'a', text: 'old' }]);
    const server = deferred<Note>();
    const { result } = renderHook(() => useAddNote(() => server.promise), { wrapper });

    act(() => result.current.mutate('new'));
    await waitFor(() => expect(qc.getQueryData<Note[]>(KEY)).toHaveLength(2));
    const drawn = qc.getQueryData<Note[]>(KEY)!;
    expect(drawn[1].text).toBe('new');
    expect(isOptimistic(drawn[1])).toBe(true);

    await act(async () => server.resolve({ id: 'b', text: 'new' }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<Note[]>(KEY)).toEqual([
      { id: 'a', text: 'old' },
      { id: 'b', text: 'new' },
    ]);
  });

  it('without optimism, the server row is written on success — no refetch needed to show it', async () => {
    const { qc, wrapper } = setup([]);
    const { result } = renderHook(() => useAddNote(async () => ({ id: 'b', text: 'x' }), { optimistic: false }), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('x');
    });
    expect(qc.getQueryData<Note[]>(KEY)).toEqual([{ id: 'b', text: 'x' }]);
  });

  it('rolls back to the snapshot on failure and still runs the caller onError', async () => {
    const { qc, wrapper } = setup([{ id: 'a', text: 'old' }]);
    const onError = vi.fn();
    const { result } = renderHook(
      () =>
        useCacheWriteMutation<Note, string>({
          mutationFn: async () => {
            throw new Error('boom');
          },
          targets: [{ queryKey: KEY, optimistic: (old: Note[] | undefined, text, { tempId }) => listOps.append(old, { id: tempId, text }) }],
          onError,
        }),
      { wrapper },
    );
    await act(async () => {
      await result.current.mutateAsync('new').catch(() => undefined);
    });
    expect(qc.getQueryData<Note[]>(KEY)).toEqual([{ id: 'a', text: 'old' }]);
    expect(onError).toHaveBeenCalledOnce();
  });

  it('invalidates every target and the extra keys when it settles (background convergence)', async () => {
    const { qc, wrapper } = setup([]);
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useCacheWriteMutation<Note, string>({
          mutationFn: async (text) => ({ id: 'b', text }),
          targets: [{ queryKey: KEY, commit: (old: Note[] | undefined, saved) => listOps.append(old, saved) }],
          invalidate: [['funil']],
        }),
      { wrapper },
    );
    await act(async () => {
      await result.current.mutateAsync('x');
    });
    const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(KEY);
    expect(keys).toContainEqual(['funil']);
  });

  it('leaves an uncached target uncached (nothing to draw on)', async () => {
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useAddNote(async () => ({ id: 'b', text: 'x' })), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('x');
    });
    expect(qc.getQueryData(KEY)).toBeUndefined();
  });
});

describe('listOps.replace', () => {
  it('never duplicates when a refetch already brought the server row in', () => {
    const list = [{ id: 'optimistic:1', t: 1 }, { id: 'b', t: 2 }];
    expect(listOps.replace(list, 'optimistic:1', { id: 'b', t: 3 })).toEqual([{ id: 'b', t: 3 }]);
  });

  it('keeps the stand-in position', () => {
    const list = [{ id: 'a' }, { id: 'optimistic:1' }, { id: 'c' }];
    expect(listOps.replace(list, 'optimistic:1', { id: 'b' })).toEqual([{ id: 'a' }, { id: 'b' }, { id: 'c' }]);
  });
});

describe("match: 'prefix'", () => {
  it('edits every cached list under the prefix, leaves a detail object untouched, and rolls all back', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    qc.setQueryData(['things', undefined], [{ id: 'a' }, { id: 'b' }]);
    qc.setQueryData(['things', { status: 'open' }], [{ id: 'b' }]);
    qc.setQueryData(['things', 'b'], { id: 'b', name: 'detail' });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const server = deferred<unknown>();
    const { result } = renderHook(
      () =>
        useCacheWriteMutation<unknown, string>({
          mutationFn: () => server.promise,
          targets: [{ queryKey: ['things'], match: 'prefix', optimistic: (old: any, id) => listOps.remove(old, id) }],
        }),
      { wrapper },
    );
    act(() => result.current.mutate('b'));
    await waitFor(() => expect(qc.getQueryData(['things', undefined])).toEqual([{ id: 'a' }]));
    expect(qc.getQueryData(['things', { status: 'open' }])).toEqual([]);
    expect(qc.getQueryData(['things', 'b'])).toEqual({ id: 'b', name: 'detail' });

    await act(async () => server.reject(new Error('nope')));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData(['things', undefined])).toEqual([{ id: 'a' }, { id: 'b' }]);
    expect(qc.getQueryData(['things', { status: 'open' }])).toEqual([{ id: 'b' }]);
  });
});

describe('listOps on non-arrays', () => {
  it('passes a paginated envelope and a detail object through unchanged', () => {
    const env = { items: [{ id: 'a' }], next_cursor: null };
    expect(listOps.remove(env as any, 'a')).toBe(env);
    expect(listOps.append(env as any, { id: 'b' })).toBe(env);
    expect(listOps.merge({ id: 'a', n: 1 }, { n: 2 })).toEqual({ id: 'a', n: 2 });
    expect(listOps.merge([{ id: 'a' }] as any, { n: 2 } as any)).toEqual([{ id: 'a' }]);
  });
});

describe('listOps.within', () => {
  it('edits the array an envelope keeps under a field and passes anything else through', () => {
    const env = { items: [{ id: 'a' }, { id: 'b' }], total: 2 };
    expect(listOps.within(env, 'items', (l) => listOps.remove(l, 'a'))).toEqual({ items: [{ id: 'b' }], total: 2 });
    expect(listOps.within(undefined as typeof env | undefined, 'items', (l) => l)).toBeUndefined();
    const detail = { id: 'x', items: 'not-a-list' } as any;
    expect(listOps.within(detail, 'items', () => [])).toBe(detail);
  });
});

describe('listOps — idKey, numeric ids, update', () => {
  it('addresses rows by a custom key and by numeric ids', () => {
    const hosts = [{ hostname: 'a.com', ok: false }, { hostname: 'b.com', ok: false }];
    expect(listOps.patch(hosts, 'b.com', { ok: true }, 'hostname')).toEqual([hosts[0], { hostname: 'b.com', ok: true }]);
    expect(listOps.remove(hosts, 'a.com', 'hostname')).toEqual([hosts[1]]);
    expect(listOps.replace(hosts, 'a.com', { hostname: 'a.com', ok: true }, 'append', 'hostname')?.length).toBe(2);
    const segs = [{ id: 1, n: 'x' }, { id: 2, n: 'y' }];
    expect(listOps.patch(segs, 2, { n: 'z' })).toEqual([segs[0], { id: 2, n: 'z' }]);
    expect(listOps.remove(segs, 1)).toEqual([segs[1]]);
    expect(listOps.replace(segs, 1, { id: 1, n: 'new' })).toEqual([{ id: 1, n: 'new' }, segs[1]]);
  });

  it('update edits a nested row inside a row', () => {
    const leads = [{ id: 'l1', activities: [{ id: 'a1' }] }, { id: 'l2', activities: [] as { id: string }[] }];
    const out = listOps.update(leads, 'l1', (l) => ({ ...l, activities: listOps.prepend(l.activities, { id: 'a2' })! }));
    expect(out?.[0].activities.map((a) => a.id)).toEqual(['a2', 'a1']);
    expect(out?.[1]).toBe(leads[1]);
    expect(listOps.update(undefined, 'l1', (l) => l)).toBeUndefined();
  });
});

describe("key-aware writes (queryKey arg + predicate)", () => {
  it('passes the concrete queryKey and only touches entries the predicate accepts', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    qc.setQueryData(['folders', 'acc1', 'all'], [{ id: 'a' }]);
    qc.setQueryData(['folders', 'acc2', 'all'], [{ id: 'b' }]);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const seen: unknown[] = [];
    const { result } = renderHook(
      () =>
        useCacheWriteMutation<{ id: string }, string>({
          mutationFn: async () => ({ id: 'n' }),
          targets: [
            {
              queryKey: ['folders'],
              match: 'prefix',
              predicate: (key) => key[1] === 'acc1',
              optimistic: (old: any, _v, _c, key) => {
                seen.push(['o', key]);
                return listOps.prepend(old, { id: 'tmp' });
              },
              commit: (old: any, saved, _v, _c, key) => {
                seen.push(['c', key]);
                return listOps.replace(old, 'tmp', saved);
              },
            },
          ],
        }),
      { wrapper },
    );
    await act(async () => {
      await result.current.mutateAsync('x');
    });
    expect(qc.getQueryData(['folders', 'acc1', 'all'])).toEqual([{ id: 'n' }, { id: 'a' }]);
    expect(qc.getQueryData(['folders', 'acc2', 'all'])).toEqual([{ id: 'b' }]);
    expect(seen).toEqual([['o', ['folders', 'acc1', 'all']], ['c', ['folders', 'acc1', 'all']]]);
  });
});

describe('listOps.insertSorted', () => {
  const byName = (a: { id: string; name: string }, b: { id: string; name: string }) => a.name.localeCompare(b.name);
  const l = [{ id: '1', name: 'a' }, { id: '2', name: 'c' }];
  it('lands where the sort puts it, replaces an existing id, passes non-arrays through', () => {
    expect(listOps.insertSorted(l, { id: '3', name: 'b' }, byName)?.map((r) => r.id)).toEqual(['1', '3', '2']);
    expect(listOps.insertSorted(l, { id: '3', name: 'z' }, byName)?.map((r) => r.id)).toEqual(['1', '2', '3']);
    expect(listOps.insertSorted(l, { id: '2', name: 'a2' }, byName)?.map((r) => r.id)).toEqual(['1', '2']);
    expect(listOps.insertSorted(undefined, l[0], byName)).toBeUndefined();
  });
});

describe('settle is background — never holds the mutation pending', () => {
  it('reaches isSuccess before the invalidation refetch resolves', async () => {
    const { qc, wrapper } = setup([]);
    const refetch = deferred<Note[]>();
    qc.setQueryDefaults(KEY, { queryFn: () => refetch.promise });
    renderHook(() => qc && null, { wrapper }); // keep wrapper warm
    const obs = qc.getQueryCache().find({ queryKey: KEY })!;
    const unsub = new (await import('@tanstack/react-query')).QueryObserver(qc, { queryKey: KEY, queryFn: () => refetch.promise }).subscribe(() => {});
    const { result } = renderHook(() => useAddNote(async (text) => ({ id: 's1', text })), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('hi');
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isPending).toBe(false);
    expect(obs.state.fetchStatus).toBe('fetching'); // refetch still in flight
    refetch.resolve([]);
    unsub();
  });
});
