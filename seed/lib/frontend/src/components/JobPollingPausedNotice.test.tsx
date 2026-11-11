import { cleanup, fireEvent, render, screen, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { JobPollingPausedNotice } from './JobPollingPausedNotice';
import { JOB_POLL_CEILING_MS, jobPolling, resetJobPollingStalled } from '../job-polling';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); resetJobPollingStalled(); vi.useRealTimers(); });

describe('JobPollingPausedNotice', () => {
  it('renders nothing while polling is healthy, says so when it gives up, and Atualizar resumes', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.mount();
    const queryFn = vi.fn(async () => ({ status: 'processando' }));
    const observer = new QueryObserver(client, {
      queryKey: ['stuck'], queryFn,
      ...jobPolling((d: { status: string } | undefined) => d?.status === 'processando', 1000),
    });
    const unsub = observer.subscribe(() => {});
    render(<QueryClientProvider client={client}><JobPollingPausedNotice /></QueryClientProvider>);
    expect(screen.queryByTestId('job-polling-paused')).toBeNull();

    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_CEILING_MS + 5 * 60_000); });
    expect(screen.getByTestId('job-polling-paused').textContent).toContain('Atualização automática pausada');

    const stopped = queryFn.mock.calls.length;
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Atualizar' })); await vi.advanceTimersByTimeAsync(20_000); });
    expect(queryFn.mock.calls.length).toBeGreaterThan(stopped + 1);
    expect(screen.queryByTestId('job-polling-paused')).toBeNull();
    unsub(); client.unmount(); client.clear();
  });
});
