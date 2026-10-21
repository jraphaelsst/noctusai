import { describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { createCrudHooks } from './hooks';

type Cliente = { id: string; nome: string };

function setup(api: Record<string, any>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const hooks = createCrudHooks<Cliente>({
    resource: 'clientes', apiPath: '/api/clientes', singularName: 'Cliente', api: api as any, getUser: () => ({ id: 'u' }),
  });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return { qc, hooks, wrapper };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

describe('createCrudHooks writes the cache (KB § PATTERNS/frontend/mutation-cache-writes.md)', () => {
  it('useCreate puts the server row in the unfiltered list without a refetch', async () => {
    const { qc, hooks, wrapper } = setup({ post: async () => ({ id: 'c2', nome: 'Novo' }) });
    qc.setQueryData(['clientes', undefined], [{ id: 'c1', nome: 'A' }]);
    const { result } = renderHook(() => hooks.useCreate(), { wrapper });
    await act(async () => { await result.current.mutateAsync({ nome: 'Novo' }); });
    expect(qc.getQueryData(['clientes', undefined])).toEqual([{ id: 'c1', nome: 'A' }, { id: 'c2', nome: 'Novo' }]);
  });

  it('useUpdate draws the edit in every list and the detail while the PATCH is in flight', async () => {
    const server = deferred<Cliente>();
    const { qc, hooks, wrapper } = setup({ patch: () => server.promise });
    qc.setQueryData(['clientes', undefined], [{ id: 'c1', nome: 'A' }]);
    qc.setQueryData(['clientes', { q: 'a' }], [{ id: 'c1', nome: 'A' }]);
    qc.setQueryData(['clientes', 'c1'], { id: 'c1', nome: 'A' });
    const { result } = renderHook(() => hooks.useUpdate(), { wrapper });
    act(() => result.current.mutate({ id: 'c1', nome: 'B' }));
    await waitFor(() => expect(qc.getQueryData(['clientes', undefined])).toEqual([{ id: 'c1', nome: 'B' }]));
    expect(qc.getQueryData(['clientes', { q: 'a' }])).toEqual([{ id: 'c1', nome: 'B' }]);
    expect(qc.getQueryData(['clientes', 'c1'])).toEqual({ id: 'c1', nome: 'B' });
    await act(async () => server.resolve({ id: 'c1', nome: 'B (server)' }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(['clientes', 'c1'])).toEqual({ id: 'c1', nome: 'B (server)' });
  });

  it('useDelete removes the row on click', async () => {
    const server = deferred<unknown>();
    const { qc, hooks, wrapper } = setup({ delete: () => server.promise });
    qc.setQueryData(['clientes', undefined], [{ id: 'c1', nome: 'A' }, { id: 'c2', nome: 'B' }]);
    const { result } = renderHook(() => hooks.useDelete(), { wrapper });
    act(() => result.current.mutate('c1'));
    await waitFor(() => expect(qc.getQueryData(['clientes', undefined])).toEqual([{ id: 'c2', nome: 'B' }]));
  });
});
