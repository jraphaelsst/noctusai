/**
 * How a session ends (2026-10-24 prod incident: an idle tab's expiry signed the
 * user out everywhere). Expiry is LOCAL only; the explicit "Sair" is the only
 * ending that reaches the server; a refusal caused by another tab's rotation is
 * an adoption, not an ending.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  adoptRotatedPair,
  endSessionLocally,
  readSharedActivity,
  signOutExplicitly,
  writeSharedActivity,
  SHARED_ACTIVITY_KEY,
} from './session-ending';

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('adoptRotatedPair — refusal after another tab rotated the chain', () => {
  it('adopts the shared newer pair when the slot holds a DIFFERENT refresh token', () => {
    expect(adoptRotatedPair('rt-1', { accessToken: 'at-2', refreshToken: 'rt-2' })).toBe('at-2');
  });

  it('is dead (null) when the slot still holds the refused token', () => {
    expect(adoptRotatedPair('rt-1', { accessToken: 'at-1', refreshToken: 'rt-1' })).toBeNull();
  });

  it('is dead (null) when the shared slot is empty', () => {
    expect(adoptRotatedPair('rt-1', { accessToken: null, refreshToken: null })).toBeNull();
    expect(adoptRotatedPair('rt-1', { accessToken: 'at-2', refreshToken: null })).toBeNull();
  });
});

describe('endSessionLocally — expiry never reaches the server', () => {
  it('clears local state and goes to the login prompt with no network call', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const clearLocal = vi.fn();
    const navigate = vi.fn();
    endSessionLocally({ clearLocal, redirectTo: '/login', navigate });
    expect(clearLocal).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/login');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('may leave storage alone (a product tab that just leaves for core)', () => {
    const navigate = vi.fn();
    endSessionLocally({ redirectTo: 'https://core.example', navigate });
    expect(navigate).toHaveBeenCalledWith('https://core.example');
  });
});

describe('signOutExplicitly — the explicit "Sair" is the only server revoke', () => {
  it('revokes server-side first, then clears locally', async () => {
    const order: string[] = [];
    await signOutExplicitly({
      revoke: async () => { order.push('revoke'); },
      clearLocal: () => { order.push('clear'); },
    });
    expect(order).toEqual(['revoke', 'clear']);
  });

  it('still clears locally when the revocation fails (non-strict), reporting it', async () => {
    const clearLocal = vi.fn();
    const onRevokeError = vi.fn();
    await signOutExplicitly({ revoke: async () => { throw new Error('network'); }, clearLocal, onRevokeError });
    expect(onRevokeError).toHaveBeenCalledTimes(1);
    expect(clearLocal).toHaveBeenCalledTimes(1);
  });

  it('strict: a failed revocation rethrows and clears nothing', async () => {
    const clearLocal = vi.fn();
    await expect(signOutExplicitly({
      revoke: async () => { throw new Error('network'); }, clearLocal, strict: true,
    })).rejects.toThrow('network');
    expect(clearLocal).not.toHaveBeenCalled();
  });
});

describe('shared activity — one inactivity clock per origin', () => {
  it('round-trips the newest interaction through localStorage', () => {
    expect(readSharedActivity()).toBe(0);
    writeSharedActivity(1234);
    expect(localStorage.getItem(SHARED_ACTIVITY_KEY)).toBe('1234');
    expect(readSharedActivity()).toBe(1234);
  });
});
