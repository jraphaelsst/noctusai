/**
 * Tests for `createWhatsAppConnectionsHooks` — URL / method / payload per
 * endpoint (list/create/update/delete/status/qr/start/restart/logout/
 * recover/webhook), plus the polling predicates (status stops on `paired`,
 * QR stops only on `status === 'WORKING'`).
 *
 * Colocated at the package root (sibling of `whatsapp.ts`, which is where
 * `createWhatsAppConnectionsHooks` itself lives) rather than under
 * `components/whatsapp-connections/`, which holds only the presentational
 * organs.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';

import { createWhatsAppConnectionsHooks } from './whatsapp';
import type { ApiClient } from './api';
import type { WhatsAppConnectionLine, WhatsAppConnectionStatus, WhatsAppConnectionQr } from './whatsapp';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

let api: ApiClient;
let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const LINE: WhatsAppConnectionLine = {
  id: 'conn-1',
  label: 'Atendimento',
  base_url: 'https://waha.example.com',
  session_name: 'default',
  webhook_url: 'https://social-wiring.example.com/api/whatsapp/webhook/tok',
  created_at: '2026-09-17T00:00:00Z',
  updated_at: '2026-09-17T00:00:00Z',
};

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  api = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  } as unknown as ApiClient;
});

describe('useConnections', () => {
  it('GETs the default base path', async () => {
    (api.get as any).mockResolvedValue([LINE]);
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnections(), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual([LINE]));
    expect(api.get).toHaveBeenCalledWith('/api/whatsapp/connections');
  });

  it('GETs a custom basePath when supplied', async () => {
    (api.get as any).mockResolvedValue([]);
    const hooks = createWhatsAppConnectionsHooks(api, { basePath: '/api/custom/wa' });
    const { result } = renderHook(() => hooks.useConnections(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(api.get).toHaveBeenCalledWith('/api/custom/wa');
  });

  it('showSkeleton before first data, false after', async () => {
    (api.get as any).mockResolvedValue([]);
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnections(), { wrapper });

    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
  });
});

describe('useConnectionMutations', () => {
  it('create() POSTs {label, api_key}', async () => {
    (api.post as any).mockResolvedValue(LINE);
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnectionMutations(), { wrapper });

    act(() => {
      result.current.create.mutate({ label: 'Atendimento', api_key: 'wa-key' });
    });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections', {
      label: 'Atendimento',
      api_key: 'wa-key',
    });
  });

  it('update() PATCHes /{id} with the body', async () => {
    (api.patch as any).mockResolvedValue(LINE);
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnectionMutations(), { wrapper });

    act(() => {
      result.current.update.mutate({ id: 'conn-1', body: { label: 'Novo nome' } });
    });

    await waitFor(() => expect(result.current.update.isSuccess).toBe(true));
    expect(api.patch).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1', {
      label: 'Novo nome',
    });
  });

  it('remove() DELETEs /{id}', async () => {
    (api.delete as any).mockResolvedValue(undefined);
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnectionMutations(), { wrapper });

    act(() => {
      result.current.remove.mutate('conn-1');
    });

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(api.delete).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1');
  });
});

describe('useConnectionStatus', () => {
  it('GETs /{id}/status and does not fire when connectionId is null', async () => {
    (api.get as any).mockResolvedValue({ connection_id: 'conn-1', status: 'WORKING', paired: true, me_id: null, me_name: null, session: 'default', error: null } as WhatsAppConnectionStatus);
    const hooks = createWhatsAppConnectionsHooks(api);

    const { result: nullResult } = renderHook(() => hooks.useConnectionStatus(null), { wrapper });
    expect(nullResult.current.fetchStatus).toBe('idle');
    expect(api.get).not.toHaveBeenCalled();

    const { result } = renderHook(() => hooks.useConnectionStatus('conn-1'), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(api.get).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/status');
  });

  it('stops polling once paired (no second GET after the poll interval elapses)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    (api.get as any).mockResolvedValue({
      connection_id: 'conn-1', status: 'WORKING', paired: true, me_id: 'x', me_name: 'y', session: 'default', error: null,
    } as WhatsAppConnectionStatus);
    const hooks = createWhatsAppConnectionsHooks(api);
    renderHook(() => hooks.useConnectionStatus('conn-1', true, { pollMs: 50 }), { wrapper });

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(api.get).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('keeps polling while not paired', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    (api.get as any).mockResolvedValue({
      connection_id: 'conn-1', status: 'SCAN_QR_CODE', paired: false, me_id: null, me_name: null, session: 'default', error: null,
    } as WhatsAppConnectionStatus);
    const hooks = createWhatsAppConnectionsHooks(api);
    renderHook(() => hooks.useConnectionStatus('conn-1', true, { pollMs: 50 }), { wrapper });

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect((api.get as any).mock.calls.length).toBeGreaterThan(1);
    vi.useRealTimers();
  });
});

describe('useConnectionQr', () => {
  it('GETs /{id}/qr only when enabled', async () => {
    (api.get as any).mockResolvedValue({ connection_id: 'conn-1', scannable: true, status: 'SCAN_QR_CODE', png_base64: 'abc' } as WhatsAppConnectionQr);
    const hooks = createWhatsAppConnectionsHooks(api);

    const { result: disabled } = renderHook(() => hooks.useConnectionQr('conn-1', false), { wrapper });
    expect(disabled.current.fetchStatus).toBe('idle');

    const { result } = renderHook(() => hooks.useConnectionQr('conn-1', true), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(api.get).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/qr');
  });
});

describe('useConnectionActions', () => {
  it('start()/restart()/logout() POST the right path', async () => {
    (api.post as any).mockResolvedValue({ connection_id: 'conn-1', status: 'STARTING', paired: false, me_id: null, me_name: null, session: 'default', error: null });
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConnectionActions(), { wrapper });

    act(() => result.current.start.mutate('conn-1'));
    await waitFor(() => expect(result.current.start.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/start');

    act(() => result.current.restart.mutate('conn-1'));
    await waitFor(() => expect(result.current.restart.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/restart');

    act(() => result.current.logout.mutate('conn-1'));
    await waitFor(() => expect(result.current.logout.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/logout');
  });
});

describe('useRecoverConnection', () => {
  it('POSTs /{id}/recover with an empty body', async () => {
    (api.post as any).mockResolvedValue({ connection_id: 'conn-1', status: 'SCAN_QR_CODE', paired: false, stage: 'logout_start' });
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useRecoverConnection(), { wrapper });

    act(() => result.current.mutate('conn-1'));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/recover', {});
    expect(result.current.data?.stage).toBe('logout_start');
  });
});

describe('useConfigureConnectionWebhook', () => {
  it('POSTs /{id}/webhook with { url, events? }', async () => {
    (api.post as any).mockResolvedValue({ connection_id: 'conn-1', ok: true, url: LINE.webhook_url, events: ['message'], status: 'WORKING' });
    const hooks = createWhatsAppConnectionsHooks(api);
    const { result } = renderHook(() => hooks.useConfigureConnectionWebhook(), { wrapper });

    act(() =>
      result.current.mutate({ id: 'conn-1', body: { url: LINE.webhook_url! } }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/webhook', {
      url: LINE.webhook_url,
    });
  });
});
