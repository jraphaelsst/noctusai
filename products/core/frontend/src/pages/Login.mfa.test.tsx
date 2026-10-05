import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

const h = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  setToken: vi.fn(),
  storeMfaTokens: vi.fn(),
  transport: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  createLoginMfaTransport: vi.fn(),
  refresh: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  api: { get: h.apiGet, post: h.apiPost },
  setToken: h.setToken,
  setRefreshToken: vi.fn(),
  storeMfaTokens: h.storeMfaTokens,
  createLoginMfaTransport: h.createLoginMfaTransport,
}));
vi.mock('../lib/auth-context', () => ({ useAuth: () => ({ refresh: h.refresh }) }));
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => h.navigate,
}));

const submitLogin = async () => {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByPlaceholderText('voce@empresa.com'), { target: { value: 'a@b.com' } });
  fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'password1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
};

beforeEach(() => {
  vi.clearAllMocks();
  h.apiGet.mockResolvedValue({ data: [] });
  h.createLoginMfaTransport.mockReturnValue(h.transport);
  h.transport.get.mockResolvedValue({
    enrolled: true,
    aal: 'aal1',
    factors: [{ id: 'f1', friendly_name: 'Celular', status: 'verified', created_at: 'x' }],
  });
});
afterEach(() => cleanup());

describe('Login MFA challenge step', () => {
  it('without factors: stores the session and enters the app (unchanged)', async () => {
    h.apiPost.mockResolvedValue({ access_token: 'a1', refresh_token: 'r1', mfa_required: false, mfa_factors: [] });
    await submitLogin();
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/'));
    expect(h.setToken).toHaveBeenCalledWith('a1');
    expect(h.createLoginMfaTransport).not.toHaveBeenCalled();
  });

  it('with a factor: shows the challenge and does NOT store the aal1 token', async () => {
    h.apiPost.mockResolvedValue({ access_token: 'aal1', refresh_token: 'r1', mfa_required: true, mfa_factors: [{ id: 'f1', friendly_name: 'Celular' }] });
    await submitLogin();
    expect(await screen.findByLabelText('Código de 6 números')).toBeInTheDocument();
    expect(h.createLoginMfaTransport).toHaveBeenCalledWith('aal1');
    expect(h.setToken).not.toHaveBeenCalled();
    expect(h.navigate).not.toHaveBeenCalled();
  });

  it('a verified code stores the aal2 tokens and enters the app', async () => {
    h.apiPost.mockResolvedValue({ access_token: 'aal1', refresh_token: 'r1', mfa_required: true, mfa_factors: [] });
    h.transport.post.mockResolvedValue({ aal: 'aal2', access_token: 'aal2tok', refresh_token: 'r2' });
    await submitLogin();
    fireEvent.change(await screen.findByLabelText('Código de 6 números'), { target: { value: '123456' } });
    fireEvent.click(screen.getByText('Confirmar'));
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/'));
    expect(h.transport.post).toHaveBeenCalledWith('/api/auth/mfa/verify', { factor_id: 'f1', code: '123456' });
    expect(h.storeMfaTokens).toHaveBeenCalledWith(expect.objectContaining({ access_token: 'aal2tok' }));
    expect(h.refresh).toHaveBeenCalled();
  });

  it('cancelling returns to the login form without a session', async () => {
    h.apiPost.mockResolvedValue({ access_token: 'aal1', refresh_token: 'r1', mfa_required: true, mfa_factors: [] });
    await submitLogin();
    await screen.findByLabelText('Código de 6 números');
    fireEvent.click(screen.getByText('Cancelar'));
    await waitFor(() => expect(screen.queryByLabelText('Código de 6 números')).not.toBeInTheDocument());
    expect(h.setToken).not.toHaveBeenCalled();
  });
});
