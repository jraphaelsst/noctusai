/**
 * ClientesTab — refetch-unmount regression guard (Category A).
 *
 * Pins the fix at `KB § PATTERNS/frontend/lying-loading-state.md`'s sibling
 * bug: gating the visible content on `isPending || isFetching` (or on
 * `.isLoading`) unmounts the table on EVERY background refetch, because that
 * boolean is also true for a refetch that already has `data`. The user's
 * words for this symptom: "structures disapearing" while editing a field.
 *
 * The correct shape (this file's fix):
 *   showSkeleton = isPending && !data     // first load only
 *   isRefreshing = isFetching && !!data   // keep rendering what we have
 *
 * Mock strategy: stub `@/hooks/useVistaShowcase` directly so each test
 * controls isPending/isFetching/data without going through TanStack Query or
 * the network — same pattern as
 * products/social-wiring/frontend/src/pages/WhatsAppChat.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

afterEach(async () => {
  (await import('@testing-library/react')).cleanup();
});

const mockUseVistaClientes = vi.fn();
const mockUseVistaClienteDetalhes = vi.fn();
vi.mock('@/hooks/useVistaShowcase', () => ({
  useVistaClientes: (...args: unknown[]) => mockUseVistaClientes(...args),
  useVistaClienteDetalhes: (...args: unknown[]) => mockUseVistaClienteDetalhes(...args),
}));

// `@noctusai/seed/components/ui/dialog` re-exports @radix-ui/react-dialog,
// which resolves `react` from the SEED framework's own node_modules — a
// physically separate install from this product's, so two React copies end
// up in the same tree ("Cannot read properties of null (reading 'useRef')").
// Same root cause + same fix as documented in
// `WhatsAppChat.test.tsx` (stub the module that transitively hits the
// dual-React boundary, since `ClienteDetalhesDialog`'s own body — not the
// Radix wrapper — is what Category A actually needs verified here).
vi.mock('@noctusai/seed/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open?: boolean; children?: React.ReactNode }) =>
    open ? React.createElement('div', { 'data-testid': 'dialog' }, children) : null,
  DialogContent: ({ children, className }: { children?: React.ReactNode; className?: string }) =>
    React.createElement('div', { className }, children),
  DialogHeader: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  DialogTitle: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
}));

const ITEMS = [
  { codigo: 'C0001', nome: 'Fulana de Tal', celular: '(11) 90000-0000', status: 'Ativo' },
  { codigo: 'C0002', nome: 'Beltrano', celular: null, status: null },
];

function pageResult(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      pagination: { pagina: 1, quantidade: 2, total: 2, paginas: 1 },
      fetched_at: '2026-08-31T00:00:00+00:00',
      items: ITEMS,
    },
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

const DETAIL_IDLE = {
  data: undefined,
  isPending: false,
  isFetching: false,
  isError: false,
  error: null,
};

describe('ClientesTab — refetch-unmount (Category A)', () => {
  it('keeps the table mounted through a background refetch (isFetching=true, data present)', async () => {
    mockUseVistaClienteDetalhes.mockReturnValue(DETAIL_IDLE);
    mockUseVistaClientes.mockReturnValue(pageResult({ isFetching: true }));

    const { ClientesTab } = await import('../ClientesTab');
    render(React.createElement(ClientesTab));

    // The rows must still be in the DOM — a mutation invalidating this query
    // (edit a field elsewhere, apply a filter, etc.) sets `isFetching: true`
    // on every refetch; the table must survive that, not collapse to a
    // skeleton over data that is already on the wire.
    expect(screen.getByText('Fulana de Tal')).toBeTruthy();
    expect(screen.getByText('Beltrano')).toBeTruthy();
  });

  it('shows the skeleton only on first load (isPending=true, no data yet)', async () => {
    mockUseVistaClienteDetalhes.mockReturnValue(DETAIL_IDLE);
    mockUseVistaClientes.mockReturnValue(
      pageResult({ data: undefined, isPending: true, isFetching: true }),
    );

    const { ClientesTab } = await import('../ClientesTab');
    render(React.createElement(ClientesTab));

    expect(screen.queryByText('Fulana de Tal')).toBeNull();
  });
});
