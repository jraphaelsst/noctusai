/**
 * Propostas — false-zero summary-card regression guard (usePropostaStats,
 * one of the 8 Cat-C-audited hooks). See src/pages/__tests__/Impostos.test.tsx
 * header for the bug-class context.
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

const mockUsePropostas = vi.fn();
const mockUsePropostaStats = vi.fn();

vi.mock('@/hooks/usePropostas', () => ({
  usePropostas: (...args: unknown[]) => mockUsePropostas(...args),
  usePropostaStats: (...args: unknown[]) => mockUsePropostaStats(...args),
  useCreateProposta: () => mockMutationResult(),
  useUpdateProposta: () => mockMutationResult(),
  useContraproposta: () => mockMutationResult(),
  useDeleteProposta: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(statsOverrides: Record<string, unknown>) {
  mockUsePropostas.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUsePropostaStats.mockReturnValue(mockQueryResult(statsOverrides));
}

async function renderPage() {
  const { default: Propostas } = await import('@/pages/Propostas');
  return render(React.createElement(MemoryRouter, null, React.createElement(Propostas)));
}

describe('Propostas — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Total" stats card shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { container } = await renderPage();

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "0" across the stats cards', async () => {
    setup({
      data: { total: 0, enviada: 0, em_analise: 0, contraproposta: 0, aceita: 0, recusada: 0, expirada: 0 },
      isPending: false,
      isFetching: false,
    });

    await renderPage();

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous "Total" stays mounted, no skeleton re-arms', async () => {
    setup({
      data: { total: 12, enviada: 4, em_analise: 3, contraproposta: 1, aceita: 2, recusada: 2, expirada: 0 },
      isPending: false,
      isFetching: true,
    });

    const { container } = await renderPage();

    expect(screen.getByText('12')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
