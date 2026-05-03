/**
 * useScheduling hook tests — pilot consumer of /api/scheduling/*.
 *
 * Pattern mirrors useConsents.test.ts: stub `api.{get,post,patch}`,
 * silence sonner, render hooks inside a fresh QueryClient.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const { mockGet, mockPost, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
}));

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
  useAuthStore: () => ({ user: { id: 'user-test', user_metadata: {} } }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import {
  useBookAppointment,
  useCandidateSlots,
  useGcalAuthorizeUrl,
} from '@/hooks/useScheduling';


function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}


describe('useScheduling hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useCandidateSlots calls /api/scheduling/candidates with required params', async () => {
    mockGet.mockResolvedValue({ data: [] });
    const { result } = renderHook(
      () =>
        useCandidateSlots({
          therapist_id: 'ther-1',
          window_start: '2026-06-01T00:00:00Z',
          window_end: '2026-06-07T23:59:59Z',
        }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain('/api/scheduling/candidates');
    expect(url).toContain('therapist_id=ther-1');
  });

  it('useCandidateSlots is disabled when params is null (no fetch)', () => {
    renderHook(() => useCandidateSlots(null), { wrapper: withQueryClient() });
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('useBookAppointment posts the slot to /api/scheduling/appointments', async () => {
    mockPost.mockResolvedValue({ data: { id: 'a1', status: 'waiting' } });
    const { result } = renderHook(() => useBookAppointment(), {
      wrapper: withQueryClient(),
    });
    result.current.mutate({
      therapist_id: 'ther-1',
      patient_id: 'pat-1',
      slot_start: '2026-06-01T10:00:00Z',
      slot_end: '2026-06-01T10:50:00Z',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith(
      '/api/scheduling/appointments',
      expect.objectContaining({
        therapist_id: 'ther-1',
        patient_id: 'pat-1',
      }),
    );
  });

  it('useGcalAuthorizeUrl fetches the per-therapist authorize url', async () => {
    mockGet.mockResolvedValue({
      data: {
        authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth?...',
        needs_authorization: true,
      },
    });
    const { result } = renderHook(() => useGcalAuthorizeUrl('ther-1'), {
      wrapper: withQueryClient(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      '/api/scheduling/gcal/authorize?therapist_id=ther-1',
    );
  });
});
