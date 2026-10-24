/**
 * InactivityWarning shares its clock across the tabs of an origin: an idle tab
 * never expires while the user is active in another tab (2026-10-24 prod: an idle
 * core tab's expiry ended the session every core tab shares).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { InactivityWarning } from './InactivityWarning';
import { SHARED_ACTIVITY_KEY } from '../session-ending';

const LIFETIME = 10_000;

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  localStorage.clear();
});

describe('InactivityWarning — cross-tab activity', () => {
  it('expires when every tab of the origin is idle', () => {
    const onExpired = vi.fn();
    render(<InactivityWarning onExtend={async () => {}} onExpired={onExpired} tokenLifetimeMs={LIFETIME} warningBeforeMs={2_000} />);
    act(() => { vi.advanceTimersByTime(LIFETIME + 1_000); });
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it('does NOT expire while another tab keeps recording activity', () => {
    const onExpired = vi.fn();
    render(<InactivityWarning onExtend={async () => {}} onExpired={onExpired} tokenLifetimeMs={LIFETIME} warningBeforeMs={2_000} />);
    for (let i = 0; i < 6; i += 1) {
      act(() => {
        vi.advanceTimersByTime(3_000);
        // the user works in ANOTHER tab of this origin
        localStorage.setItem(SHARED_ACTIVITY_KEY, String(Date.now()));
      });
    }
    expect(onExpired).not.toHaveBeenCalled();
  });

  it("publishes this tab's own interactions for the other tabs", () => {
    render(<InactivityWarning onExtend={async () => {}} onExpired={() => {}} tokenLifetimeMs={LIFETIME} />);
    act(() => {
      vi.advanceTimersByTime(2_000);
      window.dispatchEvent(new KeyboardEvent('keydown'));
    });
    expect(Number(localStorage.getItem(SHARED_ACTIVITY_KEY))).toBe(Date.now());
  });
});
