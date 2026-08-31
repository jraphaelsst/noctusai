/**
 * Notificacoes — false-zero header regression guard: "{naoLidas} não
 * lida(s)" collapsed to the friendly-but-false "Tudo em dia" ("all caught
 * up") the instant the page mounted, before `useContagemNaoLidas` had ever
 * resolved — the same lie as a bare "0", just phrased as a claim instead of
 * a digit.
 * See src/pages/__tests__/Impostos.test.tsx header for the bug-class context.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { mockQueryResult, mockMutationResult } from '@/test-utils/mockQueryResult';
import { TabsModule, SwitchModule, ScrollAreaModule } from '@/test-utils/seedUiStubs';

vi.mock('@noctusai/seed/components/ui/tabs', () => TabsModule);
vi.mock('@noctusai/seed/components/ui/switch', () => SwitchModule);
vi.mock('@noctusai/seed/components/ui/scroll-area', () => ScrollAreaModule);

const mockUseNotificacoes = vi.fn();
const mockUseContagemNaoLidas = vi.fn();

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: (...args: unknown[]) => mockUseNotificacoes(...args),
  useContagemNaoLidas: (...args: unknown[]) => mockUseContagemNaoLidas(...args),
  useMarcarComoLida: () => mockMutationResult(),
  useMarcarTodasComoLidas: () => mockMutationResult(),
  useNotificacaoPreferencias: () => mockQueryResult({ data: { data: [] } }),
  useAtualizarPreferencia: () => mockMutationResult(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup(contagemOverrides: Record<string, unknown>) {
  mockUseNotificacoes.mockReturnValue(mockQueryResult({ data: { data: [] } }));
  mockUseContagemNaoLidas.mockReturnValue(mockQueryResult(contagemOverrides));
}

describe('Notificacoes — header never shows a lying "Tudo em dia"', () => {
  it('not-yet-loaded: shows a skeleton, never "Tudo em dia"', async () => {
    setup({ data: undefined, isPending: true, isFetching: true });

    const { default: Notificacoes } = await import('@/pages/Notificacoes');
    const { container } = render(React.createElement(Notificacoes));

    expect(screen.queryByText('Tudo em dia')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('server-returned-zero: "Tudo em dia" is a real, resolved answer', async () => {
    setup({ data: { data: { nao_lidas: 0 } }, isPending: false, isFetching: false });

    const { default: Notificacoes } = await import('@/pages/Notificacoes');
    render(React.createElement(Notificacoes));

    expect(screen.getByText('Tudo em dia')).toBeTruthy();
  });

  it('refetch-with-data: the previous unread count stays mounted, no skeleton re-arms', async () => {
    setup({ data: { data: { nao_lidas: 4 } }, isPending: false, isFetching: true });

    const { default: Notificacoes } = await import('@/pages/Notificacoes');
    const { container } = render(React.createElement(Notificacoes));

    expect(screen.getByText('4 não lidas')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
