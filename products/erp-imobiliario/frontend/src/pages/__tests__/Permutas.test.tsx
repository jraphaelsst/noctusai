/**
 * Permutas (MatchesTab) — false-zero summary-card regression guard for the
 * locally-computed `stats` object (total / pendentes / aceitos / mediaScore
 * derived from `useMatches()`, one of the 8 Cat-C-audited hooks) — rendered
 * unconditionally above the already-correctly-gated match list.
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { mockQueryResult, mockMutationResult } from '@/test-utils/mockQueryResult';
import { DialogModule, SelectModule, TabsModule, ProgressModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/dialog', () => DialogModule);
vi.mock('@noctusai/seed/components/ui/select', () => SelectModule);
// Real Radix Tabs only mounts the ACTIVE panel's children by default —
// stub it so both PerfisTab and MatchesTab render unconditionally; this
// test targets MatchesTab's stats cards regardless of which tab is
// "active" (Permutas defaults to "perfis").
vi.mock('@noctusai/seed/components/ui/tabs', () => TabsModule);
vi.mock('@noctusai/seed/components/ui/progress', () => ProgressModule);

const mockUsePerfilsPermuta = vi.fn();
const mockUseCreatePerfilPermuta = vi.fn();

vi.mock('@/hooks/usePermutas', () => ({
  usePerfilsPermuta: (...args: unknown[]) => mockUsePerfilsPermuta(...args),
  useCreatePerfilPermuta: (...args: unknown[]) => mockUseCreatePerfilPermuta(...args),
}));

const mockUseMatches = vi.fn();
const mockUseMatchCounts = vi.fn();

vi.mock('@/hooks/useMatches', () => ({
  useMatches: (...args: unknown[]) => mockUseMatches(...args),
  useMatchCounts: (...args: unknown[]) => mockUseMatchCounts(...args),
  useRecalcularMatches: () => mockMutationResult(),
  useAtualizarStatusMatch: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(matchesOverrides: Record<string, unknown>) {
  mockUsePerfilsPermuta.mockReturnValue(mockQueryResult({ data: [] }));
  mockUseCreatePerfilPermuta.mockReturnValue(mockMutationResult());
  mockUseMatchCounts.mockReturnValue(mockQueryResult({ data: {} }));
  // MatchesTab's own useMatches() (no filter args) AND PerfilMatchesSection's
  // per-profile useMatches(...) both resolve through this same mock — no
  // profiles exist in this test (usePerfilsPermuta returns []), so only the
  // MatchesTab call fires.
  mockUseMatches.mockReturnValue(mockQueryResult(matchesOverrides));
}

async function renderPage() {
  const { default: Permutas } = await import('@/pages/Permutas');
  return render(React.createElement(MemoryRouter, null, React.createElement(Permutas)));
}

describe('Permutas (MatchesTab) — stats cards never show a lying zero', () => {
  it('not-yet-loaded: "Total" stats card shows a skeleton, not "0"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { container } = await renderPage();

    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('server-returned-zero: renders the real "0" across the stats cards', async () => {
    setup({ data: [], isPending: false, isFetching: false });

    await renderPage();

    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
  });

  it('refetch-with-data: the previous "Total" stays mounted, no skeleton re-arms', async () => {
    setup({
      data: [
        { id: 'm1', score: 80, status: 'pendente', detalhes: { gap_valor: 0 } },
        { id: 'm2', score: 60, status: 'aceito', detalhes: { gap_valor: 0 } },
      ],
      isPending: false,
      isFetching: true,
    });

    const { container } = await renderPage();

    expect(screen.getByText('2')).toBeTruthy();
    expect(container.querySelectorAll('.animate-pulse').length).toBe(0);
  });
});
