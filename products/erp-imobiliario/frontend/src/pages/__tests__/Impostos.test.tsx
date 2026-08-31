/**
 * Impostos — false-zero summary-card regression guard (third mode of the
 * lying-loading-state bug class, KB § PATTERNS/frontend/lying-loading-state.md).
 *
 * `resumo?.total_devido || 0` rendered unconditionally, before
 * `useResumoImpostos` had ever resolved, as a real "R$ 0,00" — indistinguishable
 * from a genuine zero. Fixed via `SummaryValue notArrived={resumoQuery.isPending
 * && !resumoQuery.data}`.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { mockQueryResult, mockMutationResult } from '@/test-utils/mockQueryResult';
import { SelectModule, DialogModule, AlertDialogModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);
vi.mock('@noctusai/seed/components/ui/dialog', () => DialogModule);
vi.mock('@noctusai/seed/components/ui/alert-dialog', () => AlertDialogModule);

const mockUseImpostos = vi.fn();
const mockUseResumoImpostos = vi.fn();

vi.mock('@/hooks/useImpostos', () => ({
  useImpostos: (...args: unknown[]) => mockUseImpostos(...args),
  useResumoImpostos: (...args: unknown[]) => mockUseResumoImpostos(...args),
  useCreateImposto: () => mockMutationResult(),
  useUpdateImposto: () => mockMutationResult(),
  useDeleteImposto: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseImpostos.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseResumoImpostos.mockReturnValue(mockQueryResult(resumoOverrides));
}

describe('Impostos — summary cards never show a lying zero', () => {
  it('not-yet-loaded: no "R$ 0,00" is shown for Total Devido, a skeleton renders instead', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Impostos } = await import('@/pages/Impostos');
    const { container } = render(React.createElement(Impostos));

    expect(screen.queryByText(/R\$\s*0,00/)).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "R$ 0,00" (a legitimate answer)', async () => {
    setup({
      data: { total_devido: 0, total_pago: 0, total_pendente: 0, total_atrasado: 0, count_by_status: {}, quantidade: 0 },
      isPending: false,
      isFetching: false,
    });

    const { default: Impostos } = await import('@/pages/Impostos');
    render(React.createElement(Impostos));

    expect(screen.getAllByText(/R\$\s*0,00/).length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous value stays mounted, no skeleton re-arms', async () => {
    setup({
      data: { total_devido: 15000, total_pago: 5000, total_pendente: 10000, total_atrasado: 0, count_by_status: {}, quantidade: 3 },
      isPending: false,
      isFetching: true, // background refetch in flight
    });

    const { default: Impostos } = await import('@/pages/Impostos');
    const { container } = render(React.createElement(Impostos));

    expect(screen.getByText(/R\$\s*15\.000,00/)).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
