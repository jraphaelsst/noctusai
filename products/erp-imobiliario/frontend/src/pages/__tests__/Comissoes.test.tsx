/**
 * Comissoes — false-zero summary-card regression guard.
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

const mockUseComissoes = vi.fn();
const mockUseComissaoResumo = vi.fn();

vi.mock('@/hooks/useComissoes', () => ({
  useComissoes: (...args: unknown[]) => mockUseComissoes(...args),
  useComissaoResumo: (...args: unknown[]) => mockUseComissaoResumo(...args),
  useCreateComissao: () => mockMutationResult(),
  useUpdateComissao: () => mockMutationResult(),
  useDeleteComissao: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseComissoes.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseComissaoResumo.mockReturnValue(mockQueryResult(resumoOverrides));
}

describe('Comissoes — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Total Geral" shows a skeleton, not "R$ 0,00"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Comissoes } = await import('@/pages/Comissoes');
    const { container } = render(React.createElement(Comissoes));

    expect(screen.queryByText(/R\$\s*0,00/)).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "R$ 0,00" and "0 comissoes"', async () => {
    setup({
      data: {
        totais: { total_pendente: 0, total_aprovada: 0, total_paga: 0, total_cancelada: 0, total_geral: 0, quantidade: 0 },
        por_corretor: [],
      },
      isPending: false,
      isFetching: false,
    });

    const { default: Comissoes } = await import('@/pages/Comissoes');
    render(React.createElement(Comissoes));

    expect(screen.getAllByText(/R\$\s*0,00/).length).toBeGreaterThan(0);
    expect(screen.getByText(/0 comissoes/)).toBeTruthy();
  });

  it('refetch-with-data: the previous total stays mounted, no skeleton re-arms', async () => {
    setup({
      data: {
        totais: { total_pendente: 1000, total_aprovada: 2000, total_paga: 3000, total_cancelada: 0, total_geral: 6000, quantidade: 4 },
        por_corretor: [],
      },
      isPending: false,
      isFetching: true,
    });

    const { default: Comissoes } = await import('@/pages/Comissoes');
    const { container } = render(React.createElement(Comissoes));

    expect(screen.getByText(/R\$\s*6\.000,00/)).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
