/**
 * Hook factory tests — two-signal loading contract, placeholderData on key change (and its deliberate
 * absence on id-keyed detail), request shapes (paths, params, bodies, multipart), invalidation after
 * money-moving mutations, downloads, and the fetch transport.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { createFinanceHooks, createFinanceTransport, financeKeys } from './hooks';
import { ACC_BANK, entry, makeClient, makeRoutedApi, ok, page, wrapperFor } from './testUtils';
import { ApiError } from '../api';

afterEach(cleanup);

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeRoutedApi({ 'GET /api/finance/entries': () => new Promise((r) => (resolve = r)) });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useEntries({}), { wrapper: wrapperFor() });

    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);
    await act(async () => resolve(page([entry()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.route('GET /api/finance/entries', () => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await act(async () => resolve2(page([entry(), entry({ id: 'e2' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.data?.data).toHaveLength(2);
  });

  it('list keeps previous rows while the filter key changes (placeholderData)', async () => {
    let resolve2!: (v: unknown) => void;
    const api = makeRoutedApi({ 'GET /api/finance/entries': page([entry()]) });
    const hooks = createFinanceHooks(api);
    const { result, rerender } = renderHook(({ status }: { status: 'open' | 'paid' }) => hooks.useEntries({ status }), {
      wrapper: wrapperFor(),
      initialProps: { status: 'open' as 'open' | 'paid' },
    });
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    api.route('GET /api/finance/entries', () => new Promise((r) => (resolve2 = r)));
    rerender({ status: 'paid' });
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data?.data).toHaveLength(1);
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    await act(async () => resolve2(page([])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(0));
  });

  it('id-keyed entry detail never shows another entry (no placeholderData) and is idle without id', async () => {
    const api = makeRoutedApi({
      'GET /api/finance/entries/a': ok({ ...entry({ id: 'a', description: 'A' }), settlements: [], attachments: [] }),
      'GET /api/finance/entries/b': () => new Promise(() => {}),
    });
    const hooks = createFinanceHooks(api);
    const { result, rerender } = renderHook(({ id }: { id: string | null }) => hooks.useEntry(id), {
      wrapper: wrapperFor(),
      initialProps: { id: null as string | null },
    });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
    rerender({ id: 'a' });
    await waitFor(() => expect(result.current.data?.description).toBe('A'));
    rerender({ id: 'b' });
    expect(result.current.data).toBeUndefined();
    expect(result.current.showSkeleton).toBe(true);
  });

  it('surfaces errors instead of swallowing them', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/accounts': () => Promise.reject(new ApiError(500, 'down')) });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useAccounts(), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.error).toBeInstanceOf(ApiError);
  });
});

describe('request shapes', () => {
  it('unwraps {data} envelopes and sends list params', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/accounts': ok([ACC_BANK]) });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useAccounts({ active: true }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toEqual([ACC_BANK]));
    expect(api.get).toHaveBeenCalledWith('/api/finance/accounts', { active: true });
  });

  it('balances: one request per account, keyed by id', async () => {
    const api = makeRoutedApi({
      'GET /api/finance/accounts/a1/balance': ok({ account_id: 'a1', on: 'x', opening_balance_cents: 0, movement_cents: 5, balance_cents: 5 }),
      'GET /api/finance/accounts/a2/balance': ok({ account_id: 'a2', on: 'x', opening_balance_cents: 0, movement_cents: 9, balance_cents: 9 }),
    });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useAccountBalances(['a1', 'a2']), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(Object.keys(result.current.byId)).toEqual(['a1', 'a2']));
    expect(result.current.byId.a2.balance_cents).toBe(9);
    expect(result.current.showSkeleton).toBe(false);
  });

  it('report hooks hit the contract paths', async () => {
    const api = makeRoutedApi({
      'GET /api/finance/reports/cashflow': ok({ buckets: [] }),
      'GET /api/finance/reports/aging': ok({ counterparties: [] }),
      'GET /api/finance/reports/dre': ok({ lines: [] }),
      'GET /api/finance/reports/simples-base': ok({ months: [] }),
      'GET /api/finance/accountant-checklist': ok({ items: [], exports: [] }),
      'GET /api/finance/dre-settings': ok({ tax_regime: 'unknown' }),
    });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(
      () => ({
        c: hooks.useCashflow({ from: '2026-10-01', to: '2027-03-31', account_id: 'a1' }),
        a: hooks.useAging('2026-10-14'),
        d: hooks.useDre({ from: '2026-01-01', to: '2026-10-14', view: 'managerial' }),
        s: hooks.useSimplesBase({ from: '2026-10-01' }),
        k: hooks.useAccountantChecklist(),
        g: hooks.useDreSettings(),
      }),
      { wrapper: wrapperFor() },
    );
    await waitFor(() => expect(Object.values(result.current).every((q) => !!q.data)).toBe(true));
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/cashflow', { from: '2026-10-01', to: '2027-03-31', account_id: 'a1' });
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/aging', { as_of: '2026-10-14' });
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/dre', { from: '2026-01-01', to: '2026-10-14', view: 'managerial' });
  });
});

describe('mutations', () => {
  it('settle posts to the entry settlements path and refreshes entries, balances and reports', async () => {
    const api = makeRoutedApi({ 'POST /api/finance/entries/e1/settlements': ok({ settlement: {}, entry: entry(), replayed: false }) });
    const client = makeClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useEntryMutations(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.settle.mutateAsync({ id: 'e1', account_id: 'a1', amount_cents: 500 });
    });
    expect(api.post).toHaveBeenCalledWith('/api/finance/entries/e1/settlements', { account_id: 'a1', amount_cents: 500 });
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(financeKeys.entries);
    expect(keys).toContainEqual(['finance', 'balance']);
    expect(keys).toContainEqual(financeKeys.reports);
  });

  it('reverse sends only the reason; create answers a list; rejects with ApiError', async () => {
    const api = makeRoutedApi({
      'POST /api/finance/settlements/s1/reverse': ok({ settlement: {}, entry: entry() }),
      'POST /api/finance/entries': () => Promise.reject(new ApiError(422, 'x', { error: { code: 'categoria_inativa', message: 'x' } })),
    });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => hooks.useEntryMutations(), { wrapper: wrapperFor() });
    await act(async () => {
      await result.current.reverse.mutateAsync({ settlementId: 's1', reason: 'engano' });
    });
    expect(api.post).toHaveBeenCalledWith('/api/finance/settlements/s1/reverse', { reason: 'engano' });
    await act(async () => {
      await expect(
        result.current.create.mutateAsync({ direction: 'receivable', description: 'x', due_date: '2026-10-20', amount_cents: 1 }),
      ).rejects.toMatchObject({ code: 'categoria_inativa' });
    });
  });

  it('attachments upload as multipart under `file`; statements as account_id + file + column_map', async () => {
    const api = makeRoutedApi({
      'UPLOAD /api/finance/entries/e1/attachments': ok({ id: 'att' }),
      'UPLOAD /api/finance/statements': ok({ import: { id: 'i1' }, lines: 1, duplicates_skipped: 0, skipped_zero: 0, suggested: 0 }),
    });
    const hooks = createFinanceHooks(api);
    const { result } = renderHook(() => ({ att: hooks.useAttachmentMutations('e1'), rec: hooks.useReconciliationMutations() }), { wrapper: wrapperFor() });
    const file = new File(['%PDF-'], 'nota.pdf', { type: 'application/pdf' });
    await act(async () => {
      await result.current.att.upload.mutateAsync(file);
      await result.current.rec.importStatement.mutateAsync({ account_id: 'a1', file, format: 'csv', column_map: { date: 'Data', description: 'Histórico', amount: 'Valor' } });
    });
    const form1 = api.upload.mock.calls[0][1] as FormData;
    expect((form1.get('file') as File).name).toBe('nota.pdf');
    const form2 = api.upload.mock.calls[1][1] as FormData;
    expect(form2.get('account_id')).toBe('a1');
    expect(form2.get('format')).toBe('csv');
    expect(JSON.parse(form2.get('column_map') as string)).toEqual({ date: 'Data', description: 'Histórico', amount: 'Valor' });
  });

  it('export downloads the blob with the query string and saves it', async () => {
    const api = makeRoutedApi();
    const click = vi.fn();
    const create = vi.fn(() => 'blob:x');
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const orig = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = click;
    try {
      const hooks = createFinanceHooks(api);
      const { result } = renderHook(() => hooks.useExport(), { wrapper: wrapperFor() });
      await act(async () => {
        await result.current.mutateAsync({ path: '/api/finance/exports/entries.csv', params: { from: '2026-10-01', status: '' }, filename: 'lancamentos.csv' });
      });
      expect(api.download).toHaveBeenCalledWith('/api/finance/exports/entries.csv?from=2026-10-01');
      expect(click).toHaveBeenCalled();
      expect(revoke).toHaveBeenCalledWith('blob:x');
    } finally {
      HTMLAnchorElement.prototype.click = orig;
    }
  });
});

describe('fetch transport (base URL)', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('GETs with params, throws ApiError carrying the body, downloads blobs', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'x', message: 'Sem acesso' } }), { status: 403 }))
      .mockResolvedValueOnce(new Response('a,b', { status: 200 }))
      .mockResolvedValueOnce(new Response('no', { status: 403 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createFinanceTransport('https://api.test/');
    await api.get('/api/finance/accounts', { active: true, q: '' });
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.test/api/finance/accounts?active=true');
    await expect(api.get('/api/finance/accounts')).rejects.toMatchObject({ status: 403 });
    const blob = await api.download('/api/finance/exports/entries.csv');
    expect(blob.size).toBe(3);
    await expect(api.download('/api/finance/exports/ledger.ofx')).rejects.toMatchObject({ status: 403 });
    vi.unstubAllGlobals();
  });
});
