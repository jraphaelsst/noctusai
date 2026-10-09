/**
 * Core logout ends the session everywhere: the server revocation call happens
 * FIRST (it needs the bearer), and local state is cleared whatever its outcome.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import React from 'react';

const order: string[] = [];
const post = vi.fn();

vi.mock('./api', () => ({
  api: { post: (...a: unknown[]) => post(...a), get: vi.fn().mockRejectedValue(new Error('no profile')) },
  clearToken: () => { order.push('clear'); },
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
  getRefreshToken: () => null,
  isAuthenticated: () => true,
}));
vi.mock('@noctusai/lib/components', () => ({ MfaChallengeHost: () => null }));
vi.mock('@noctusai/lib/design-system/useActivityRefresh', () => ({ useActivityRefresh: () => undefined }));

import { AuthProvider, useAuth } from './auth-context';

let captured: ReturnType<typeof useAuth>;
function Probe() {
  captured = useAuth();
  return null;
}

describe('core logout ordering', () => {
  beforeEach(() => {
    order.length = 0;
    post.mockReset();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('calls POST /api/auth/logout before clearing local state', async () => {
    post.mockImplementation(async (path: string) => { order.push(`post:${path}`); return { ok: true }; });
    render(<AuthProvider><Probe /></AuthProvider>);
    order.length = 0;
    await act(async () => { await captured.logout(); });
    expect(order).toEqual(['post:/api/auth/logout', 'clear']);
  });

  it('still clears local state when the server call fails', async () => {
    post.mockImplementation(async (path: string) => { order.push(`post:${path}`); throw new Error('network'); });
    render(<AuthProvider><Probe /></AuthProvider>);
    order.length = 0;
    await act(async () => { await captured.logout(); });
    expect(order).toEqual(['post:/api/auth/logout', 'clear']);
  });
});
