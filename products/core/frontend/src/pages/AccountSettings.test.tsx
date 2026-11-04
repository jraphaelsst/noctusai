import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AccountSettings } from './AccountSettings';

const { patch, authState } = vi.hoisted(() => ({
  patch: vi.fn(),
  authState: { current: {} as Record<string, unknown> },
}));

vi.mock('../lib/api', () => ({ api: { patch } }));
vi.mock('../lib/auth-context', () => ({ useAuth: () => authState.current }));

const updateUser = vi.fn();
const refresh = vi.fn();
const baseUser = { id: 'u1', nome: 'Ana', email: 'ana@x.com', role: 'user', org_id: 'o1', telefone: null };

const renderPage = () =>
  render(
    <MemoryRouter>
      <AccountSettings />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  authState.current = { user: baseUser, loading: false, unavailable: false, updateUser, refresh };
});
afterEach(() => cleanup());

describe('AccountSettings WhatsApp', () => {
  it('shows a skeleton while the profile loads, never an empty form', () => {
    authState.current = { user: null, loading: true, unavailable: false, updateUser, refresh };
    renderPage();
    expect(screen.getByTestId('account-skeleton')).toBeInTheDocument();
    expect(screen.queryByLabelText('WhatsApp')).not.toBeInTheDocument();
  });

  it('offers a retry when the profile is unavailable', () => {
    authState.current = { user: null, loading: false, unavailable: true, updateUser, refresh };
    renderPage();
    fireEvent.click(screen.getByText('Tentar novamente'));
    expect(refresh).toHaveBeenCalled();
  });

  it('renders the stored number with the helper text', () => {
    authState.current = { ...authState.current, user: { ...baseUser, telefone: '+5511994573387' } };
    renderPage();
    expect(screen.getByLabelText('WhatsApp')).toHaveValue('+5511994573387');
    expect(screen.getByText('Usado para receber relatórios e alertas dos agentes (ex.: Julia).')).toBeInTheDocument();
  });

  it('saves the number and writes the server-normalized row into the auth context', async () => {
    patch.mockResolvedValue({ data: { nome: 'Ana', avatar_url: null, telefone: '+5511994573387' } });
    renderPage();
    fireEvent.change(screen.getByLabelText('WhatsApp'), { target: { value: '(11) 99457-3387' } });
    fireEvent.click(screen.getByText('Salvar Alterações'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/api/auth/profile', { nome: 'Ana', telefone: '(11) 99457-3387' }),
    );
    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith({ nome: 'Ana', avatar_url: null, telefone: '+5511994573387' }),
    );
    expect(await screen.findByText('Perfil atualizado com sucesso!')).toBeInTheDocument();
  });

  it('clearing the field sends an empty string', async () => {
    authState.current = { ...authState.current, user: { ...baseUser, telefone: '+5511994573387' } };
    patch.mockResolvedValue({ data: { nome: 'Ana', telefone: null } });
    renderPage();
    fireEvent.change(screen.getByLabelText('WhatsApp'), { target: { value: '' } });
    fireEvent.click(screen.getByText('Salvar Alterações'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/api/auth/profile', { nome: 'Ana', telefone: '' }),
    );
  });

  it('shows the server refusal and does not touch the auth context', async () => {
    patch.mockRejectedValue(new Error('Telefone inválido. Use o formato com DDD.'));
    renderPage();
    fireEvent.change(screen.getByLabelText('WhatsApp'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByText('Salvar Alterações'));
    expect(await screen.findByText(/Telefone inválido/)).toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });
});
