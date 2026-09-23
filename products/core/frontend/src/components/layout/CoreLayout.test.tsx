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

let mockAuth: { isAdmin: boolean; isMarketing: boolean; logout: () => void };

vi.mock('../../lib/auth-context', () => ({
  useAuth: () => mockAuth,
}));

vi.mock('../../lib/api', () => ({
  isAuthenticated: () => false,
  api: { get: vi.fn(), post: vi.fn() },
  getRefreshToken: () => null,
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
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
