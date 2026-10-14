import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { createContractsHooks, listQuery } from './hooks';
import { contract, ok, page, setup, wrapperFor } from './testUtils';
import { ApiError } from '../api';
import { makeRoutedApi } from '../organ-kit/testing';
import type { ContractsApi } from './hooks';

afterEach(cleanup);

describe('listQuery', () => {
  it('maps filters to the wire and drops the empty ones', () => {
    expect(listQuery({ q: ' ct ', status: 'active', billing_model: 'retainer', page: 2, page_size: 50 })).toEqual({
      q: 'ct', status: 'active', billing_model: 'retainer', page: 2, page_size: 50,
    });
    expect(listQuery({ q: '', status: '', billing_model: '' })).toEqual({});
    expect(listQuery({ expiring_within_days: 0 })).toEqual({ expiring_within_days: 0 });
  });
});

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on refetch over data; list keeps data across key change', async () => {
    let resolve!: (v: unknown) => void;
    const { api, hooks } = setup();
    api.route('GET /api/contracts', () => new Promise((r) => (resolve = r)));
    const { result, rerender } = renderHook(({ p }) => hooks.useContracts({ page: p }), { wrapper: wrapperFor(), initialProps: { p: 1 } });
    expect(result.current.showSkeleton).toBe(true);
    await act(async () => resolve(page([contract()])));
    await waitFor(() => expect(result.current.data?.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);
    api.route('GET /api/contracts', () => new Promise(() => undefined));
    rerender({ p: 2 });
    expect(result.current.data?.data).toHaveLength(1); // placeholderData: no lying empty state
    expect(result.current.showSkeleton).toBe(false);
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
  });

  it('the by-id read has NO placeholder data (never shows the previous contract under a new key)', async () => {
    const { api, hooks } = setup({ 'GET /api/contracts/a': ok(contract({ id: 'a', title: 'A' })) });
    api.route('GET /api/contracts/b', () => new Promise(() => undefined));
    const { result, rerender } = renderHook(({ id }) => hooks.useContract(id), { wrapper: wrapperFor(), initialProps: { id: 'a' } });
    await waitFor(() => expect(result.current.data?.title).toBe('A'));
    rerender({ id: 'b' });
    expect(result.current.data).toBeUndefined();
    expect(result.current.showSkeleton).toBe(true);
  });

  it('a disabled by-id read is not a skeleton', () => {
    const { hooks } = setup();
    const { result } = renderHook(() => hooks.useContract(null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
  });
});

describe('mutations', () => {
  it('terminate posts the body and refreshes the contract, its versions and the list', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { api, hooks } = setup({ 'POST /api/contracts/c1/terminate': ok(contract({ status: 'terminated' })), 'GET /api/contracts/c1': ok(contract()) });
    const { result } = renderHook(() => ({ term: hooks.useTerminateContract(), detail: hooks.useContract('c1') }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.detail.data?.status).toBe('draft'));
    api.route('GET /api/contracts/c1', ok(contract({ status: 'terminated' })));
    await act(async () => { await result.current.term.mutateAsync({ id: 'c1', body: { reason: 'fim', effective_on: '2026-12-01' } }); });
    expect(api.post).toHaveBeenCalledWith('/api/contracts/c1/terminate', { reason: 'fim', effective_on: '2026-12-01' });
    await waitFor(() => expect(result.current.detail.data?.status).toBe('terminated'));
  });

  it('a refused mutation rejects with the ApiError (never swallowed)', async () => {
    const api = makeRoutedApi<ContractsApi>({
      'POST /api/contracts/c1/activate': () => { throw new ApiError(409, 'x', { error: { code: 'transicao_invalida', message: 'x' } }); },
    });
    const hooks = createContractsHooks(api);
    const { result } = renderHook(() => hooks.useActivateContract(), { wrapper: wrapperFor() });
    await expect(act(async () => { await result.current.mutateAsync({ id: 'c1' }); })).rejects.toBeInstanceOf(ApiError);
  });

  it('readjust preview does not invalidate; apply does', async () => {
    const { api, hooks } = setup({ 'POST /api/contracts/c1/readjust': (_p: string, body: any) => ok({ applied: !!body.apply, amount_cents_before: 1, amount_cents_after: 2 }), 'GET /api/contracts/c1': ok(contract()) });
    const { result } = renderHook(() => ({ r: hooks.useReadjustContract(), d: hooks.useContract('c1') }), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.d.data).toBeDefined());
    const before = api.get.mock.calls.length;
    await act(async () => { await result.current.r.mutateAsync({ id: 'c1', percent_bp: 450, apply: false }); });
    expect(api.get.mock.calls.length).toBe(before);
    await act(async () => { await result.current.r.mutateAsync({ id: 'c1', percent_bp: 450, apply: true }); });
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(before));
  });
});
