import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { createQuotesHooks, createQuotesPublicHooks, listQuery, quotesErrorMessage, quotesKeys } from './hooks';
import { makeApi, makeClient, page, publicView, quote, wrapperFor } from './testUtils';

afterEach(cleanup);

describe('listQuery', () => {
  it('drops empty filters and maps include_versions', () => {
    expect(listQuery({ q: '  ', status: '', page: 2, page_size: 10 })).toEqual({ page: 2, page_size: 10 });
    expect(listQuery({ q: ' ORC ', status: 'sent', party_id: 'p', include_versions: true })).toEqual({ q: 'ORC', status: 'sent', party_id: 'p', include_versions: true });
  });
});

describe('staff hooks', () => {
  it('list: skeleton first, data after, two-signal loading', async () => {
    const api = makeApi({ 'GET /api/quotes': page([quote()]) });
    const { result } = renderHook(() => createQuotesHooks(api).useQuotes({}), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);
  });

  it('a refetch over data is isRefreshing, not a skeleton', async () => {
    const api = makeApi({ 'GET /api/quotes': page([quote()]) });
    const { result } = renderHook(() => createQuotesHooks(api).useQuotes({}), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    act(() => { void result.current.refetch(); });
    expect(result.current.showSkeleton).toBe(false);
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('by-id is disabled without an id (idle is not a skeleton) and has no placeholderData across ids', async () => {
    const api = makeApi({ 'GET /api/quotes/a': { data: quote({ id: 'a' }) }, 'GET /api/quotes/b': { data: quote({ id: 'b' }) } });
    const hooks = createQuotesHooks(api);
    const idle = renderHook(() => hooks.useQuote(null), { wrapper: wrapperFor() });
    expect(idle.result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
    const { result, rerender } = renderHook(({ id }) => hooks.useQuote(id), { wrapper: wrapperFor(), initialProps: { id: 'a' } });
    await waitFor(() => expect(result.current.data?.id).toBe('a'));
    rerender({ id: 'b' });
    expect(result.current.data).toBeUndefined();            // never another quote's data under the new key
    await waitFor(() => expect(result.current.data?.id).toBe('b'));
  });

  it('mutations unwrap the envelope, hit the right route and invalidate the lists + that quote', async () => {
    const api = makeApi({
      'POST /api/quotes': { data: quote() },
      'PATCH /api/quotes/q1': { data: quote({ title: 'Novo' }) },
      'POST /api/quotes/q1/versions': { data: quote({ id: 'q2', version: 2 }) },
      'POST /api/quotes/q1/send': { data: { quote: quote(), channel: 'link', url: 'https://x/y', sent_to: null } },
      'POST /api/quotes/q1/accept': { data: quote({ status: 'accepted' }) },
      'POST /api/quotes/q1/reject': { data: quote({ status: 'rejected' }) },
      'POST /api/quotes/q1/convert': { data: quote() },
      'DELETE /api/quotes/q1': null,
      'POST /api/quotes/calculate': { data: { subtotal_cents: 1, discount_cents: 0, total_cents: 1, lines: [], effective_convert_to: 'none' } },
    });
    const client = makeClient();
    const spy = client.invalidateQueries.bind(client);
    const keys: unknown[] = [];
    client.invalidateQueries = ((f: { queryKey: unknown }) => { keys.push(f.queryKey); return spy(f as never); }) as never;
    const { result } = renderHook(() => createQuotesHooks(api).useQuoteMutations(), { wrapper: wrapperFor(client) });
    await act(async () => {
      expect((await result.current.create.mutateAsync({ party_id: 'p1', lines: [] })).id).toBe('q1');
      expect((await result.current.update.mutateAsync({ id: 'q1', title: 'Novo' })).title).toBe('Novo');
      expect((await result.current.newVersion.mutateAsync({ id: 'q1' })).version).toBe(2);
      expect((await result.current.send.mutateAsync({ id: 'q1', channel: 'link' })).url).toBe('https://x/y');
      await result.current.accept.mutateAsync({ id: 'q1', signer_name: 'Ana Souza' });
      await result.current.reject.mutateAsync({ id: 'q1', reason: 'caro' });
      await result.current.convert.mutateAsync('q1');
      await result.current.remove.mutateAsync('q1');
      await result.current.calculate.mutateAsync({ lines: [] });
    });
    expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/accept', { signer_name: 'Ana Souza' });
    expect(api.post).toHaveBeenCalledWith('/api/quotes/q1/versions', {});
    expect(keys).toContainEqual(quotesKeys.lists);
    expect(keys).toContainEqual(quotesKeys.detail('q1'));
  });

  it('a refusal rejects with the ApiError (never swallowed) and maps to pt-BR copy', async () => {
    const err = new ApiError(409, 'blocked', { error: { code: 'orcamento_bloqueado' } });
    const api = makeApi({ 'PATCH /api/quotes/q1': () => { throw err; } });
    const { result } = renderHook(() => createQuotesHooks(api).useQuoteMutations(), { wrapper: wrapperFor() });
    await act(async () => {
      await expect(result.current.update.mutateAsync({ id: 'q1', title: 'x' })).rejects.toBe(err);
    });
    expect(quotesErrorMessage(Object.assign(new ApiError(409, 'x', { error: { code: 'orcamento_bloqueado' } }))).length).toBeGreaterThan(0);
    expect(quotesErrorMessage(new Error('rede caiu'))).toBe('rede caiu');
  });

  it('pdfUrl points at the staff route', () => {
    expect(createQuotesHooks(makeApi()).pdfUrl('q1')).toBe('/api/quotes/q1/pdf');
  });
});

describe('public hooks', () => {
  it('reads the view with the token in the path and settles the cache from a decision', async () => {
    const api = makeApi({
      'GET /api/public/quotes/tok': { data: publicView() },
      'POST /api/public/quotes/tok/accept': { data: publicView({ status: 'accepted', can_decide: false, decision: { decision: 'accepted', decided_at: '2026-10-14T10:00:00Z' } }) },
    });
    const hooks = createQuotesPublicHooks(api, { apiBase: 'https://api.test/' });
    const { result } = renderHook(() => ({ view: hooks.usePublicQuote('tok'), dec: hooks.usePublicDecision('tok') }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.view.data?.can_decide).toBe(true));
    await act(async () => { await result.current.dec.accept.mutateAsync({ name: 'Ana Souza', agree: true }); });
    expect(api.post).toHaveBeenCalledWith('/api/public/quotes/tok/accept', { name: 'Ana Souza', agree: true });
    await waitFor(() => expect(result.current.view.data?.decision?.decision).toBe('accepted'));
    expect(hooks.pdfUrl('tok')).toBe('https://api.test/api/public/quotes/tok/pdf');
  });

  it('a 404 link is an answer, not a transient fault: it is asked once', async () => {
    const api = makeApi({ 'GET /api/public/quotes/bad': () => { throw new ApiError(404, 'x', { error: { code: 'link_invalido' } }); } });
    const hooks = createQuotesPublicHooks(api);
    const client = makeClient();
    client.setDefaultOptions({ queries: { retry: undefined as never } });
    const { result } = renderHook(() => hooks.usePublicQuote('bad'), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('no token, no request', () => {
    const api = makeApi();
    renderHook(() => createQuotesPublicHooks(api).usePublicQuote(null), { wrapper: wrapperFor() });
    expect(api.get).not.toHaveBeenCalled();
  });
});
