/**
 * Central-login password recovery: /esqueci-senha and /redefinir-senha
 * (contract: products/core/CONTRACTS/sso-entry.md).
 */
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EsqueciSenha } from './EsqueciSenha';
import { RedefinirSenha } from './RedefinirSenha';

const h = vi.hoisted(() => ({
  resetPasswordForEmail: vi.fn(),
  setSession: vi.fn(),
  updateUser: vi.fn(),
  apiPost: vi.fn(),
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
  refresh: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('../lib/recovery-supabase', async (orig) => ({
  ...(await orig<typeof import('../lib/recovery-supabase')>()),
  createRecoveryClient: () => ({
    auth: { resetPasswordForEmail: h.resetPasswordForEmail, setSession: h.setSession, updateUser: h.updateUser },
  }),
  recoveryRedirectTo: (q: string) => `https://noctusai.com/redefinir-senha${q}`,
}));
vi.mock('../lib/api', () => ({
  api: { get: vi.fn(), post: h.apiPost },
  setToken: h.setToken,
  setRefreshToken: h.setRefreshToken,
}));
vi.mock('../lib/auth-context', () => ({ useAuth: () => ({ refresh: h.refresh }) }));
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => h.navigate,
}));

const replace = vi.fn();
const TOKEN = { sso_token: 't', product_slug: 'agents', redirect_url: 'https://agents.noctusai.com/sso#token=t' };

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/');
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, replace, hash: '', pathname: '/redefinir-senha', search: '' },
  });
  h.resetPasswordForEmail.mockResolvedValue({ error: null });
  h.setSession.mockResolvedValue({ error: null });
  h.updateUser.mockResolvedValue({ error: null, data: { user: { email: 'a@b.com' } } });
  h.apiPost.mockImplementation(async (p: string) => (p === '/api/sso/token' ? TOKEN : { access_token: 'x', refresh_token: 'r' }));
  h.refresh.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

const setHash = (hash: string) => {
  (window.location as { hash: string }).hash = hash;
};
const RECOVERY = '#access_token=A&refresh_token=R&type=recovery';
const renderEsqueci = (q = '') => render(<MemoryRouter initialEntries={[`/esqueci-senha${q}`]}><EsqueciSenha /></MemoryRouter>);
const renderRedefinir = (q = '') => render(<MemoryRouter initialEntries={[`/redefinir-senha${q}`]}><RedefinirSenha /></MemoryRouter>);

describe('/esqueci-senha', () => {
  it('sends the link with redirectTo CORE_URL/redefinir-senha carrying produto and next', async () => {
    renderEsqueci('?produto=agents&next=/leads');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar link' }));
    await waitFor(() => expect(h.resetPasswordForEmail).toHaveBeenCalledWith('a@b.com', {
      redirectTo: 'https://noctusai.com/redefinir-senha?produto=agents&next=%2Fleads',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('enviamos um link');
  });

  it('non-path next is dropped from the redirectTo', async () => {
    renderEsqueci('?produto=agents&next=//evil.example');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar link' }));
    await waitFor(() => expect(h.resetPasswordForEmail).toHaveBeenCalledWith('a@b.com', {
      redirectTo: 'https://noctusai.com/redefinir-senha?produto=agents',
    }));
  });

  it('invalid email: inline error wired with aria-invalid/aria-describedby, nothing sent', () => {
    renderEsqueci();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar link' }));
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/email válido/);
    expect(h.resetPasswordForEmail).not.toHaveBeenCalled();
  });

  it('GoTrue 429 over_email_send_rate_limit: visible countdown that disables resend, then re-enables', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    h.resetPasswordForEmail.mockResolvedValue({ error: { status: 429, code: 'over_email_send_rate_limit' } });
    renderEsqueci();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Tente de novo em 60s');
    expect(screen.getByRole('button', { name: 'Aguarde 60s' })).toBeDisabled();
    await act(async () => { vi.advanceTimersByTime(30_500); });
    expect(screen.getByRole('alert')).toHaveTextContent(/Tente de novo em (29|30)s/);
    await act(async () => { vi.advanceTimersByTime(31_000); });
    expect(screen.getByRole('button', { name: 'Enviar link' })).toBeEnabled();
  });

  it('other failure: visible plain-language error, form stays', async () => {
    h.resetPasswordForEmail.mockResolvedValue({ error: { status: 500, code: 'unexpected_failure' } });
    renderEsqueci();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível enviar o email');
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('back link keeps the product', () => {
    renderEsqueci('?produto=agents&next=/x');
    expect(screen.getByRole('link', { name: 'Voltar ao login' })).toHaveAttribute('href', '/login?produto=agents&next=%2Fx');
  });
});

describe('/redefinir-senha', () => {
  const submit = (pw = 'novasenha1', confirm = pw) => {
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: pw } });
    fireEvent.change(screen.getByLabelText('Confirmar nova senha'), { target: { value: confirm } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova senha' }));
  };

  it('no recovery token in the URL: visible "link inválido" with a way to ask again (product kept)', () => {
    renderRedefinir('?produto=agents');
    expect(screen.getByRole('alert')).toHaveTextContent('Link inválido ou expirado');
    expect(screen.getByRole('link', { name: 'Pedir novo link' })).toHaveAttribute('href', '/esqueci-senha?produto=agents');
  });

  it('mismatch / too short: inline errors, no call', () => {
    setHash(RECOVERY);
    renderRedefinir();
    submit('curta', 'outra');
    expect(screen.getByLabelText('Nova senha')).toHaveAccessibleDescription(/ao menos 8/);
    expect(screen.getByLabelText('Confirmar nova senha')).toHaveAccessibleDescription(/não são iguais/);
    expect(h.updateUser).not.toHaveBeenCalled();
  });

  it('resets, signs in through core login, then launches the product with next', async () => {
    setHash(RECOVERY);
    renderRedefinir('?produto=agents&next=/leads');
    submit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`${TOKEN.redirect_url}&next=%2Fleads`));
    expect(h.setSession).toHaveBeenCalledWith({ access_token: 'A', refresh_token: 'R' });
    expect(h.updateUser).toHaveBeenCalledWith({ password: 'novasenha1' });
    expect(h.apiPost).toHaveBeenCalledWith('/api/auth/login', { email: 'a@b.com', password: 'novasenha1' });
    expect(h.setToken).toHaveBeenCalledWith('x');
    expect(h.apiPost.mock.calls.filter((c) => c[0] === '/api/sso/token')).toHaveLength(1);
  });

  it('without a product: continues to core home', async () => {
    setHash(RECOVERY);
    renderRedefinir();
    submit();
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/', { replace: true }));
    expect(replace).not.toHaveBeenCalled();
  });

  it('MFA-enrolled user: no session is created here; sent to /login with the product for the challenge', async () => {
    h.apiPost.mockResolvedValue({ access_token: 'pending', mfa_required: true });
    setHash(RECOVERY);
    renderRedefinir('?produto=agents&next=/leads');
    submit();
    await waitFor(() => expect(h.navigate).toHaveBeenCalledWith('/login?produto=agents&next=%2Fleads', { replace: true }));
    expect(h.setToken).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('same_password: field error, no login attempt', async () => {
    h.updateUser.mockResolvedValue({ error: { code: 'same_password' }, data: { user: null } });
    setHash(RECOVERY);
    renderRedefinir();
    submit();
    expect(await screen.findByText(/diferente da atual/)).toBeInTheDocument();
    expect(h.apiPost).not.toHaveBeenCalled();
  });

  it('expired token at setSession: visible error, nothing changed', async () => {
    h.setSession.mockResolvedValue({ error: { message: 'expired' } });
    setHash(RECOVERY);
    renderRedefinir();
    submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('link expirou');
    expect(h.updateUser).not.toHaveBeenCalled();
  });

  it('password saved but product launch refused: says so, on core, no redirect', async () => {
    h.apiPost.mockImplementation(async (p: string) => {
      if (p === '/api/sso/token') throw new Error('Organização não tem acesso a este produto');
      return { access_token: 'x' };
    });
    setHash(RECOVERY);
    renderRedefinir('?produto=agents');
    submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Senha alterada, mas não foi possível abrir o produto');
    expect(replace).not.toHaveBeenCalled();
  });

  it('takes the tokens out of the address bar', () => {
    setHash(RECOVERY);
    const spy = vi.spyOn(window.history, 'replaceState');
    renderRedefinir();
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
