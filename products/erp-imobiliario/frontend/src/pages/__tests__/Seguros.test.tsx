/**
 * Seguros — false-zero summary-card regression guard. Unlike the other
 * pages in this sweep, three of the four cards (Apolices Ativas, Cobertura
 * Total, Premio Anual) are LOCALLY computed from the `seguros` list query
 * (not a separate `resumo` hook) — the fix gates them on the list query's
 * own notArrived signal (`showSegurosSkeleton`); only "Vencendo em 30d" has
 * its own query (`useVencimentosSeguros`).
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { mockQueryResult, mockMutationResult } from '@/test-utils/mockQueryResult';
import { SelectModule, DialogModule, AlertDialogModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);
vi.mock('@noctusai/seed/components/ui/dialog', () => DialogModule);
vi.mock('@noctusai/seed/components/ui/alert-dialog', () => AlertDialogModule);

const mockUseSeguros = vi.fn();
const mockUseVencimentosSeguros = vi.fn();

vi.mock('@/hooks/useSeguros', () => ({
  useSeguros: (...args: unknown[]) => mockUseSeguros(...args),
  useVencimentosSeguros: (...args: unknown[]) => mockUseVencimentosSeguros(...args),
  useCreateSeguro: () => mockMutationResult(),
  useUpdateSeguro: () => mockMutationResult(),
  useDeleteSeguro: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Seguros — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Apolices Ativas" shows a skeleton, not "0"', async () => {
    mockUseSeguros.mockReturnValue(mockQueryResult({ data: undefined, isPending: true, isFetching: true }));
    mockUseVencimentosSeguros.mockReturnValue(mockQueryResult({ data: undefined, isPending: true, isFetching: true }));

    const { default: Seguros } = await import('@/pages/Seguros');
    const { container } = render(React.createElement(Seguros));

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: an empty (but resolved) list and vencimentos render the real "0"s', async () => {
    mockUseSeguros.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null }, isPending: false, isFetching: false }));
    mockUseVencimentosSeguros.mockReturnValue(mockQueryResult({ data: [], isPending: false, isFetching: false }));

    const { default: Seguros } = await import('@/pages/Seguros');
    render(React.createElement(Seguros));

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous computed "Apolices Ativas" count stays mounted, no skeleton re-arms', async () => {
    const seguros = [
      { id: 's1', status: 'ativo', valor_cobertura: 100000, valor_premio: 2000 },
    ];
    mockUseSeguros.mockReturnValue(
      mockQueryResult({ data: { data: seguros, pagination: null }, isPending: false, isFetching: true }),
    );
    mockUseVencimentosSeguros.mockReturnValue(
      mockQueryResult({ data: [{ id: 's1' }], isPending: false, isFetching: true }),
    );

    const { default: Seguros } = await import('@/pages/Seguros');
    const { container } = render(React.createElement(Seguros));

    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
