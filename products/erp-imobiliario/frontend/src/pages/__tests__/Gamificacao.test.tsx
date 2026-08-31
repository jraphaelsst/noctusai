/**
 * Gamificacao — false-zero summary-card regression guard for "Meus Pontos"
 * (useMeusPontos, one of the 8 Cat-C-audited hooks) and "Conquistas"
 * (useMinhasConquistas), both hero stat cards that previously rendered
 * unconditionally.
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { mockQueryResult } from '@/test-utils/mockQueryResult';
import { SelectModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);
vi.mock('@noctusai/seed/infra', () => ({
  useAuthStore: () => ({ user: { id: 'u1' } }),
}));

const mockUseLeaderboard = vi.fn();
const mockUseMeusPontos = vi.fn();
const mockUseMinhasConquistas = vi.fn();

vi.mock('@/hooks/useGamificacao', () => ({
  useLeaderboard: (...args: unknown[]) => mockUseLeaderboard(...args),
  useMeusPontos: (...args: unknown[]) => mockUseMeusPontos(...args),
  useMinhasConquistas: (...args: unknown[]) => mockUseMinhasConquistas(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(pontosOverrides: Record<string, unknown>, conquistasOverrides: Record<string, unknown>) {
  mockUseLeaderboard.mockReturnValue(mockQueryResult({ data: [] }));
  mockUseMeusPontos.mockReturnValue(mockQueryResult(pontosOverrides));
  mockUseMinhasConquistas.mockReturnValue(mockQueryResult(conquistasOverrides));
}

describe('Gamificacao — summary cards never show a lying zero', () => {
  it('not-yet-loaded: "Meus Pontos" and "Conquistas" show a skeleton, not "0"', async () => {
    setup(
      { data: undefined, isPending: true, isFetching: true },
      { data: undefined, isPending: true, isFetching: true },
    );

    const { default: Gamificacao } = await import('@/pages/Gamificacao');
    const { container } = render(React.createElement(Gamificacao));

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('server-returned-zero: renders the real "0" pontos', async () => {
    setup(
      { data: { data: [], pagination: null, total_pontos: 0 }, isPending: false, isFetching: false },
      { data: [], isPending: false, isFetching: false },
    );

    const { default: Gamificacao } = await import('@/pages/Gamificacao');
    render(React.createElement(Gamificacao));

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous pontos total stays mounted, no skeleton re-arms', async () => {
    setup(
      { data: { data: [], pagination: null, total_pontos: 340 }, isPending: false, isFetching: true },
      { data: [], isPending: false, isFetching: true },
    );

    const { default: Gamificacao } = await import('@/pages/Gamificacao');
    const { container } = render(React.createElement(Gamificacao));

    expect(screen.getByText('340')).toBeTruthy();
    expect(container.querySelectorAll('.animate-pulse').length).toBe(0);
  });
});
