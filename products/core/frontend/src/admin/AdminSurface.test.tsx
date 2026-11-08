import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AdminSurface } from './AdminSurface';
import { ADMIN_ROUTES } from './routes';
import { WEBSITE_ROUTES } from './websiteConfig';

afterEach(() => cleanup());

vi.mock('../components/layout/Layout', () => ({
  Layout: ({ children, role }: { children: React.ReactNode; role: string }) => (
    <div data-testid="admin-shell" data-role={role}>{children}</div>
  ),
}));

function html(path: string, role: 'admin' | 'marketing') {
  const r = render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<AdminSurface role={role} routes={role === 'admin' ? ADMIN_ROUTES : WEBSITE_ROUTES} navGroups={[]} />} />
      </Routes>
    </MemoryRouter>,
  );
  const out = r.container.innerHTML;
  cleanup();
  return out;
}

describe('AdminSurface route registration', () => {
  it('marketing on a non-website admin path gets the plain unknown-path NotFound, no shell', () => {
    const unknown = html('/nope', 'marketing');
    expect(html('/admin/users', 'marketing')).toBe(unknown);
    expect(html('/admin', 'marketing')).toBe(unknown);
    expect(unknown).not.toContain('admin-shell');
  });

  it('an admin on an unknown path also gets the plain NotFound', () => {
    expect(html('/nope', 'admin')).toContain('Página não encontrada');
    expect(html('/nope', 'admin')).not.toContain('admin-shell');
  });

  it('marketing reaches the website shell', () => {
    expect(html('/admin/website/leads', 'marketing')).toContain('data-role="marketing"');
  });

  it('an admin reaches the shell on a known path', () => {
    expect(html('/admin/users', 'admin')).toContain('data-role="admin"');
  });
});
