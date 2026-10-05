import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Security } from './Security';

const { get, post, del } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), del: vi.fn() }));

vi.mock('../lib/api', () => ({
  api: { get, post, delete: del },
  storeMfaTokens: vi.fn(),
}));

const renderPage = () =>
  render(
    <MemoryRouter>
      <Security />
    </MemoryRouter>,
  );

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe('Security page', () => {
  it('shows a skeleton while the status loads, never the empty state', () => {
    get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('heading', { name: 'Segurança' })).toBeInTheDocument();
    expect(screen.getByTestId('mfa-skeleton')).toBeInTheDocument();
    expect(screen.queryByText('Adicionar dispositivo')).not.toBeInTheDocument();
  });

  it('empty state: no devices yet offers enrolment', async () => {
    get.mockResolvedValue({ enrolled: false, aal: 'aal1', factors: [] });
    renderPage();
    expect(await screen.findByText('Adicionar dispositivo')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/api/auth/mfa/status');
  });

  it('lists enrolled devices and allows removing one', async () => {
    get.mockResolvedValue({
      enrolled: true,
      aal: 'aal2',
      factors: [{ id: 'f1', friendly_name: 'Celular', status: 'verified', created_at: '2026-10-05T00:00:00Z' }],
    });
    del.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText('Celular')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Remover Celular'));
    fireEvent.click(await screen.findByText('Confirmar remoção'));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/api/auth/mfa/factors/f1'));
  });

  it('error state: a failed status load is reported with a retry, not an empty list', async () => {
    get.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Adicionar dispositivo')).not.toBeInTheDocument();
  });
});
