/**
 * CoreLayout carries no admin gate any more (admin routes are not registered for non-admins; see
 * `pages/CatchAll`). It renders children and the inactivity watcher, nothing admin-shaped.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CoreLayout } from './CoreLayout';

afterEach(() => cleanup());

let mockAuthenticated = false;
vi.mock('../../lib/auth-context', () => ({ useAuth: () => ({ endLocally: mockEndLocally }) }));
const mockEndLocally = vi.fn();
vi.mock('../../lib/api', () => ({
  isAuthenticated: () => mockAuthenticated,
  refreshCoreSession: vi.fn(),
}));

let capturedExpired: (() => void | Promise<void>) | null = null;
vi.mock('@noctusai/lib/design-system/InactivityWarning', () => ({
  InactivityWarning: ({ onExpired }: { onExpired: () => void | Promise<void> }) => {
    capturedExpired = onExpired;
    return null;
  },
}));

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <CoreLayout><div>CHILD</div></CoreLayout>
    </MemoryRouter>,
  );
}

describe('CoreLayout', () => {
  it('renders children directly for every path, admin-looking or not', () => {
    renderAt('/admin/users');
    expect(screen.getByText('CHILD')).toBeTruthy();
  });
});

describe('CoreLayout — inactivity expiry', () => {
  it('ends the session LOCALLY and goes to /login — never a server logout (2026-10-24)', async () => {
    mockAuthenticated = true;
    const assign = vi.fn();
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    Object.defineProperty(window, 'location', { value: { href: '/', pathname: '/dashboard', assign }, writable: true });
    renderAt('/dashboard');
    expect(capturedExpired).not.toBeNull();
    await capturedExpired!();
    expect(mockEndLocally).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith('/login');
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    mockAuthenticated = false;
  });
});
