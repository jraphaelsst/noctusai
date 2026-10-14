/** Hook factory: two-signal loading, placeholderData on key change, invalidation after stock mutations, error mapping. */
import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { createInventoryHooks, inventoryErrorMessage, inventoryKeys } from './hooks';
import { balance, makeApi, makeClient, page, wrapperFor } from './testUtils';

afterEach(cleanup);

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createInventoryHooks(api);
    const { result } = renderHook(() => hooks.useBalances({}), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => resolve(page([balance()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([balance(), balance({ item_id: 'b' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a page change keeps the previous rows (placeholderData) instead of a skeleton flash', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([balance()]));
    const hooks = createInventoryHooks(api);
    const { result, rerender } = renderHook(({ p }) => hooks.useBalances({ page: p }), { wrapper: wrapperFor(), initialProps: { p: 1 } });
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    rerender({ p: 2 });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve(page([balance({ item_id: 'z' })])));
  });

  it('the kardex is disabled without an item and never shows another item\'s rows under a new key', async () => {
    const api = makeApi();
    const hooks = createInventoryHooks(api);
    const { result } = renderHook(() => hooks.useKardex(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();

    api.get.mockResolvedValueOnce(page([{ id: 'm-a' }]));
    const { result: r2, rerender } = renderHook(({ id }) => hooks.useKardex({ item_id: id }), { wrapper: wrapperFor(), initialProps: { id: 'A' } });
    await waitFor(() => expect(r2.current.data?.data).toHaveLength(1));
    api.get.mockImplementationOnce(() => new Promise(() => undefined));
    rerender({ id: 'B' });
    await waitFor(() => expect(r2.current.data).toBeUndefined());
    expect(r2.current.showSkeleton).toBe(true);
  });
});

describe('mutations', () => {
  it('a stock move invalidates balances, kardex, valuation and low-stock together', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { status: 'ok', moves: [] } });
    const client = makeClient();
    const hooks = createInventoryHooks(api);
    const { result } = renderHook(() => hooks.useStockMutations(), { wrapper: wrapperFor(client) });
    for (const k of [inventoryKeys.balances, inventoryKeys.kardex, inventoryKeys.valuation, inventoryKeys.lowStock]) {
      client.setQueryData([...k, 'probe'], { x: 1 });
    }
    await act(async () => {
      await result.current.adjust.mutateAsync({ item_id: 'i', warehouse_id: 'w', counted_qty: '3' });
    });
    expect(api.post).toHaveBeenCalledWith('/api/inventory/adjust', { item_id: 'i', warehouse_id: 'w', counted_qty: '3' });
    for (const k of [inventoryKeys.balances, inventoryKeys.kardex, inventoryKeys.valuation, inventoryKeys.lowStock]) {
      expect(client.getQueryState([...k, 'probe'])?.isInvalidated).toBe(true);
    }
  });

  it('a refused move rejects with ApiError (never swallowed) and the code maps to pt-BR copy', async () => {
    const api = makeApi();
    api.post.mockRejectedValue(new ApiError(409, 'x', { error: { code: 'estoque_insuficiente', message: 'x' } }));
    const hooks = createInventoryHooks(api);
    const { result } = renderHook(() => hooks.useStockMutations(), { wrapper: wrapperFor() });
    const err = await result.current.transfer.mutateAsync({ item_id: 'i', from_warehouse_id: 'a', to_warehouse_id: 'b', qty: '1' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(inventoryErrorMessage(err)).toBe('Estoque disponível insuficiente.');
    expect(inventoryErrorMessage(new ApiError(500, 'boom', {}))).toContain('boom');
  });

  it('warehouse mutations invalidate the warehouse list', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { id: 'w' } });
    const client = makeClient();
    client.setQueryData([...inventoryKeys.warehouses, {}], []);
    const hooks = createInventoryHooks(api);
    const { result } = renderHook(() => hooks.useWarehouseMutations(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.create.mutateAsync({ name: 'A', code: 'A' });
    });
    expect(client.getQueryState([...inventoryKeys.warehouses, {}])?.isInvalidated).toBe(true);
  });
});
