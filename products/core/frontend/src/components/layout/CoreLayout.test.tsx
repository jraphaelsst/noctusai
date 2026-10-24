/**
 * CoreLayout — the marketing-role route gate (contract §6, docs `11 §Roles`).
 *
 * `admin` reaches every `/admin/*` route. `marketing` reaches ONLY
 * `/admin/website/*` and is redirected away from anything else under
 * `/admin`. A plain `user` sees nothing under `/admin` at all. Module
 * boundaries (`../../lib/auth-context`, `../../lib/api`, `./Layout`) are
 * substituted via `vi.mock` — the house pattern for page-level tests that
 * consume context hooks with no DI-provider seam (see `Onboarding.test.tsx`).
 * `./Layout` is mocked to isolate the gate logic under test; its own sidebar
 * derivation is covered by `Layout.test.tsx`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CoreLayout } from './CoreLayout';

afterEach(() => cleanup());

let mockAuth: { isAdmin: boolean; isMarketing: boolean; logout: () => void; endLocally?: () => void };

vi.mock('../../lib/auth-context', () => ({
  useAuth: () => mockAuth,
}));

let mockAuthenticated = false;
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

vi.mock('./Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div data-testid="admin-shell">{children}</div>,
}));

function renderAt(path: string, auth: typeof mockAuth) {
  mockAuth = auth;
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<div>HOME</div>} />
        <Route path="*" element={<CoreLayout><div>CHILD</div></CoreLayout>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CoreLayout — marketing role gate', () => {
  it('admin sees every /admin/* route', () => {
    renderAt('/admin/users', { isAdmin: true, isMarketing: false, logout: vi.fn() });
    expect(screen.getByTestId('admin-shell')).toBeTruthy();
    expect(screen.getByText('CHILD')).toBeTruthy();
    expect(screen.queryByText('HOME')).toBeNull();
  });

  it('marketing reaches /admin/website/*', () => {
    renderAt('/admin/website/settings', { isAdmin: false, isMarketing: true, logout: vi.fn() });
    expect(screen.getByTestId('admin-shell')).toBeTruthy();
    expect(screen.getByText('CHILD')).toBeTruthy();
  });

  it('marketing is redirected away from every other /admin route', () => {
    renderAt('/admin/users', { isAdmin: false, isMarketing: true, logout: vi.fn() });
    expect(screen.getByText('HOME')).toBeTruthy();
    expect(screen.queryByTestId('admin-shell')).toBeNull();
  });

  it('marketing is redirected away from the /admin dashboard root too', () => {
    renderAt('/admin', { isAdmin: false, isMarketing: true, logout: vi.fn() });
    expect(screen.getByText('HOME')).toBeTruthy();
  });

  it('a plain user sees nothing under /admin', () => {
    renderAt('/admin', { isAdmin: false, isMarketing: false, logout: vi.fn() });
    expect(screen.getByText('HOME')).toBeTruthy();
    expect(screen.queryByTestId('admin-shell')).toBeNull();
  });

  it('non-admin routes render children directly, no shell, for anyone', () => {
    renderAt('/dashboard', { isAdmin: false, isMarketing: false, logout: vi.fn() });
    expect(screen.getByText('CHILD')).toBeTruthy();
    expect(screen.queryByTestId('admin-shell')).toBeNull();
  });
});

describe('CoreLayout — inactivity expiry', () => {
  it('ends the session LOCALLY and goes to /login — never a server logout (2026-10-24)', async () => {
    mockAuthenticated = true;
    const logout = vi.fn().mockResolvedValue(undefined);
    const endLocally = vi.fn();
    const assign = vi.fn();
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    Object.defineProperty(window, 'location', { value: { href: '/', pathname: '/dashboard', assign }, writable: true });
    renderAt('/dashboard', { isAdmin: false, isMarketing: false, logout, endLocally });
    expect(capturedExpired).not.toBeNull();
    await capturedExpired!();
    expect(endLocally).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith('/login');
    expect(logout).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    mockAuthenticated = false;
  });
});
