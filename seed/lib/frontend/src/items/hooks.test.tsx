/** Hook factory: two-signal loading, placeholderData on key change, invalidation, CSV transport, error helpers. */
import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { createItemsHooks, itemsKeys, apiFieldError, importRowErrors } from './hooks';
import { item, makeApi, makeClient, page, wrapperFor } from './testUtils';
import { ApiError } from '../api';

afterEach(cleanup);

describe('useItems — two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createItemsHooks(api);
    const { result } = renderHook(() => hooks.useItems({}), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => resolve(page([item()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([item(), item({ id: 'i2' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a filter/page key change keeps the previous page instead of an empty/skeleton flash', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([item({ id: 'a' })]));
    const hooks = createItemsHooks(api);
    const { result, rerender } = renderHook(({ p }) => hooks.useItems({ page: p }), { wrapper: wrapperFor(), initialProps: { p: 1 } });
    await waitFor(() => expect(result.current.data?.data[0].id).toBe('a'));

    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    rerender({ p: 2 });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data[0].id).toBe('a');
    expect(result.current.isRefreshing).toBe(true);
    await act(async () => resolve(page([item({ id: 'b' })])));
    await waitFor(() => expect(result.current.data?.data[0].id).toBe('b'));
  });

  it('sends only the set filters', async () => {
    const api = makeApi();
    api.get.mockResolvedValue(page([]));
    const hooks = createItemsHooks(api);
    renderHook(() => hooks.useItems({ q: 'par', item_type: 'goods', active: 'false', category_id: '' }), { wrapper: wrapperFor() });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(api.get).toHaveBeenCalledWith('/api/items', { page: 1, page_size: 20, q: 'par', item_type: 'goods', active: 'false' });
  });
});

describe('useItem', () => {
  it('stays idle (no skeleton, no request) without an id', () => {
    const api = makeApi();
    const hooks = createItemsHooks(api);
    const { result } = renderHook(() => hooks.useItem(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });
  it('unwraps the {data} envelope', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: item({ id: 'x' }) });
    const hooks = createItemsHooks(api);
    const { result } = renderHook(() => hooks.useItem('x'), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data?.id).toBe('x'));
    expect(api.get).toHaveBeenCalledWith('/api/items/x');
  });
});

describe('mutations', () => {
  it('create/update/archive hit the right routes and invalidate the item queries', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: item() });
    api.patch.mockResolvedValue({ data: item({ name: 'N' }) });
    const hooks = createItemsHooks(api);
    const client = makeClient();
    const seen: unknown[] = [];
    client.getQueryCache().subscribe((e) => e.type === 'updated' && seen.push(e.query.queryKey));
    client.setQueryData(itemsKeys.list, page([item()]));
    const { result } = renderHook(() => hooks.useItemMutations(), { wrapper: wrapperFor(client) });

    await act(async () => void (await result.current.create.mutateAsync({ sku: 'A', name: 'A' })));
    expect(api.post).toHaveBeenCalledWith('/api/items', { sku: 'A', name: 'A' });
    await act(async () => void (await result.current.update.mutateAsync({ id: 'i1', name: 'N' })));
    expect(api.patch).toHaveBeenCalledWith('/api/items/i1', { name: 'N' });
    await act(async () => void (await result.current.archive.mutateAsync('i1')));
    expect(api.post).toHaveBeenCalledWith('/api/items/i1/archive');
    await act(async () => void (await result.current.unarchive.mutateAsync('i1')));
    expect(api.post).toHaveBeenCalledWith('/api/items/i1/unarchive');
    expect(client.getQueryState(itemsKeys.list)?.isInvalidated).toBe(true);
  });

  it('a rejected mutation surfaces the ApiError', async () => {
    const api = makeApi();
    api.post.mockRejectedValue(new ApiError(409, 'Já existe um item com este SKU.', { error: { code: 'sku_duplicado', message: 'Já existe um item com este SKU.', details: { } } }));
    const hooks = createItemsHooks(api);
    const { result } = renderHook(() => hooks.useItemMutations(), { wrapper: wrapperFor() });
    await act(async () => {
      await expect(result.current.create.mutateAsync({ sku: 'A', name: 'A' })).rejects.toMatchObject({ status: 409 });
    });
    await waitFor(() => expect(result.current.create.error).toBeTruthy());
  });
});

describe('CSV', () => {
  it('export downloads a blob from the filtered export route', async () => {
    const api = makeApi();
    const blob = new Blob(['sku\n']);
    api.download.mockResolvedValue(blob);
    const hooks = createItemsHooks(api);
    const { result } = renderHook(() => hooks.useExportItems(), { wrapper: wrapperFor() });
    let out: Blob | undefined;
    await act(async () => void (out = await result.current.mutateAsync({ q: 'par', active: 'true', category_id: '' })));
    expect(out).toBe(blob);
    expect(api.download).toHaveBeenCalledWith('/api/items/export.csv?q=par&active=true');
  });

  it('import uploads multipart with the flags; a real import invalidates, a dry run does not', async () => {
    const api = makeApi();
    api.upload.mockResolvedValueOnce({ data: { created: 1, updated: 0, dry_run: true } });
    api.upload.mockResolvedValueOnce({ data: { created: 1, updated: 0, dry_run: false } });
    const hooks = createItemsHooks(api);
    const client = makeClient();
    client.setQueryData(itemsKeys.list, page([item()]));
    const { result } = renderHook(() => hooks.useImportItems(), { wrapper: wrapperFor(client) });
    const file = new File(['sku,name\nA,a\n'], 'itens.csv', { type: 'text/csv' });

    await act(async () => void (await result.current.mutateAsync({ file, dryRun: true })));
    const form = api.upload.mock.calls[0][1] as FormData;
    expect(api.upload.mock.calls[0][0]).toBe('/api/items/import');
    expect([form.get('update_existing'), form.get('dry_run')]).toEqual(['false', 'true']);
    expect((form.get('file') as File).name).toBe('itens.csv');
    expect(client.getQueryState(itemsKeys.list)?.isInvalidated).toBe(false);

    await act(async () => void (await result.current.mutateAsync({ file, updateExisting: true })));
    expect(client.getQueryState(itemsKeys.list)?.isInvalidated).toBe(true);
  });
});

describe('error helpers', () => {
  it('apiFieldError reads error.details.field', () => {
    const err = new ApiError(422, 'x', { error: { code: 'gtin_invalido', message: 'GTIN inválido', details: { field: 'gtin' } } });
    expect(apiFieldError(err)).toEqual({ field: 'gtin', code: 'gtin_invalido', message: 'GTIN inválido' });
    expect(apiFieldError(new Error('boom'))).toBeNull();
  });
  it('importRowErrors only for importacao_invalida with a list', () => {
    const rows = [{ line: 2, field: 'ncm', code: 'ncm_invalido', message: 'NCM inválido' }];
    const err = new ApiError(422, 'x', { error: { code: 'importacao_invalida', details: { errors: rows, error_count: 3 } } });
    expect(importRowErrors(err)).toEqual({ rows, total: 3 });
    expect(importRowErrors(new ApiError(422, 'x', { error: { code: 'outro' } }))).toBeNull();
  });
});
