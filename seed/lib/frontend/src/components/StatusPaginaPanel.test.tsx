/**
 * Tests for the StatusPaginaPanel organ.
 *
 * Coverage:
 *   1. Loading state — aria-busy present
 *   2. Error state — role="alert" with message + retry
 *   3. Empty state — "Nenhuma página cadastrada" message
 *   4. Success — each page rendered with name + status badge + selector
 *   5. Changing a selector PATCHes /api/status-paginas/{id} with the new status
 *   6. Selecting the SAME status is a no-op (no PATCH)
 *   7. enabled=false does not fire the GET
 *
 * Dual-React gap: resolved in the noctusai monorepo (NOC-REMEDIATE resolved
 * 2026-05-29) — full render tests are safe here.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { StatusPaginaPanel } from './StatusPaginaPanel';
import type { StatusPaginaApi, StatusPaginaRow } from './StatusPaginaPanel';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

afterEach(cleanup);

// ── Fixtures ─────────────────────────────────────────────────────────────────

const ROWS: StatusPaginaRow[] = [
  {
    id: 'p1',
    nome_pagina: 'Dashboard',
    status: 'producao',
    descricao: 'Painel inicial',
    tipo_pagina: 'page',
    updated_at: '2026-06-01T00:00:00Z',
  },
  {
    id: 'p2',
    nome_pagina: 'Relatórios (beta)',
    status: 'desenvolvimento',
    descricao: null,
    tipo_pagina: null,
    updated_at: null,
  },
];

function makeApi(overrides: Partial<StatusPaginaApi> = {}): StatusPaginaApi {
  return {
    get: vi.fn(async () => ROWS as any),
    patch: vi.fn(async (_path: string) => ROWS[0] as any),
    ...overrides,
  };
}

function renderPanel(props: Partial<Parameters<typeof StatusPaginaPanel>[0]>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const api = props.api ?? makeApi();
  const utils = render(
    <QueryClientProvider client={client}>
      <StatusPaginaPanel api={api} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, api };
}

// ── 1. Loading ────────────────────────────────────────────────────────────────

describe('StatusPaginaPanel: loading', () => {
  it('renders an aria-busy indicator while the query is in flight', () => {
    // A never-resolving get keeps the query pending.
    const api = makeApi({ get: vi.fn((): Promise<any> => new Promise(() => {})) });
    const { container } = renderPanel({ api });
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });
});

// ── 2. Error ──────────────────────────────────────────────────────────────────

describe('StatusPaginaPanel: error', () => {
  it('renders an alert with the error message', async () => {
    const api = makeApi({
      get: vi.fn(async () => {
        throw new Error('Boom 403');
      }),
    });
    renderPanel({ api });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Boom 403');
    expect(screen.getByText('Tentar novamente')).toBeInTheDocument();
  });
});

// ── 3. Empty ──────────────────────────────────────────────────────────────────

describe('StatusPaginaPanel: empty', () => {
  it('renders the empty message when no pages exist', async () => {
    const api = makeApi({ get: vi.fn(async () => [] as any) });
    renderPanel({ api });
    expect(
      await screen.findByText(/Nenhuma página cadastrada/i),
    ).toBeInTheDocument();
  });
});

// ── 4. Success ────────────────────────────────────────────────────────────────

describe('StatusPaginaPanel: success', () => {
  it('renders each page with its name and a status selector', async () => {
    renderPanel({});
    expect(await screen.findByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Relatórios (beta)')).toBeInTheDocument();
    // Two selectors, one per page, defaulting to each row's status.
    const select1 = screen.getByLabelText('Status de Dashboard') as HTMLSelectElement;
    expect(select1.value).toBe('producao');
    const select2 = screen.getByLabelText(
      'Status de Relatórios (beta)',
    ) as HTMLSelectElement;
    expect(select2.value).toBe('desenvolvimento');
  });
});

// ── 5. Change status → PATCH ──────────────────────────────────────────────────

describe('StatusPaginaPanel: change status', () => {
  it('PATCHes /api/status-paginas/{id} with the new status', async () => {
    const { api } = renderPanel({});
    const select = (await screen.findByLabelText(
      'Status de Dashboard',
    )) as HTMLSelectElement;

    fireEvent.change(select, { target: { value: 'desativado' } });

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/api/status-paginas/p1', {
        status: 'desativado',
      }),
    );
  });

  it('does NOT PATCH when the selected status is unchanged', async () => {
    const { api } = renderPanel({});
    const select = (await screen.findByLabelText(
      'Status de Dashboard',
    )) as HTMLSelectElement;

    fireEvent.change(select, { target: { value: 'producao' } });

    expect(api.patch).not.toHaveBeenCalled();
  });
});

// ── 6. enabled gate ───────────────────────────────────────────────────────────

describe('StatusPaginaPanel: enabled gate', () => {
  it('does not fire the GET when enabled=false', () => {
    const api = makeApi();
    renderPanel({ api, enabled: false });
    expect(api.get).not.toHaveBeenCalled();
  });
});
