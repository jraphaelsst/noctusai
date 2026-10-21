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
