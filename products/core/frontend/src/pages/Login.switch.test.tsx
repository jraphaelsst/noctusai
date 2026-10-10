import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

const h = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
  navigate: vi.fn(),
  order: [] as string[],
  liveUser: null as null | { email: string },
}));

vi.mock('../lib/api', () => ({
  api: { get: h.apiGet, post: h.apiPost },
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
  storeMfaTokens: vi.fn(),
  createLoginMfaTransport: vi.fn(),
}));
vi.mock('../lib/auth-context', () => ({
  useAuth: () => ({ refresh: h.refresh, logout: h.logout, user: h.liveUser }),
}));
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => h.navigate,
}));

const submit = (email: string) => {
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.change(screen.getByPlaceholderText('voce@empresa.com'), { target: { value: email } });
  fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'password1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
};

beforeEach(() => {
  vi.clearAllMocks();
  h.order.length = 0;
  h.liveUser = { email: 'a@x.com' };
  h.apiGet.mockResolvedValue({ data: [{ id: 'google', name: 'Google', auth_url: 'http://localhost/oauth' }] });
  h.logout.mockImplementation(async () => { h.order.push('logout'); });
  h.apiPost.mockImplementation(async () => { h.order.push('login'); return { access_token: 't', mfa_required: false }; });
});
afterEach(() => cleanup());

describe('Login ends a live session before signing in someone else (P2.5)', () => {
  it('different user: strict logout runs BEFORE the login call', async () => {
    submit('b@x.com');
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/'));
    expect(h.logout).toHaveBeenCalledWith({ strict: true });
    expect(h.order).toEqual(['logout', 'login']);
  });

  it('same user (case-insensitive): no revoke', async () => {
    submit('A@X.com');
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/'));
    expect(h.logout).not.toHaveBeenCalled();
  });

  it('no live session: no revoke', async () => {
    h.liveUser = null;
    submit('b@x.com');
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/'));
    expect(h.logout).not.toHaveBeenCalled();
  });

  it('logout failure: visible error, no login attempt, no navigation', async () => {
    h.logout.mockRejectedValue(new Error('network'));
    submit('b@x.com');
    expect(await screen.findByText(/Não foi possível encerrar a sessão anterior/)).toBeInTheDocument();
    expect(h.apiPost).not.toHaveBeenCalled();
    expect(h.navigate).not.toHaveBeenCalled();
  });

  it('OAuth with a live session: revokes before leaving; failure blocks the redirect', async () => {
    h.logout.mockRejectedValue(new Error('network'));
    render(<MemoryRouter><Login /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /Google/ }));
    expect(await screen.findByText(/Não foi possível encerrar a sessão anterior/)).toBeInTheDocument();
    expect(h.logout).toHaveBeenCalledWith({ strict: true });
  });
});
