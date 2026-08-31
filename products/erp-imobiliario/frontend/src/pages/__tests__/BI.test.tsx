/**
 * BI (Business Intelligence dashboard) — false-zero summary-card regression
 * guard. Found while sweeping siblings of Impostos/Manutencao/Comissoes for
 * the same shape: 13 cards across 4 tabs (Vendas/Captacao/Imoveis/
 * Financeiro) rendered `vendas?.total_vendas ?? 0` unconditionally while the
 * chart BELOW the same cards, in the same component, was already correctly
 * gated on `loadingVendas` — the two were simply never wired together.
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { mockQueryResult } from '@/test-utils/mockQueryResult';
import { SelectModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);

const mockUseBIVendas = vi.fn();
const mockUseBICaptacao = vi.fn();
const mockUseBICorretores = vi.fn();
const mockUseBIImoveis = vi.fn();
const mockUseBIFinanceiro = vi.fn();

vi.mock('@/hooks/useBI', () => ({
  useBIVendas: (...args: unknown[]) => mockUseBIVendas(...args),
  useBICaptacao: (...args: unknown[]) => mockUseBICaptacao(...args),
  useBICorretores: (...args: unknown[]) => mockUseBICorretores(...args),
  useBIImoveis: (...args: unknown[]) => mockUseBIImoveis(...args),
  useBIFinanceiro: (...args: unknown[]) => mockUseBIFinanceiro(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(vendasOverrides: Record<string, unknown>) {
  mockUseBIVendas.mockReturnValue(mockQueryResult(vendasOverrides));
  mockUseBICaptacao.mockReturnValue(mockQueryResult({ data: {} }));
  mockUseBICorretores.mockReturnValue(mockQueryResult({ data: {} }));
  mockUseBIImoveis.mockReturnValue(mockQueryResult({ data: {} }));
  mockUseBIFinanceiro.mockReturnValue(mockQueryResult({ data: {} }));
}

describe('BI (Vendas tab) — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Total Vendas" shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: BI } = await import('@/pages/BI');
    const { container } = render(React.createElement(BI));

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('server-returned-zero: renders the real "0" for Total Vendas / Tempo Medio', async () => {
    setup({
      data: { total_vendas: 0, ticket_medio: 0, taxa_conversao: 0, tempo_medio_dias: 0, vendas_por_mes: [] },
      isPending: false,
      isFetching: false,
    });

    const { default: BI } = await import('@/pages/BI');
    render(React.createElement(BI));

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous "Total Vendas" stays mounted, no skeleton re-arms', async () => {
    setup({
      data: { total_vendas: 42, ticket_medio: 350000, taxa_conversao: 12.5, tempo_medio_dias: 30, vendas_por_mes: [] },
      isPending: false,
      isFetching: true,
    });

    const { default: BI } = await import('@/pages/BI');
    const { container } = render(React.createElement(BI));

    expect(screen.getByText('42')).toBeTruthy();
    expect(container.querySelectorAll('.animate-pulse').length).toBe(0);
  });
});
