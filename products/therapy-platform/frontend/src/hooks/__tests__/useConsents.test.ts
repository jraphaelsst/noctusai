/**
 * useConsents hook tests — first Vitest coverage for the therapy frontend.
 *
 * Pattern mirrors the established ERP + PF hook tests
 * (`useAI.test.ts`): stub `api.get`/`api.post` at `@noctusai/seed/infra`,
 * silence `sonner` toasts, render hooks inside a fresh QueryClient
 * provider per test.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost },
  useAuthStore: () => ({ user: { id: 'user-test', user_metadata: {} } }),
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


describe('useConsents hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useConsents fetches /api/consents/:appointmentId and unwraps res.data', async () => {
    mockGet.mockResolvedValue({
      data: [
        {
          id: 'c1',
          appointment_id: 'appt-1',
          patient_id: 'pat-1',
          therapist_id: 'ther-1',
          scope: 'recording',
          policy_version: 'v1',
          purpose_text: 'gravar',
          actor_user_id: 'pat-1',
          granted_at: '2026-05-01T10:00:00Z',
          revoked_at: null,
          revoked_by: null,
          revoke_reason: null,
        },
      ],
    });

    const { useConsents } = await import('@/hooks/useConsents');
    const { result } = renderHook(() => useConsents('appt-1'), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGet).toHaveBeenCalledWith('/api/consents/appt-1');
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].scope).toBe('recording');
  });

  it('getActiveConsent returns the active recording consent + ignores revoked', async () => {
    const { getActiveConsent } = await import('@/hooks/useConsents');
    const records = [
      {
        id: 'c-old', scope: 'recording' as const, revoked_at: '2026-04-01T10:00:00Z',
        appointment_id: 'a', patient_id: 'p', therapist_id: 't',
        policy_version: 'v1', purpose_text: 'x', actor_user_id: 'p',
        granted_at: '2026-03-01T10:00:00Z', revoked_by: 't', revoke_reason: 'revisao',
      },
      {
        id: 'c-active', scope: 'recording' as const, revoked_at: null,
        appointment_id: 'a', patient_id: 'p', therapist_id: 't',
        policy_version: 'v1', purpose_text: 'x', actor_user_id: 'p',
        granted_at: '2026-05-01T10:00:00Z', revoked_by: null, revoke_reason: null,
      },
    ];
    expect(getActiveConsent(records, 'recording')?.id).toBe('c-active');
    expect(getActiveConsent(records, 'transcription')).toBeUndefined();
  });

  it('useGrantConsent posts to /api/consents/grant with default policy + purpose', async () => {
    mockPost.mockResolvedValue({ data: { id: 'c-new' } });

    const { useGrantConsent, CONSENT_POLICY_VERSION } = await import('@/hooks/useConsents');
    const { result } = renderHook(() => useGrantConsent(), { wrapper: withQueryClient() });

    result.current.mutate({ appointment_id: 'appt-1', scope: 'recording' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body] = mockPost.mock.calls[0];
    expect(url).toBe('/api/consents/grant');
    expect(body.appointment_id).toBe('appt-1');
    expect(body.scope).toBe('recording');
    expect(body.policy_version).toBe(CONSENT_POLICY_VERSION);
    // Default purpose-text non-empty so the LGPD audit trail records it.
    expect(typeof body.purpose_text).toBe('string');
    expect(body.purpose_text.length).toBeGreaterThan(0);
  });

  it('useRevokeConsent posts to /api/consents/revoke', async () => {
    mockPost.mockResolvedValue({ data: { id: 'c-revoked' } });

    const { useRevokeConsent } = await import('@/hooks/useConsents');
    const { result } = renderHook(() => useRevokeConsent(), { wrapper: withQueryClient() });

    result.current.mutate({ appointment_id: 'appt-1', scope: 'recording', reason: 'patient changed mind' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith(
      '/api/consents/revoke',
      { appointment_id: 'appt-1', scope: 'recording', reason: 'patient changed mind' },
    );
  });

  it('useGrantConsent surfaces error toast on failure', async () => {
    const { toast } = await import('sonner');
    mockPost.mockRejectedValue(new Error('network'));

    const { useGrantConsent } = await import('@/hooks/useConsents');
    const { result } = renderHook(() => useGrantConsent(), { wrapper: withQueryClient() });

    result.current.mutate({ appointment_id: 'appt-1', scope: 'recording' });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Erro ao registrar consentimento');
  });
});
