/**
 * useAgenda hook smoke tests — including GCal sync.
 *
 * Pattern mirrors products/erp-imobiliario/frontend/src/hooks/__tests__/useCorretorHooks.test.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test.com' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
  useAuthStore: () => mockAuth,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

const MOCK_EVENT = {
  id: 'ev1',
  org_id: 'org1',
  title: 'Reunião cliente',
  description: null,
  event_type: 'meeting',
  client_id: null,
  starts_at: '2026-06-05T10:00:00Z',
  ends_at: '2026-06-05T11:00:00Z',
  location: null,
  gcal_event_id: null,
  assignee_user_id: null,
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
};

describe('useAgenda hook smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useAgendaEvents fetches /api/agenda/events with default params', async () => {
    const mockResponse = {
      items: [MOCK_EVENT],
      total: 1,
      page: 1,
      page_size: 200,
    };
    mockGet.mockResolvedValue(mockResponse);

    const { useAgendaEvents } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useAgendaEvents(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/agenda/events', { page: 1, page_size: 200 });
    expect(result.current.data?.items[0].title).toBe('Reunião cliente');
  });

  it('useAgendaEvents passes event_type filter', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useAgendaEvents } = await import('@/hooks/useAgenda');
    renderHook(() => useAgendaEvents({ event_type: 'call' }), { wrapper: withQueryClient() });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/agenda/events', {
      page: 1,
      page_size: 200,
      event_type: 'call',
    });
  });

  it('useAgendaEvents passes date range filters', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useAgendaEvents } = await import('@/hooks/useAgenda');
    renderHook(
      () => useAgendaEvents({ from: '2026-06-01', to: '2026-06-30' }),
      { wrapper: withQueryClient() }
    );

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/agenda/events', {
      page: 1,
      page_size: 200,
      from: '2026-06-01',
      to: '2026-06-30',
    });
  });

  it('useCreateAgendaEvent POSTs to /api/agenda/events', async () => {
    mockPost.mockResolvedValue(MOCK_EVENT);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useCreateAgendaEvent } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useCreateAgendaEvent(), { wrapper: withQueryClient() });

    result.current.mutate({
      title: 'Reunião cliente',
      event_type: 'meeting',
      starts_at: '2026-06-05T10:00:00Z',
      ends_at: '2026-06-05T11:00:00Z',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/api/agenda/events', expect.objectContaining({
      title: 'Reunião cliente',
      event_type: 'meeting',
    }));
  });

  it('useDeleteAgendaEvent DELETEs /api/agenda/events/{id}', async () => {
    mockDelete.mockResolvedValue({ ok: true });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useDeleteAgendaEvent } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useDeleteAgendaEvent(), { wrapper: withQueryClient() });

    result.current.mutate('ev1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith('/api/agenda/events/ev1');
  });

  it('useSyncGcal POSTs to /api/agenda/events/{id}/sync-gcal', async () => {
    const synced = {
      ...MOCK_EVENT,
      gcal_event_id: 'fake_gcal_abc123',
    };
    mockPost.mockResolvedValue(synced);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useSyncGcal } = await import('@/hooks/useAgenda');
    const { result } = renderHook(() => useSyncGcal(), { wrapper: withQueryClient() });

    result.current.mutate('ev1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/api/agenda/events/ev1/sync-gcal', {});
    expect(result.current.data?.gcal_event_id).toBe('fake_gcal_abc123');
  });
});
