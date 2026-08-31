/**
 * Assinaturas — Mode A (isLoading skeleton gate on the list) + false-zero
 * summary-card regression guard, found while sweeping siblings of
 * Impostos/Manutencao/Comissoes for the same shape.
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

const mockUseAssinaturas = vi.fn();
const mockUseResumoAssinaturas = vi.fn();

vi.mock('@/hooks/useAssinaturas', () => ({
  useAssinaturas: (...args: unknown[]) => mockUseAssinaturas(...args),
  useResumoAssinaturas: (...args: unknown[]) => mockUseResumoAssinaturas(...args),
  useEnviarAssinatura: () => mockMutationResult(),
  useCancelarAssinatura: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(resumoOverrides: Record<string, unknown>) {
  mockUseAssinaturas.mockReturnValue(mockQueryResult({ data: { data: [], pagination: null } }));
  mockUseResumoAssinaturas.mockReturnValue(mockQueryResult(resumoOverrides));
}

describe('Assinaturas — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Pendentes" shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Assinaturas } = await import('@/pages/Assinaturas');
    const { container } = render(React.createElement(Assinaturas));

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: renders the real "0"', async () => {
    setup({
      data: { pendentes: 0, enviadas: 0, assinadas: 0, recusadas: 0, expiradas: 0, canceladas: 0, total: 0 },
      isPending: false,
      isFetching: false,
    });

    const { default: Assinaturas } = await import('@/pages/Assinaturas');
    render(React.createElement(Assinaturas));

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: previous counts stay mounted, no skeleton re-arms', async () => {
    setup({
      data: { pendentes: 5, enviadas: 2, assinadas: 8, recusadas: 1, expiradas: 0, canceladas: 0, total: 16 },
      isPending: false,
      isFetching: true,
    });

    const { default: Assinaturas } = await import('@/pages/Assinaturas');
    const { container } = render(React.createElement(Assinaturas));

    expect(screen.getByText('5')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
