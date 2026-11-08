/**
 * Admin is NOT RENDERED for anyone but a server-confirmed platform admin / marketing: for everyone
 * else `/admin/*` is byte-identical to a path that never existed.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CatchAll from './CatchAll';

afterEach(() => cleanup());

let mockAuth: Record<string, unknown>;
vi.mock('../lib/auth-context', () => ({ useAuth: () => mockAuth }));
vi.mock('../admin/AdminApp', () => ({
  default: ({ role }: { role: string }) => <div data-testid="admin-app">{role}</div>,
}));

const base = { loading: false, unavailable: false, refresh: vi.fn() };

function renderAt(path: string, auth: Record<string, unknown>) {
  mockAuth = { ...base, ...auth };
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<CatchAll />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CatchAll', () => {
  it('renders /admin for a non-admin exactly like an unknown path', () => {
    const a = renderAt('/admin', { isAdmin: false, isMarketing: false });
    const adminHtml = a.container.innerHTML;
    cleanup();
    const b = renderAt('/definitely-not-a-page', { isAdmin: false, isMarketing: false });
    expect(adminHtml).toBe(b.container.innerHTML);
    expect(adminHtml).toContain('Página não encontrada');
  });

  it('puts no admin link or label in a non-admin DOM', () => {
    const { container } = renderAt('/admin/users', { isAdmin: false, isMarketing: false });
    expect(container.querySelectorAll('a[href^="/admin"]')).toHaveLength(0);
    expect(screen.queryByTestId('admin-app')).toBeNull();
    for (const label of ['Painel', 'CRM', 'ERP', 'Integrações', 'Configurações', 'Fleet Control']) {
      expect(container.textContent).not.toContain(label);
    }
  });

  it('hands a platform admin to the admin surface', async () => {
    renderAt('/admin', { isAdmin: true, isMarketing: false });
    expect((await screen.findByTestId('admin-app')).textContent).toBe('admin');
  });

  it('hands a marketing user to the admin surface as marketing', async () => {
    renderAt('/admin/website/leads', { isAdmin: false, isMarketing: true });
    expect((await screen.findByTestId('admin-app')).textContent).toBe('marketing');
  });

  it('never decides before the profile resolves (no NotFound flash for an admin)', () => {
    const { container } = renderAt('/admin', { isAdmin: false, isMarketing: false, loading: true });
    expect(container.textContent).not.toContain('Página não encontrada');
  });
});
