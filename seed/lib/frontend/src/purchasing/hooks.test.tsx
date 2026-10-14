/** Hook factory: two-signal loading, placeholderData on key change, invalidation after writes, error mapping, host callback. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { createPurchasingHooks, purchasingErrorMessage } from './hooks';
import { detail, makeApi, makeClient, order, page, receipt, wrapperFor } from './testUtils';

afterEach(cleanup);

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createPurchasingHooks(api);
    const { result } = renderHook(() => hooks.usePurchaseOrders({}), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => resolve(page([order()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([order(), order({ id: 'o2' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a filter change keeps the previous rows (placeholderData); empty filters are not sent', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([order()]));
    const hooks = createPurchasingHooks(api);
    const { result, rerender } = renderHook(({ s }) => hooks.usePurchaseOrders({ status: s, q: '' }), { wrapper: wrapperFor(), initialProps: { s: '' as const } });
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(api.get).toHaveBeenCalledWith('/api/purchasing/orders', {});
    api.get.mockImplementationOnce(() => new Promise(() => undefined));
    rerender({ s: 'draft' as never });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    expect(api.get).toHaveBeenLastCalledWith('/api/purchasing/orders', { status: 'draft' });
  });

  it('the order detail is disabled without an id and never shows another order under a new id', async () => {
    const api = makeApi();
    const hooks = createPurchasingHooks(api);
    const { result } = renderHook(() => hooks.usePurchaseOrder(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();

    api.get.mockResolvedValueOnce({ data: detail() });
    const { result: r2, rerender } = renderHook(({ id }) => hooks.usePurchaseOrder(id), { wrapper: wrapperFor(), initialProps: { id: 'A' } });
    await waitFor(() => expect(r2.current.data?.id).toBe('ord-1'));
    api.get.mockImplementationOnce(() => new Promise(() => undefined));
    rerender({ id: 'B' });
    await waitFor(() => expect(r2.current.showSkeleton).toBe(true));
    expect(r2.current.data).toBeUndefined();
  });
});

describe('writes', () => {
  it('save posts a new order and PUTs a replacement; the answer seeds the detail cache and the lists refetch', async () => {
    const api = makeApi();
    const client = makeClient();
    api.post.mockResolvedValue({ data: order({ id: 'new' }) });
    api.put.mockResolvedValue({ data: order({ id: 'ord-1', notes: 'x' }) });
    const hooks = createPurchasingHooks(api);
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => hooks.usePurchaseOrderMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.save.mutateAsync({ lines: [{ description: 'x', qty: '1', unit_cost_cents: 1 }] })));
    expect(api.post).toHaveBeenCalledWith('/api/purchasing/orders', { lines: [{ description: 'x', qty: '1', unit_cost_cents: 1 }] });
    await act(async () => void (await result.current.save.mutateAsync({ id: 'ord-1', notes: 'x', lines: [] })));
    expect(api.put).toHaveBeenCalledWith('/api/purchasing/orders/ord-1', { notes: 'x', lines: [] });
    expect(client.getQueryData(['purchasing', 'order', 'ord-1'])).toMatchObject({ notes: 'x' });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['purchasing', 'orders'] });
  });

  it('approve / send / cancel hit their routes; cancel carries the reason only when given', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: order() });
    const hooks = createPurchasingHooks(api);
    const { result } = renderHook(() => hooks.usePurchaseOrderMutations(), { wrapper: wrapperFor() });
    await act(async () => {
      await result.current.approve.mutateAsync('o1');
      await result.current.send.mutateAsync('o1');
      await result.current.cancel.mutateAsync({ id: 'o1' });
      await result.current.cancel.mutateAsync({ id: 'o1', reason: 'duplicado' });
    });
    expect(api.post.mock.calls).toEqual([
      ['/api/purchasing/orders/o1/approve'],
      ['/api/purchasing/orders/o1/send'],
      ['/api/purchasing/orders/o1/cancel', {}],
      ['/api/purchasing/orders/o1/cancel', { reason: 'duplicado' }],
    ]);
  });

  it('a receipt refreshes orders + receipts and calls the host callback (stock / payables live elsewhere)', async () => {
    const api = makeApi();
    const client = makeClient();
    const onReceived = vi.fn();
    api.post.mockResolvedValue({ data: { ...receipt(), replayed: false, order_status: 'received' } });
    const hooks = createPurchasingHooks(api, { onReceived });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => hooks.useReceiptMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.receive.mutateAsync({ orderId: 'o1', idempotency_key: 'k', lines: [{ order_line_id: 'l1', qty: '2' }] })));
    expect(api.post).toHaveBeenCalledWith('/api/purchasing/orders/o1/receipts', { idempotency_key: 'k', lines: [{ order_line_id: 'l1', qty: '2' }] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['purchasing', 'receipts'] });
    expect(onReceived).toHaveBeenCalledTimes(1);
    await act(async () => void (await result.current.repost.mutateAsync('rc-1')));
    expect(api.post).toHaveBeenLastCalledWith('/api/purchasing/receipts/rc-1/post');
    expect(onReceived).toHaveBeenCalledTimes(2);
  });

  it('approvers: list and add/remove seed the cache, and refresh the settings read (is_approver may have changed)', async () => {
    const api = makeApi();
    const client = makeClient();
    const row = (user_id: string) => ({ org_id: 'o', user_id, granted_by: null, granted_at: '' });
    api.get.mockResolvedValue({ data: [row('u1')] });
    api.post.mockResolvedValue({ data: [row('u1'), row('u2')] });
    api.delete.mockResolvedValue({ data: [row('u2')] });
    const hooks = createPurchasingHooks(api);
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => ({ q: hooks.usePurchaseApprovers(), m: hooks.usePurchaseApproverMutations() }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.q.data).toHaveLength(1));
    await act(async () => void (await result.current.m.add.mutateAsync('u2')));
    expect(api.post).toHaveBeenCalledWith('/api/purchasing/approvers', { user_id: 'u2' });
    await waitFor(() => expect(result.current.q.data).toHaveLength(2));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['purchasing', 'settings'] });
    await act(async () => void (await result.current.m.remove.mutateAsync('u1')));
    expect(api.delete).toHaveBeenCalledWith('/api/purchasing/approvers/u1');
    await waitFor(() => expect(result.current.q.data).toEqual([row('u2')]));
  });

  it('a disabled approvers hook never calls the API', () => {
    const api = makeApi();
    renderHook(() => createPurchasingHooks(api).usePurchaseApprovers(false), { wrapper: wrapperFor() });
    expect(api.get).not.toHaveBeenCalled();
  });

  it('settings: read, then write the threshold (null clears) and seed the cache', async () => {
    const api = makeApi();
    const client = makeClient();
    api.get.mockResolvedValue({ data: { approval_threshold_cents: null, persisted: false } });
    api.put.mockResolvedValue({ data: { approval_threshold_cents: 50000, persisted: true } });
    const hooks = createPurchasingHooks(api);
    const { result } = renderHook(() => ({ q: hooks.usePurchasingSettings(), m: hooks.useSetPurchasingSettings() }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.q.data?.persisted).toBe(false));
    await act(async () => void (await result.current.m.mutateAsync(50000)));
    expect(api.put).toHaveBeenCalledWith('/api/purchasing/settings', { approval_threshold_cents: 50000 });
    await waitFor(() => expect(result.current.q.data?.approval_threshold_cents).toBe(50000));
  });
});

describe('error mapping', () => {
  it('maps stable codes to pt-BR and falls back to the server message', () => {
    const coded = new ApiError(403, 'x', { error: { code: 'aprovacao_acima_do_limite', message: 'x' } });
    expect(purchasingErrorMessage(coded)).toContain('limite de aprovação');
    expect(purchasingErrorMessage(new ApiError(409, 'x', { error: { code: 'limite_em_carencia', message: 'x' } }))).toContain('carência');
    expect(purchasingErrorMessage(new ApiError(403, 'x', { error: { code: 'sem_permissao_limite', message: 'x' } }))).toContain('aprovador');
    expect(purchasingErrorMessage(new ApiError(500, 'boom', {}))).toContain('boom');
    expect(purchasingErrorMessage(new Error('rede'))).toBe('rede');
  });
});
