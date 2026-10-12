/**
 * Hook factory tests — two-signal loading contract, placeholderData on key
 * change, order polling that stops, invalidation after mutations, fetch
 * transport (envelopes/errors).
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { createCommerceHooks, createFetchTransport, commerceKeys, ORDER_POLL_MS } from './hooks';
import { makeApi, makeClient, wrapperFor } from './testUtils';
import { ApiError } from '../api';

afterEach(cleanup);

const page = (rows: unknown[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length } });

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createCommerceHooks(api);
    const client = makeClient();
    const { result } = renderHook(() => hooks.useOrders({}), { wrapper: wrapperFor(client) });

    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => resolve(page([{ id: 'o1' }])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    // data stays on screen while refreshing: never a skeleton again.
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([{ id: 'o1' }, { id: 'o2' }])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a list key change keeps the previous page (placeholderData) instead of an empty/skeleton flash', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([{ id: 'a' }]));
    const hooks = createCommerceHooks(api);
    const { result, rerender } = renderHook(({ p }) => hooks.useOrders({ page: p }), {
      wrapper: wrapperFor(),
      initialProps: { p: 1 },
    });
    await waitFor(() => expect(result.current.data?.data[0]).toEqual({ id: 'a' }));

    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    rerender({ p: 2 });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data[0]).toEqual({ id: 'a' });
    expect(result.current.isRefreshing).toBe(true);
    await act(async () => resolve(page([{ id: 'b' }])));
    await waitFor(() => expect(result.current.data?.data[0]).toEqual({ id: 'b' }));
  });

  it('a disabled query (no id) is not a skeleton', () => {
    const hooks = createCommerceHooks(makeApi());
    const { result } = renderHook(() => hooks.useProduct(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
  });

  it('id-keyed personal data does not leak the previous record under a new key', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce({ data: { id: 'c1', name: 'Ana' } });
    const hooks = createCommerceHooks(api);
    const { result, rerender } = renderHook(({ id }) => hooks.useCustomer(id), {
      wrapper: wrapperFor(),
      initialProps: { id: 'c1' },
    });
    await waitFor(() => expect(result.current.data?.name).toBe('Ana'));
    api.get.mockImplementationOnce(() => new Promise(() => {}));
    rerender({ id: 'c2' });
    await waitFor(() => expect(result.current.showSkeleton).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('surfaces query errors (no silent catch)', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'boom'));
    const { result } = renderHook(() => createCommerceHooks(api).useCoupons(), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(String(result.current.error)).toContain('boom');
  });
});

describe('order polling', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('polls while pending_payment and stops once paid', async () => {
    const api = makeApi();
    api.get
      .mockResolvedValueOnce({ data: { token: 't', status: 'pending_payment', items: [] } })
      .mockResolvedValueOnce({ data: { token: 't', status: 'paid', items: [] } });
    const hooks = createCommerceHooks(api);
    const { result } = renderHook(() => hooks.usePublicOrder('t', { poll: true }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data?.status).toBe('pending_payment'));
    await act(async () => void (await vi.advanceTimersByTimeAsync(ORDER_POLL_MS + 50)));
    await waitFor(() => expect(result.current.data?.status).toBe('paid'));
    const calls = api.get.mock.calls.length;
    await act(async () => void (await vi.advanceTimersByTimeAsync(ORDER_POLL_MS * 3)));
    expect(api.get.mock.calls.length).toBe(calls);
  });

  it('does not poll without the poll option', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: { token: 't', status: 'pending_payment', items: [] } });
    const { result } = renderHook(() => createCommerceHooks(api).usePublicOrder('t'), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    await act(async () => void (await vi.advanceTimersByTimeAsync(ORDER_POLL_MS * 3)));
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});

describe('mutations', () => {
  it('invalidate the right namespaced keys and unwrap envelopes', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'p1' } });
    const client = makeClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => createCommerceHooks(api).useProductMutations(), { wrapper: wrapperFor(client) });
    let created: unknown;
    await act(async () => {
      created = await result.current.create.mutateAsync({ slug: 's', title: 'T', product_type: 'digital', fulfillment_type: 'digital_delivery' });
    });
    expect(created).toEqual({ id: 'p1' });
    expect(api.post).toHaveBeenCalledWith('/api/commerce/products', expect.objectContaining({ slug: 's' }));
    expect(spy).toHaveBeenCalledWith({ queryKey: commerceKeys.products });
  });

  it('rejects with the ApiError (not swallowed) so the UI can branch on 409', async () => {
    const api = makeApi();
    api.put.mockRejectedValue(new ApiError(409, 'versao_conflitante', { error: { code: 'versao_conflitante' } }));
    const { result } = renderHook(() => createCommerceHooks(api).useSaveProfile(), { wrapper: wrapperFor() });
    await act(async () => {
      await expect(result.current.mutateAsync({ expected_version: 1 } as never)).rejects.toMatchObject({ status: 409 });
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('fetch transport (base URL mode)', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });
  it('GETs with query params, drops empty ones, and throws ApiError with code on 422', async () => {
    const f = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ data: [] }), { status: 200 }));
    globalThis.fetch = f as unknown as typeof fetch;
    const t = createFetchTransport('https://shop.test/');
    await t.get('/api/storefront/catalog', { q: '', page: 2, category: undefined });
    expect(f.mock.calls[0][0]).toBe('https://shop.test/api/storefront/catalog?page=2');

    f.mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'aceite_obrigatorio', message: 'faltou aceite' } }), { status: 422 }));
    await expect(t.post('/api/storefront/checkout', {})).rejects.toMatchObject({ status: 422, code: 'aceite_obrigatorio' });
  });
});
