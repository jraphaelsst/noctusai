/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const coreDelete = vi.fn();
vi.mock('@noctusai/seed/infra', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a) },
  coreApi: { delete: (...a: unknown[]) => coreDelete(...a) },
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

import { ActingAsBanner } from './ActingAsBanner';

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ActingAsBanner />
    </QueryClientProvider>,
  );
}

const acting = { session_id: 's1', org_id: 'o1', org_nome: 'Imobiliária Acme', started_at: '2026-10-06T10:00:00Z' };

describe('ActingAsBanner', () => {
  beforeEach(() => { apiGet.mockReset(); coreDelete.mockReset(); });
  afterEach(() => cleanup());

  it('renders nothing when acting is null', async () => {
    apiGet.mockResolvedValue({ org: { id: 'o', nome: 'N' }, home_org: { id: 'o', nome: 'N' }, acting: null });
    mount();
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/me/context'));
    expect(screen.queryByTestId('acting-as-banner')).toBeNull();
  });

  it('renders nothing when the context call fails', async () => {
    apiGet.mockRejectedValue(new Error('403'));
    mount();
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(screen.queryByTestId('acting-as-banner')).toBeNull();
  });

  it('shows the org and Sair calls core DELETE then navigates to core admin', async () => {
    apiGet.mockResolvedValue({ org: { id: 'o1', nome: 'Imobiliária Acme' }, home_org: { id: 'h', nome: 'Noctus' }, acting });
    coreDelete.mockResolvedValue({ ended: true });
    const assign = vi.fn();
    const orig = window.location;
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, assign } });
    mount();
    expect(await screen.findByText('Imobiliária Acme')).toBeInTheDocument();
    expect(screen.getByText(/Você está acessando como/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sair' }));
    await waitFor(() => expect(coreDelete).toHaveBeenCalledWith('/api/admin/act-as/current'));
    await waitFor(() => expect(assign).toHaveBeenCalledWith(expect.stringMatching(/\/admin\/organizacoes$/)));
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });
});
