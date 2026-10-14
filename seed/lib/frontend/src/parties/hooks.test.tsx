/**
 * Hook factory tests — two-signal loading contract, placeholderData on key change (and its deliberate
 * absence on the by-id read), invalidation after mutations, query-string mapping, import / export transport.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { createPartiesHooks, listQuery, partiesKeys } from './hooks';
import { makeApi, makeClient, page, party, wrapperFor } from './testUtils';
import { ApiError } from '../api';

afterEach(cleanup);

describe('listQuery', () => {
  it('maps filters to the wire and drops the empty ones', () => {
    expect(listQuery({ q: ' ana ', kind: 'PF', role: 'supplier', active: 'archived', page: 2, page_size: 50 })).toEqual({
      q: 'ana', kind: 'PF', role: 'supplier', active: false, page: 2, page_size: 50,
    });
    expect(listQuery({ q: '', kind: '', role: '', active: 'all' })).toEqual({});
    expect(listQuery({ active: 'active' })).toEqual({ active: true });
  });
});

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(() => hooks.useParties({}), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => resolve(page([party()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false); // data stays on screen while refreshing
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([party(), party({ id: 'p2' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a list key change keeps the previous page (placeholderData) instead of a skeleton flash', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([party({ id: 'a' })]));
    const hooks = createPartiesHooks(api);
    const { result, rerender } = renderHook(({ p }) => hooks.useParties({ page: p }), { wrapper: wrapperFor(), initialProps: { p: 1 } });
    await waitFor(() => expect(result.current.data?.data[0].id).toBe('a'));

    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    rerender({ p: 2 });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data[0].id).toBe('a');
    expect(result.current.isRefreshing).toBe(true);
    await act(async () => resolve(page([party({ id: 'b' })])));
    await waitFor(() => expect(result.current.data?.data[0].id).toBe('b'));
  });

  it('a disabled by-id query (no id) is not a skeleton', () => {
    const hooks = createPartiesHooks(makeApi());
    const { result } = renderHook(() => hooks.useParty(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
  });

  it('the by-id read does not leak the previous person under a new key', async () => {
    const api = makeApi();
    api.get.mockResolvedValueOnce({ data: party({ id: 'c1', legal_name: 'Ana' }) });
    const hooks = createPartiesHooks(api);
    const { result, rerender } = renderHook(({ id }) => hooks.useParty(id), { wrapper: wrapperFor(), initialProps: { id: 'c1' } });
    await waitFor(() => expect(result.current.data?.legal_name).toBe('Ana'));
    api.get.mockImplementationOnce(() => new Promise(() => {}));
    rerender({ id: 'c2' });
    await waitFor(() => expect(result.current.showSkeleton).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('exposes the error and a retry, never swallows it', async () => {
    const api = makeApi();
    api.get.mockRejectedValueOnce(new ApiError(500, 'boom'));
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(() => hooks.useParties({}), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    api.get.mockResolvedValueOnce(page([party()]));
    await act(async () => void result.current.refetch());
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
  });
});

describe('requests', () => {
  it('lists with the mapped query string', async () => {
    const api = makeApi();
    api.get.mockResolvedValue(page([]));
    const hooks = createPartiesHooks(api);
    renderHook(() => hooks.useParties({ q: 'x', role: 'carrier', active: 'active' }), { wrapper: wrapperFor() });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/parties', { q: 'x', role: 'carrier', active: true }));
  });

  it('create / update / roles / archive / restore / delete hit the right endpoints and refresh the lists', async () => {
    const api = makeApi();
    api.post.mockResolvedValue({ data: party() });
    api.patch.mockResolvedValue({ data: party() });
    api.put.mockResolvedValue({ data: party() });
    api.delete.mockResolvedValue(undefined);
    const client = makeClient();
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(
      () => ({
        c: hooks.useCreateParty(), u: hooks.useUpdateParty(), r: hooks.useSetRoles(), a: hooks.useArchiveParty(), d: hooks.useDeleteParty(),
      }),
      { wrapper: wrapperFor(client) },
    );
    const invalidated: unknown[] = [];
    const orig = client.invalidateQueries.bind(client);
    client.invalidateQueries = ((f: { queryKey: unknown }) => (invalidated.push(f.queryKey), orig(f as never))) as typeof client.invalidateQueries;

    await act(async () => void (await result.current.c.mutateAsync({ kind: 'PF', legal_name: 'Ana' })));
    expect(api.post).toHaveBeenLastCalledWith('/api/parties', { kind: 'PF', legal_name: 'Ana' });
    expect(invalidated).toContainEqual(partiesKeys.lists);

    await act(async () => void (await result.current.u.mutateAsync({ id: 'p1', trade_name: 'Aninha' })));
    expect(api.patch).toHaveBeenLastCalledWith('/api/parties/p1', { trade_name: 'Aninha' });
    expect(invalidated).toContainEqual(partiesKeys.detail('p1'));

    await act(async () => void (await result.current.r.mutateAsync({ id: 'p1', roles: ['supplier'] })));
    expect(api.put).toHaveBeenLastCalledWith('/api/parties/p1/roles', { roles: ['supplier'] });

    await act(async () => void (await result.current.a.mutateAsync({ id: 'p1', restore: false })));
    expect(api.post).toHaveBeenLastCalledWith('/api/parties/p1/archive', {});
    await act(async () => void (await result.current.a.mutateAsync({ id: 'p1', restore: true })));
    expect(api.post).toHaveBeenLastCalledWith('/api/parties/p1/restore', {});

    await act(async () => void (await result.current.d.mutateAsync('p1')));
    expect(api.delete).toHaveBeenLastCalledWith('/api/parties/p1');
  });

  it('a failed mutation rejects with the ApiError (never swallowed)', async () => {
    const api = makeApi();
    api.post.mockRejectedValue(new ApiError(409, 'dup', { error: { code: 'documento_duplicado' } }));
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(() => hooks.useCreateParty(), { wrapper: wrapperFor() });
    await act(async () => {
      await expect(result.current.mutateAsync({ kind: 'PF', legal_name: 'x' })).rejects.toMatchObject({ code: 'documento_duplicado', status: 409 });
    });
  });

  it('import uploads multipart with the dry_run flag; only a real import refreshes the lists', async () => {
    const api = makeApi();
    api.upload.mockResolvedValue({ data: { dry_run: true, created: 2, skipped: [], errors: [] } });
    const client = makeClient();
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(() => hooks.useImportParties(), { wrapper: wrapperFor(client) });
    const spy: unknown[] = [];
    const orig = client.invalidateQueries.bind(client);
    client.invalidateQueries = ((f: { queryKey: unknown }) => (spy.push(f.queryKey), orig(f as never))) as typeof client.invalidateQueries;

    const file = new File(['kind,legal_name\nPF,Ana\n'], 'p.csv', { type: 'text/csv' });
    await act(async () => void (await result.current.mutateAsync({ file, dryRun: true })));
    const [path, form] = api.upload.mock.calls[0] as [string, FormData];
    expect(path).toBe('/api/parties/import');
    expect(form.get('dry_run')).toBe('true');
    expect((form.get('file') as File).name).toBe('p.csv');
    expect(spy).toEqual([]);

    api.upload.mockResolvedValue({ data: { dry_run: false, created: 2, skipped: [], errors: [] } });
    await act(async () => void (await result.current.mutateAsync({ file })));
    expect((api.upload.mock.calls[1][1] as FormData).get('dry_run')).toBe('false');
    expect(spy).toContainEqual(partiesKeys.lists);
  });

  it('export downloads with the list filters but without paging', async () => {
    const api = makeApi();
    const blob = new Blob(['x']);
    api.download.mockResolvedValue(blob);
    const hooks = createPartiesHooks(api);
    const { result } = renderHook(() => hooks.useExportParties(), { wrapper: wrapperFor() });
    let got: Blob | undefined;
    await act(async () => void (got = await result.current.mutateAsync({ role: 'supplier', active: 'active', page: 3, page_size: 20 })));
    expect(got).toBe(blob);
    expect(api.download).toHaveBeenCalledWith('/api/parties/export.csv?role=supplier&active=true');
    await act(async () => void (await result.current.mutateAsync({})));
    expect(api.download).toHaveBeenLastCalledWith('/api/parties/export.csv');
  });
});
