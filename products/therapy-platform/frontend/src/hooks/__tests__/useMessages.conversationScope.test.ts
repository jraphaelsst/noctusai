/**
 * useMessages placeholderData axis-scoping regression test.
 *
 * `useMessages`' queryKey is `['messages', conversationId, page]` — two
 * independently-changing axes that need OPPOSITE placeholderData
 * treatment (see the comment on `useMessages` in `useMessages.ts`):
 *
 *   - `page` changing within the SAME conversation → reuse is fine
 *     (pagination-flicker fix, same person's thread).
 *   - `conversationId` changing → reuse is a cross-patient exposure bug:
 *     the previous patient's private message thread would render under
 *     the newly-selected patient's header until the real fetch resolves.
 *
 * This test proves BOTH halves: switching `conversationId` mid-flight
 * must NOT surface the prior conversation's messages, while switching
 * `page` within one conversation DOES keep the prior page mounted.
 *
 * Before the fix (`placeholderData: (prev) => prev`, unscoped): the
 * "conversationId switch" case below fails — `result.current.data` holds
 * conversation A's messages while the query key already points at
 * conversation B.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: { id: 'user-test' } }),
  supabase: { auth: { refreshSession: vi.fn() } },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useMessages placeholderData axis scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does NOT render the previous conversation\'s messages when conversationId changes', async () => {
    const { useMessages } = await import('@/hooks/useMessages');

    // Conversation A's page resolves immediately.
    mockGet.mockResolvedValueOnce({
      data: {
        data: [{ id: 'm1', conversation_id: 'conv-A', content: 'Ola de A' }],
        total: 1,
        page: 1,
        page_size: 50,
      },
    });

    const { result, rerender } = renderHook(
      ({ conversationId }: { conversationId: string }) => useMessages(conversationId, 1),
      { wrapper: withQueryClient(), initialProps: { conversationId: 'conv-A' } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data[0].content).toBe('Ola de A');

    // Conversation B's fetch is held open — this is the transition window
    // where a cross-patient leak would show if placeholderData reused A's
    // data.
    let resolveB!: (v: unknown) => void;
    mockGet.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveB = resolve;
      }),
    );

    rerender({ conversationId: 'conv-B' });

    // Mid-flight: the query key now points at conv-B, and `data` must NOT
    // still be conversation A's messages — that would be A's private
    // thread rendered under B's header.
    expect(result.current.isFetching).toBe(true);
    expect(result.current.data).toBeUndefined();
    expect(result.current.isPlaceholderData).toBe(false);
    expect(result.current.isPending).toBe(true);

    resolveB({
      data: {
        data: [{ id: 'm2', conversation_id: 'conv-B', content: 'Ola de B' }],
        total: 1,
        page: 1,
        page_size: 50,
      },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data[0].content).toBe('Ola de B');
  });

  it('keeps the previous page mounted while a page change within the SAME conversation is in flight', async () => {
    const { useMessages } = await import('@/hooks/useMessages');

    // Page 1 resolves immediately.
    mockGet.mockResolvedValueOnce({
      data: {
        data: [{ id: 'm1', conversation_id: 'conv-A', content: 'Pagina 1' }],
        total: 2,
        page: 1,
        page_size: 50,
      },
    });

    const { result, rerender } = renderHook(
      ({ page }: { page: number }) => useMessages('conv-A', page),
      { wrapper: withQueryClient(), initialProps: { page: 1 } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data[0].content).toBe('Pagina 1');

    // Page 2 fetch (same conversation) held open.
    let resolvePage2!: (v: unknown) => void;
    mockGet.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePage2 = resolve;
      }),
    );

    rerender({ page: 2 });

    // Mid-flight: same conversation, so the previous page's messages stay
    // mounted (never undefined) — the pagination-flicker fix this axis is
    // meant to provide.
    expect(result.current.isFetching).toBe(true);
    expect(result.current.data?.data[0].content).toBe('Pagina 1');
    expect(result.current.isPlaceholderData).toBe(true);

    resolvePage2({
      data: {
        data: [{ id: 'm2', conversation_id: 'conv-A', content: 'Pagina 2' }],
        total: 2,
        page: 2,
        page_size: 50,
      },
    });
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));
    expect(result.current.data?.data[0].content).toBe('Pagina 2');
  });
});
