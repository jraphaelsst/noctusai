import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { formatCents, parseMoneyToCents, centsToInput } from './money';
import { keep, signals, createFetchTransport } from './query';
import { ListSkeleton, RefreshingBar, RetryError } from './controls';
import { makeRoutedApi } from './testing';

describe('organ-kit', () => {
  it('money: cents <-> BRL text', () => {
    expect(formatCents(123456).replace(/\s/g, ' ')).toBe('R$ 1.234,56');
    expect(parseMoneyToCents('R$ 1.234,56')).toBe(123456);
    expect(parseMoneyToCents('abc')).toBeNull();
    expect(centsToInput(1250)).toBe('12,50');
  });

  it('signals: skeleton only on first load, refreshing only over data; idle is no skeleton', () => {
    const base = { data: undefined, error: null, isError: false, isPending: true, refetch: () => undefined } as const;
    const first = signals({ ...base, isFetching: true, fetchStatus: 'fetching' } as never);
    expect(first.showSkeleton).toBe(true);
    expect(first.isRefreshing).toBe(false);
    const idle = signals({ ...base, isFetching: false, fetchStatus: 'idle' } as never);
    expect(idle.showSkeleton).toBe(false);
    const refetch = signals({ ...base, data: [1], isPending: false, isFetching: true, fetchStatus: 'fetching' } as never);
    expect(refetch.showSkeleton).toBe(false);
    expect(refetch.isRefreshing).toBe(true);
    expect(keep([1])).toEqual([1]);
  });

  it('controls render', () => {
    render(
      <>
        <ListSkeleton rows={2} />
        <RefreshingBar active label="Atualizando" />
        <RetryError message="falhou" onRetry={() => undefined} retryLabel="Tentar de novo" />
      </>,
    );
    expect(screen.getByTestId('list-loading')).toBeTruthy();
    expect(screen.getByText('Atualizando')).toBeTruthy();
    expect(screen.getByText('Tentar de novo')).toBeTruthy();
  });

  it('makeRoutedApi: routed value, function handler, and a loud unrouted rejection', async () => {
    const api = makeRoutedApi({ 'GET /x': { ok: 1 }, 'POST /y': (_p: string, b?: unknown) => ({ got: b }) });
    expect(await api.get('/x?z=1')).toEqual({ ok: 1 });
    expect(await api.post('/y', { a: 1 })).toEqual({ got: { a: 1 } });
    await expect(api.get('/nope')).rejects.toThrow(/unrouted GET \/nope/);
  });

  it('createFetchTransport is a full api surface', () => {
    const api = createFetchTransport('http://x/');
    expect(Object.keys(api).sort()).toEqual(['delete', 'get', 'patch', 'post', 'put', 'upload']);
  });
});
