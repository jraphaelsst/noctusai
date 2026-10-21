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

describe('cache writes (KB § PATTERNS/frontend/mutation-cache-writes.md)', () => {
  const never = () => new Promise<never>(() => undefined); // a refetch that never answers: the cache must already be right

  it('product update merges the PATCH answer into the detail (offers / media kept) and into the list row', async () => {
    const api = makeApi();
    let resolve!: (v: unknown) => void;
    api.patch.mockReturnValue(new Promise((r) => (resolve = r)));
    api.get.mockImplementation(never);
    const client = makeClient();
    const listKey = [...commerceKeys.products, 'list', {}];
    client.setQueryData(listKey, page([{ id: 'p1', title: 'Velho' }, { id: 'p2', title: 'Outro' }]));
    client.setQueryData(commerceKeys.product('p1'), { id: 'p1', title: 'Velho', offers: [{ id: 'o1' }], media: [{ id: 'm1' }] });
    const { result } = renderHook(() => createCommerceHooks(api).useProductMutations(), { wrapper: wrapperFor(client) });

    act(() => void result.current.update.mutate({ id: 'p1', title: 'Novo' }));
    await act(async () => resolve({ data: { id: 'p1', title: 'Novo', updated_at: 'now' } }));
    await waitFor(() => expect((client.getQueryData(commerceKeys.product('p1')) as { title: string }).title).toBe('Novo'));
    expect(client.getQueryData(commerceKeys.product('p1'))).toMatchObject({ offers: [{ id: 'o1' }], media: [{ id: 'm1' }] });
    expect((client.getQueryData(listKey) as { data: { title: string }[] }).data.map((r) => r.title)).toEqual(['Novo', 'Outro']);
  });

  it('product setStatus draws the status on the click and rolls it back when the server refuses', async () => {
    const api = makeApi();
    let reject!: (e: unknown) => void;
    api.post.mockReturnValue(new Promise((_r, j) => (reject = j)));
    api.get.mockImplementation(never);
    const client = makeClient();
    const listKey = [...commerceKeys.products, 'list', {}];
    client.setQueryData(listKey, page([{ id: 'p1', status: 'draft' }]));
    client.setQueryData(commerceKeys.product('p1'), { id: 'p1', status: 'draft' });
    const { result } = renderHook(() => createCommerceHooks(api).useProductMutations(), { wrapper: wrapperFor(client) });

    act(() => void result.current.setStatus.mutate({ id: 'p1', status: 'published' }));
    await waitFor(() => expect((client.getQueryData(commerceKeys.product('p1')) as { status: string }).status).toBe('published'));
    expect((client.getQueryData(listKey) as { data: { status: string }[] }).data[0].status).toBe('published');
    await act(async () => reject(new ApiError(422, 'sem_oferta_ativa', { error: { code: 'sem_oferta_ativa' } })));
    await waitFor(() => expect((client.getQueryData(commerceKeys.product('p1')) as { status: string }).status).toBe('draft'));
    expect((client.getQueryData(listKey) as { data: { status: string }[] }).data[0].status).toBe('draft');
  });

  it('product remove draws the removal on the click', async () => {
    const api = makeApi();
    api.delete.mockImplementation(never);
    api.get.mockImplementation(never);
    const client = makeClient();
    const listKey = [...commerceKeys.products, 'list', {}];
    client.setQueryData(listKey, page([{ id: 'p1' }, { id: 'p2' }]));
    const { result } = renderHook(() => createCommerceHooks(api).useProductMutations(), { wrapper: wrapperFor(client) });
    act(() => void result.current.remove.mutate('p1'));
    await waitFor(() => expect(client.getQueryData(listKey)).toMatchObject({ data: [{ id: 'p2' }], pagination: { total: 1 } }));
  });

  it('product create seeds the (empty) detail of the new product', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'new', title: 'N' } });
    api.get.mockImplementation(never);
    const client = makeClient();
    const { result } = renderHook(() => createCommerceHooks(api).useProductMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.create.mutateAsync({ slug: 's', title: 'N', product_type: 'digital', fulfillment_type: 'digital_delivery' })));
    expect(client.getQueryData(commerceKeys.product('new'))).toMatchObject({ id: 'new', offers: [], media: [] });
  });

  it('offer create / update / remove edit both the offers read and the detail\'s embedded offers', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'o2', name: 'B' } });
    api.get.mockImplementation(never);
    const client = makeClient();
    client.setQueryData(commerceKeys.offers('p1'), [{ id: 'o1', name: 'A' }]);
    client.setQueryData(commerceKeys.product('p1'), { id: 'p1', offers: [{ id: 'o1', name: 'A' }] });
    const { result } = renderHook(() => createCommerceHooks(api).useOfferMutations('p1'), { wrapper: wrapperFor(client) });

    await act(async () => void (await result.current.create.mutateAsync({ name: 'B' } as never)));
    expect((client.getQueryData(commerceKeys.offers('p1')) as { id: string }[]).map((o) => o.id)).toEqual(['o1', 'o2']);
    expect((client.getQueryData(commerceKeys.product('p1')) as { offers: { id: string }[] }).offers.map((o) => o.id)).toEqual(['o1', 'o2']);

    api.delete.mockImplementation(never);
    act(() => void result.current.remove.mutate('o1'));
    await waitFor(() => expect((client.getQueryData(commerceKeys.offers('p1')) as { id: string }[]).map((o) => o.id)).toEqual(['o2']));
    expect((client.getQueryData(commerceKeys.product('p1')) as { offers: { id: string }[] }).offers.map((o) => o.id)).toEqual(['o2']);
  });

  it('cancel order puts the cancelled order in the detail (items kept) and the list row', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'o1', status: 'cancelled' } });
    api.get.mockImplementation(never);
    const client = makeClient();
    const listKey = [...commerceKeys.orders, 'list', {}];
    client.setQueryData(listKey, page([{ id: 'o1', status: 'pending_payment' }]));
    client.setQueryData(commerceKeys.order('o1'), { id: 'o1', status: 'pending_payment', items: [{ id: 'i' }] });
    const { result } = renderHook(() => createCommerceHooks(api).useCancelOrder(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.mutateAsync('o1')));
    expect(client.getQueryData(commerceKeys.order('o1'))).toMatchObject({ status: 'cancelled', items: [{ id: 'i' }] });
    expect((client.getQueryData(listKey) as { data: { status: string }[] }).data[0].status).toBe('cancelled');
  });

  it('coupon create commits the server row; category rename is drawn on the click', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'c2', code: 'B' } });
    api.patch.mockImplementation(never);
    api.get.mockImplementation(never);
    const client = makeClient();
    client.setQueryData(commerceKeys.coupons, [{ id: 'c1', code: 'A' }]);
    client.setQueryData(commerceKeys.categories, [{ id: 'k1', name: 'Velho' }]);
    const hooks = createCommerceHooks(api);
    const { result } = renderHook(() => ({ c: hooks.useCouponMutations(), k: hooks.useCategoryMutations() }), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.c.create.mutateAsync({ code: 'B' } as never)));
    expect((client.getQueryData(commerceKeys.coupons) as { id: string }[]).map((c) => c.id)).toEqual(['c1', 'c2']);
    act(() => void result.current.k.update.mutate({ id: 'k1', name: 'Novo' }));
    await waitFor(() => expect((client.getQueryData(commerceKeys.categories) as { name: string }[])[0].name).toBe('Novo'));
  });

  it('invoice issue appends the invoice; fiscal save replaces the view; profile save replaces the profile', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'inv1', status: 'processing' } });
    api.put.mockResolvedValueOnce({ data: { enabled: true } }).mockResolvedValueOnce({ data: { trade_name: 'Loja' } });
    api.get.mockImplementation(never);
    const client = makeClient();
    client.setQueryData(commerceKeys.invoices('o1'), []);
    const hooks = createCommerceHooks(api);
    const { result } = renderHook(() => ({ i: hooks.useInvoiceMutations('o1'), f: hooks.useFiscalMutations(), p: hooks.useSaveProfile() }), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.i.issue.mutateAsync('nfse' as never)));
    expect(client.getQueryData(commerceKeys.invoices('o1'))).toEqual([{ id: 'inv1', status: 'processing' }]);
    await act(async () => void (await result.current.f.save.mutateAsync({} as never)));
    expect(client.getQueryData(commerceKeys.fiscal)).toEqual({ enabled: true });
    await act(async () => void (await result.current.p.mutateAsync({} as never)));
    expect(client.getQueryData(commerceKeys.profile)).toEqual({ trade_name: 'Loja' });
  });

  it('regenerate payment merges the new charge into the public order on screen', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { status: 'pending_payment', checkout_url: 'https://pay/new', expires_at: '2030-01-01' } });
    api.get.mockImplementation(never);
    const client = makeClient();
    client.setQueryData(commerceKeys.publicOrder('tok'), { token: 'tok', status: 'expired', items: [{ title: 'X' }], checkout_url: null, pix_qr: { code: 'old' } });
    const { result } = renderHook(() => createCommerceHooks(api).useRegeneratePayment('tok'), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.mutateAsync({ method: 'pix' } as never)));
    expect(client.getQueryData(commerceKeys.publicOrder('tok'))).toMatchObject({
      status: 'pending_payment', checkout_url: 'https://pay/new', items: [{ title: 'X' }], pix_qr: { code: 'old' },
    });
  });
});
