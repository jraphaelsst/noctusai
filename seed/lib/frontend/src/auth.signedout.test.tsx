/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import { useSupabaseAuthInit } from './auth';

function setup(stored: unknown) {
  let cb: (e: string, s: unknown) => void = () => {};
  const supabase = {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn((fn) => {
        cb = fn;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
    },
  };
  const setUser = vi.fn();
  renderHook(() => useSupabaseAuthInit(supabase, setUser));
  supabase.auth.getSession.mockResolvedValue({ data: { session: stored } });
  return { fire: cb, getCb: () => cb, setUser };
}

describe('useSupabaseAuthInit SIGNED_OUT', () => {
  it('keeps the user when the shared slot still holds a live session', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const user = { id: 'u1' };
    const h = setup({ user });
    await waitFor(() => expect(h.setUser).toHaveBeenCalledWith(null)); // boot, no session
    h.setUser.mockClear();
    await act(async () => { h.getCb()('SIGNED_OUT', null); });
    await waitFor(() => expect(h.setUser).toHaveBeenCalledWith(user));
    expect(h.setUser).not.toHaveBeenCalledWith(null);
    expect(warn).toHaveBeenCalled();
  });

  it('signs out (and logs) when no session is stored', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const h = setup(null);
    await waitFor(() => expect(h.setUser).toHaveBeenCalled());
    h.setUser.mockClear();
    await act(async () => { h.getCb()('SIGNED_OUT', null); });
    await waitFor(() => expect(h.setUser).toHaveBeenCalledWith(null));
    expect(warn.mock.calls.flat().join(' ')).toContain('SIGNED_OUT confirmed');
  });
});
