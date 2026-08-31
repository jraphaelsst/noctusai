/**
 * Manutencao — false-zero summary-card regression guard.
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

const mockUseManutencao = vi.fn();
const mockUseResumoManutencao = vi.fn();

vi.mock('@/hooks/useManutencao', () => ({
  useManutencao: (...args: unknown[]) => mockUseManutencao(...args),
  useResumoManutencao: (...args: unknown[]) => mockUseResumoManutencao(...args),
  useCreateOrdemServico: () => mockMutationResult(),
  useUpdateOrdemServico: () => mockMutationResult(),
  useDeleteOrdemServico: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseManutencao.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseResumoManutencao.mockReturnValue(mockQueryResult(resumoOverrides));
}

describe('Manutencao — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Abertas" shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Manutencao } = await import('@/pages/Manutencao');
    const { container } = render(React.createElement(Manutencao));

    expect(container.querySelector('.animate-pulse')).toBeTruthy();
    // "0" would be the buggy fallback for every one of the 4 cards; none
    // should be present while the summary query has never resolved.
    expect(screen.queryByText('0')).toBeNull();
  });

  it('server-returned-zero: "Abertas" renders the real "0"', async () => {
    setup({
      data: { por_status: { aberto: 0, em_andamento: 0 }, tempo_medio_resolucao: 0, atrasados: 0, custo_total: 0 },
      isPending: false,
      isFetching: false,
    });

    const { default: Manutencao } = await import('@/pages/Manutencao');
    render(React.createElement(Manutencao));

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: previous counts stay mounted, no skeleton re-arms', async () => {
    setup({
      data: { por_status: { aberto: 7, em_andamento: 3 }, tempo_medio_resolucao: 4, atrasados: 1, custo_total: 12000 },
      isPending: false,
      isFetching: true,
    });

    const { default: Manutencao } = await import('@/pages/Manutencao');
    const { container } = render(React.createElement(Manutencao));

    expect(screen.getByText('7')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
