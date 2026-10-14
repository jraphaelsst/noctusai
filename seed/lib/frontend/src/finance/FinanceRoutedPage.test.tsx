import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { FinanceRoutedPage } from './FinanceRoutedPage';
import { makeClient } from './testUtils';

afterEach(cleanup);

const makeApi = () => ({
  get: vi.fn((_path: string) => new Promise(() => {})),
  post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn(),
});

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderAt(path: string, base = '/financeiro', props: Partial<React.ComponentProps<typeof FinanceRoutedPage>> = {}) {
  const api = makeApi();
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path={`${base}/*`}
            element={
              <>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <FinanceRoutedPage basePath={base} api={api as any} isAdmin {...(props as object)} />
                <Where />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return api;
}

const current = () => screen.getByRole('button', { current: 'page' }).textContent;

describe('FinanceRoutedPage', () => {
  it('the bare base path is the overview', () => {
    renderAt('/financeiro');
    expect(current()).toBe('Visão geral');
  });

  it('a deep link opens that section and reads /api/finance through the given api', () => {
    const api = renderAt('/financeiro/receber');
    expect(current()).toBe('Contas a receber');
    expect(api.get.mock.calls.some(([p]) => String(p).startsWith('/api/finance/'))).toBe(true);
  });

  it('clicking a section writes the URL; the overview returns to the base path', () => {
    renderAt('/financeiro/dre');
    fireEvent.click(screen.getByRole('button', { name: 'Contas a pagar' }));
    expect(screen.getByTestId('where').textContent).toBe('/financeiro/pagar');
    fireEvent.click(screen.getByRole('button', { name: 'Visão geral' }));
    expect(screen.getByTestId('where').textContent).toBe('/financeiro');
  });

  it('an unknown segment redirects to the canonical URL of the overview', () => {
    renderAt('/financeiro/nao-existe');
    expect(screen.getByTestId('where').textContent).toBe('/financeiro');
    expect(current()).toBe('Visão geral');
  });

  it('works under a nested base path and a trailing-slash base', () => {
    renderAt('/admin/financeiro/pagar', '/admin/financeiro', { basePath: '/admin/financeiro/' });
    expect(current()).toBe('Contas a pagar');
    fireEvent.click(screen.getByRole('button', { name: 'DRE' }));
    expect(screen.getByTestId('where').textContent).toBe('/admin/financeiro/dre');
  });

  it('renders the optional title', () => {
    renderAt('/financeiro', '/financeiro', { title: 'Financeiro da casa', className: 'p-4' });
    expect(screen.getByRole('heading', { level: 1, name: 'Financeiro da casa' })).toBeTruthy();
  });
});
