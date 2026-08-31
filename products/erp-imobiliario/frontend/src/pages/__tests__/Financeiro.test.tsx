/**
 * Financeiro — false-zero summary-card regression guard.
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

const mockUseFinanceiro = vi.fn();
const mockUseResumoFinanceiro = vi.fn();

vi.mock('@/hooks/useFinanceiro', () => ({
  useFinanceiro: (...args: unknown[]) => mockUseFinanceiro(...args),
  useResumoFinanceiro: (...args: unknown[]) => mockUseResumoFinanceiro(...args),
  useFluxoCaixa: () => mockQueryResult({ data: [] }),
  useCreateLancamento: () => mockMutationResult(),
  useUpdateLancamento: () => mockMutationResult(),
  useDeleteLancamento: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseFinanceiro.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseResumoFinanceiro.mockReturnValue(mockQueryResult(resumoOverrides));
}

describe('Financeiro — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Receitas" shows a skeleton, not "R$ 0,00"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Financeiro } = await import('@/pages/Financeiro');
    const { container } = render(React.createElement(Financeiro));

    expect(screen.queryByText(/R\$\s*0,00/)).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "R$ 0,00"', async () => {
    setup({ data: { receitas: 0, despesas: 0, saldo: 0, atrasados: 0 }, isPending: false, isFetching: false });

    const { default: Financeiro } = await import('@/pages/Financeiro');
    render(React.createElement(Financeiro));

    expect(screen.getAllByText(/R\$\s*0,00/).length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous saldo stays mounted, no skeleton re-arms', async () => {
    setup({ data: { receitas: 50000, despesas: 20000, saldo: 30000, atrasados: 2 }, isPending: false, isFetching: true });

    const { default: Financeiro } = await import('@/pages/Financeiro');
    const { container } = render(React.createElement(Financeiro));

    expect(screen.getByText(/R\$\s*30\.000,00/)).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
