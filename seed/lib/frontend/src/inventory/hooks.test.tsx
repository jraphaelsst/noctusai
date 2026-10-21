/** Hook factory: two-signal loading, placeholderData on key change, invalidation after stock mutations, error mapping. */
import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { createInventoryHooks, inventoryErrorMessage, inventoryKeys } from './hooks';
import { ITEM, WH1, WH2, balance, makeApi, makeClient, move, page, warehouse, wrapperFor } from './testUtils';

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

describe('cache writes (KB § PATTERNS/frontend/mutation-cache-writes.md)', () => {
  const pending = () => new Promise<never>(() => undefined);

  it('a receive puts the server\'s post-move numbers into the balance rows before any refetch', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: { status: 'ok', moves: [move({ on_hand_after: 25, reserved_after: 2, avg_cost_after_cents: 200 })] } });
    api.get.mockReturnValue(pending()); // every refetch hangs: what is on screen must already be right
    const client = makeClient();
    const key = [...inventoryKeys.balances, { page: 1 }];
    client.setQueryData(key, page([balance(), balance({ item_id: 'other', on_hand: 1, available: 1 })]));
    const { result } = renderHook(() => createInventoryHooks(api).useStockMutations(), { wrapper: wrapperFor(client) });

    await act(async () => void (await result.current.receive.mutateAsync({ item_id: ITEM, warehouse_id: WH1, qty: '15', unit_cost_cents: 200 })));
    const rows = client.getQueryData<{ data: ReturnType<typeof balance>[] }>(key)!.data;
    expect(rows[0]).toMatchObject({ on_hand: 25, reserved: 2, available: 23, avg_cost_cents: 200, value_cents: 5000 });
    expect(rows[1].on_hand).toBe(1); // a row the move did not touch is left alone
  });

  it('a transfer updates both warehouses\' rows', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({
      data: { status: 'ok', moves: [move({ warehouse_id: WH1, on_hand_after: 4 }), move({ id: 'm2', warehouse_id: WH2, on_hand_after: 6 })] },
    });
    api.get.mockReturnValue(pending());
    const client = makeClient();
    const key = [...inventoryKeys.balances, {}];
    client.setQueryData(key, page([balance({ warehouse_id: WH1 }), balance({ warehouse_id: WH2, on_hand: 0 })]));
    const { result } = renderHook(() => createInventoryHooks(api).useStockMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.transfer.mutateAsync({ item_id: ITEM, from_warehouse_id: WH1, to_warehouse_id: WH2, qty: '6' })));
    expect(client.getQueryData<{ data: { on_hand: number }[] }>(key)!.data.map((r) => r.on_hand)).toEqual([4, 6]);
  });

  it('setMinQty writes the new minimum into the row; the low-stock flag stays the server\'s to decide', async () => {
    const api = makeApi();
    api.put.mockResolvedValue({ data: { item_id: ITEM, warehouse_id: WH1, min_qty: 12 } });
    api.get.mockReturnValue(pending());
    const client = makeClient();
    const key = [...inventoryKeys.balances, {}];
    client.setQueryData(key, page([balance()]));
    const { result } = renderHook(() => createInventoryHooks(api).useStockMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.setMinQty.mutateAsync({ item_id: ITEM, warehouse_id: WH1, min_qty: '12' })));
    expect(client.getQueryData<{ data: { min_qty: number }[] }>(key)!.data[0].min_qty).toBe(12);
  });

  it('warehouse create commits the server row into the unfiltered + active lists; update is drawn on the click', async () => {
    const api = makeApi();
    let resolvePatch!: (v: unknown) => void;
    api.post.mockResolvedValue({ data: warehouse({ id: 'w2', name: 'Filial', code: 'FIL' }) });
    api.patch.mockReturnValue(new Promise((r) => (resolvePatch = r)));
    api.get.mockReturnValue(pending());
    const client = makeClient();
    const all = [...inventoryKeys.warehouses, {}];
    const inactive = [...inventoryKeys.warehouses, { active: false }];
    client.setQueryData(all, [warehouse()]);
    client.setQueryData([...inventoryKeys.warehouses, { active: true }], [warehouse()]);
    client.setQueryData(inactive, []);
    const { result } = renderHook(() => createInventoryHooks(api).useWarehouseMutations(), { wrapper: wrapperFor(client) });

    await act(async () => void (await result.current.create.mutateAsync({ name: 'Filial', code: 'FIL' })));
    expect(client.getQueryData<{ id: string }[]>(all)!.map((w) => w.id)).toEqual([WH1, 'w2']);
    expect(client.getQueryData<unknown[]>(inactive)).toHaveLength(0); // a filter the new row does not satisfy is not touched

    act(() => void result.current.update.mutate({ id: 'w2', name: 'Filial 2' }));
    await waitFor(() => expect(client.getQueryData<{ name: string }[]>(all)![1].name).toBe('Filial 2'));
    await act(async () => resolvePatch({ data: warehouse({ id: 'w2', name: 'Filial 2' }) }));
  });
});
