/** Request budget (2026-11-10): the bell polls ONE cheap count; the list refetches only when the count moves. */
import { act, cleanup, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./auth', () => ({ useAuthReady: () => true }));

import { createNotificationHooks, NOTIFICATION_POLL_MS } from './notifications';

let naoLidas = 0;
let ultimaId: string | null = null;
const get = vi.fn(async (url: string) =>
  url.startsWith('/api/notificacoes/contagem')
    ? { nao_lidas: naoLidas, ultima_id: ultimaId }
    : { data: [], pagination: {} },
);
const hooks = createNotificationHooks({ get } as never, () => ({ user: { id: 'u' } }));
const calls = (prefix: string) => get.mock.calls.filter(([u]) => u.startsWith(prefix)).length;

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  renderHook(() => { hooks.useNotificacoes(1, 10); hooks.useContagemNaoLidas(); }, { wrapper });
}

beforeEach(() => { vi.useFakeTimers(); get.mockClear(); naoLidas = 0; ultimaId = null; focusManager.setFocused(true); });
afterEach(() => { cleanup(); vi.useRealTimers(); focusManager.setFocused(undefined); });

describe('notification bell request budget', () => {
  it('polls no faster than a minute', () => {
    expect(NOTIFICATION_POLL_MS).toBeGreaterThanOrEqual(60_000);
  });

  it('does not re-read the list while the count is unchanged', async () => {
    setup();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    const listBefore = calls('/api/notificacoes?');
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS * 3); });
    expect(calls('/api/notificacoes?')).toBe(listBefore);
  });

  it('re-reads the list when the count moves', async () => {
    setup();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    const listBefore = calls('/api/notificacoes?');
    naoLidas = 1;
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS + 1_000); });
    expect(calls('/api/notificacoes?')).toBeGreaterThan(listBefore);
  });

  it('re-reads the list when a new unread arrives and another is read in the same window (count unchanged)', async () => {
    naoLidas = 1;
    ultimaId = 'n1';
    setup();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    const listBefore = calls('/api/notificacoes?');
    ultimaId = 'n2'; // n2 arrived, n1 was read elsewhere: still 1 unread
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS + 1_000); });
    expect(calls('/api/notificacoes?')).toBeGreaterThan(listBefore);
  });

  it('does not poll while the tab is hidden', async () => {
    setup();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    focusManager.setFocused(false);
    const before = get.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS * 5); });
    expect(get.mock.calls.length).toBe(before);
  });
});
