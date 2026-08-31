/**
 * Contratos — false-zero summary-card regression guard, including the
 * `resumo ? Object.values(resumo.por_status).reduce(...) : 0` shape (a
 * carefully-truthy-checked variant of the same lie: it still rendered a
 * bare "0" instead of a skeleton before the query had ever resolved).
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { mockQueryResult, mockMutationResult } from '@/test-utils/mockQueryResult';
import { SelectModule, DialogModule, AlertDialogModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);
vi.mock('@noctusai/seed/components/ui/dialog', () => DialogModule);
vi.mock('@noctusai/seed/components/ui/alert-dialog', () => AlertDialogModule);

const mockUseContratos = vi.fn();
const mockUseResumoContratos = vi.fn();

vi.mock('@/hooks/useContratos', () => ({
  useContratos: (...args: unknown[]) => mockUseContratos(...args),
  useResumoContratos: (...args: unknown[]) => mockUseResumoContratos(...args),
  useCreateContrato: () => mockMutationResult(),
  useUpdateContrato: () => mockMutationResult(),
  useDeleteContrato: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseContratos.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseResumoContratos.mockReturnValue(mockQueryResult(resumoOverrides));
}

async function renderPage() {
  const { default: Contratos } = await import('@/pages/Contratos');
  return render(React.createElement(MemoryRouter, null, React.createElement(Contratos)));
}

describe('Contratos — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Total Contratos" shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { container } = await renderPage();

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "0" for the Object.values(por_status).reduce(...) card', async () => {
    setup({
      data: {
        por_status: { ativo: 0, encerrado: 0 },
        por_tipo: {},
        valor_total: 0,
        inadimplencia: { total_parcelas: 0, parcelas_atrasadas: 0, valor_atrasado: 0, taxa_inadimplencia: 0 },
      },
      isPending: false,
      isFetching: false,
    });

    await renderPage();

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous total stays mounted, no skeleton re-arms', async () => {
    setup({
      data: {
        por_status: { ativo: 6, encerrado: 2 },
        por_tipo: {},
        valor_total: 500000,
        inadimplencia: { total_parcelas: 20, parcelas_atrasadas: 3, valor_atrasado: 9000, taxa_inadimplencia: 15 },
      },
      isPending: false,
      isFetching: true,
    });

    const { container } = await renderPage();

    // ativo(6) + encerrado(2) = 8, the reduce()'d "Total Contratos" card.
    expect(screen.getByText('8')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
