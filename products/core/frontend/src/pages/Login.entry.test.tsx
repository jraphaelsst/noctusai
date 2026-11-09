/**
 * Central login entry (contract: products/core/docs/sso-entry-contract.md): /login?produto=&next=&prompt=
 */
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

const h = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
  navigate: vi.fn(),
  auth: { user: null as null | { email: string }, loading: false },
  mfaCapture: { onVerified: null as null | ((r: unknown) => Promise<void>) },
}));

vi.mock('../lib/api', () => ({
  api: { get: h.apiGet, post: h.apiPost },
  setToken: vi.fn(),
  setRefreshToken: vi.fn(),
  storeMfaTokens: vi.fn(),
  createLoginMfaTransport: vi.fn(() => ({})),
}));
vi.mock('../lib/auth-context', () => ({
  useAuth: () => ({ refresh: h.refresh, logout: h.logout, user: h.auth.user, loading: h.auth.loading }),
}));
vi.mock('@noctusai/lib/components', () => ({
  MfaChallengeDialog: (p: { onVerified: (r: unknown) => Promise<void> }) => {
    h.mfaCapture.onVerified = p.onVerified;
    return <div role="dialog" aria-label="Verificação em duas etapas" />;
  },
}));
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => h.navigate,
}));

const AGENTES = { slug: 'agents', nome: 'Agentes', icone: 'bot', landing_url: 'https://agents.noctusai.com' };
const TOKEN = { sso_token: 't', product_slug: 'agents', redirect_url: 'https://agents.noctusai.com/sso#token=t' };
const replace = vi.fn();

function renderAt(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}><Login /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const fillAndSubmit = (email = 'a@b.com') => {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'password1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
};

const tokenCalls = () => h.apiPost.mock.calls.filter((c) => c[0] === '/api/sso/token');

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  h.auth.user = null;
  h.auth.loading = false;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, replace, href: 'http://localhost/login' },
  });
  h.apiGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/sso/produto/')) {
      if (path.endsWith('/agents')) return AGENTES;
      throw Object.assign(new Error('[404] Produto não encontrado'), { status: 404 });
    }
    return { data: [{ id: 'google', name: 'Google', auth_url: 'http://localhost/oauth' }] };
  });
  h.apiPost.mockImplementation(async (path: string) => {
    if (path === '/api/sso/token') return TOKEN;
    return { access_token: 'x', mfa_required: false };
  });
  h.logout.mockResolvedValue(undefined);
  h.refresh.mockResolvedValue(undefined);
});
afterEach(() => cleanup());

describe('product identity', () => {
  it('titles the form "Entrar no <nome>" from the public endpoint', async () => {
    renderAt('/login?produto=agents');
    expect(await screen.findByRole('heading', { name: 'Entrar no Agentes' })).toBeInTheDocument();
    expect(h.apiGet).toHaveBeenCalledWith('/api/sso/produto/agents');
  });

  it('shows a status (not a blank page) while the identity loads', async () => {
    h.apiGet.mockImplementation(() => new Promise(() => {}));
    renderAt('/login?produto=agents');
    expect(await screen.findByRole('status')).toHaveTextContent('Verificando seu acesso');
  });

  it('unknown or inactive slug: visible error ON CORE, no redirect, no token', async () => {
    renderAt('/login?produto=ghost&next=/x');
    expect(await screen.findByRole('alert')).toHaveTextContent('Não encontramos este produto');
    expect(replace).not.toHaveBeenCalled();
    expect(tokenCalls()).toHaveLength(0);
    expect(screen.queryByLabelText('Senha')).not.toBeInTheDocument();
  });

  it('a 409 (cross-site / no URL) shows the server message on core, no redirect', async () => {
    h.apiGet.mockRejectedValue(Object.assign(new Error('O endereço de acesso do produto não pertence ao mesmo site'), { status: 409 }));
    renderAt('/login?produto=agents');
    expect(await screen.findByRole('alert')).toHaveTextContent('mesmo site');
    expect(replace).not.toHaveBeenCalled();
  });

  it('a malformed slug is not treated as a product (plain login, no lookup)', () => {
    renderAt('/login?produto=https://evil.example');
    expect(h.apiGet).not.toHaveBeenCalledWith(expect.stringContaining('/api/sso/produto'));
    expect(screen.getByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
  });
});

describe('already signed in at core', () => {
  beforeEach(() => { h.auth.user = { email: 'a@b.com' }; });

  it('one POST /api/sso/token, then replace(redirect_url + next)', async () => {
    renderAt('/login?produto=agents&next=/leads%3Fa%3D1');
    await waitFor(() => expect(replace).toHaveBeenCalledTimes(1));
    expect(tokenCalls()).toEqual([['/api/sso/token', { product_slug: 'agents' }]]);
    expect(replace).toHaveBeenCalledWith(`${TOKEN.redirect_url}&next=${encodeURIComponent('/leads?a=1')}`);
  });

  it('no next: the redirect_url verbatim', async () => {
    renderAt('/login?produto=agents');
    await waitFor(() => expect(replace).toHaveBeenCalledWith(TOKEN.redirect_url));
  });

  it.each(['//evil.example/x', 'https://evil.example', '/a\\b', 'javascript:alert(1)'])(
    'non-path next %s is dropped',
    async (bad) => {
      renderAt(`/login?produto=agents&next=${encodeURIComponent(bad)}`);
      await waitFor(() => expect(replace).toHaveBeenCalledWith(TOKEN.redirect_url));
    },
  );

  it('prompt=none with a session still launches', async () => {
    renderAt('/login?produto=agents&prompt=none');
    await waitFor(() => expect(replace).toHaveBeenCalledWith(TOKEN.redirect_url));
  });

  it('waits for the session check: no bounce while auth is loading', async () => {
    h.auth.user = null;
    h.auth.loading = true;
    renderAt('/login?produto=agents&prompt=none');
    await screen.findByText('Verificando seu acesso…');
    expect(replace).not.toHaveBeenCalled();
  });

  it('a refused launch (403) is shown on core, with the form still usable; no redirect', async () => {
    h.apiPost.mockRejectedValue(Object.assign(new Error('Organização não tem acesso a este produto'), { status: 403 }));
    renderAt('/login?produto=agents');
    expect(await screen.findByRole('alert')).toHaveTextContent('não tem acesso');
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Senha')).toBeInTheDocument();
    expect(tokenCalls()).toHaveLength(1);
  });
});

describe('prompt=none without a core session', () => {
  it('bounces to landing_url#sso=login_required, no form, no token', async () => {
    renderAt('/login?produto=agents&prompt=none&next=/x');
    await waitFor(() => expect(replace).toHaveBeenCalledWith('https://agents.noctusai.com#sso=login_required'));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(tokenCalls()).toHaveLength(0);
  });

  it('never bounces for an unknown product', async () => {
    renderAt('/login?produto=ghost&prompt=none');
    await screen.findByRole('alert');
    expect(replace).not.toHaveBeenCalled();
  });
});

describe('after signing in (prompt=login)', () => {
  it('password login continues to the product, not "/"', async () => {
    renderAt('/login?produto=agents&next=/leads');
    await screen.findByRole('heading', { name: 'Entrar no Agentes' });
    fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`${TOKEN.redirect_url}&next=%2Fleads`));
    expect(h.navigate).not.toHaveBeenCalled();
    expect(tokenCalls()).toHaveLength(1);
  });

  it('a session appearing from the form does not double-launch', async () => {
    renderAt('/login?produto=agents');
    await screen.findByRole('heading', { name: 'Entrar no Agentes' });
    h.refresh.mockImplementation(async () => { h.auth.user = { email: 'a@b.com' }; });
    fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalled());
    expect(tokenCalls()).toHaveLength(1);
  });

  it('the MFA challenge path keeps the product', async () => {
    h.apiPost.mockImplementation(async (path: string) =>
      path === '/api/sso/token' ? TOKEN : { access_token: 'pending', mfa_required: true });
    renderAt('/login?produto=agents&next=/leads');
    await screen.findByRole('heading', { name: 'Entrar no Agentes' });
    fillAndSubmit();
    await screen.findByRole('dialog', { name: 'Verificação em duas etapas' });
    expect(replace).not.toHaveBeenCalled();
    await h.mfaCapture.onVerified!({});
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`${TOKEN.redirect_url}&next=%2Fleads`));
    expect(h.navigate).not.toHaveBeenCalled();
  });

  it('P2.5 holds: a different user ends the live session before the new login', async () => {
    // A live session whose launch was refused leaves the form visible.
    h.auth.user = { email: 'old@x.com' };
    h.apiPost.mockRejectedValueOnce(new Error('Organização não tem acesso a este produto'));
    renderAt('/login?produto=agents');
    await screen.findByRole('alert');
    h.apiPost.mockImplementation(async (path: string) => (path === '/api/sso/token' ? TOKEN : { access_token: 'x' }));
    fillAndSubmit('new@x.com');
    await waitFor(() => expect(replace).toHaveBeenCalled());
    expect(h.logout).toHaveBeenCalledWith({ strict: true });
  });

  it('password login refusal stays on core with the message', async () => {
    h.apiPost.mockRejectedValue(new Error('Credenciais inválidas'));
    renderAt('/login?produto=agents');
    await screen.findByRole('heading', { name: 'Entrar no Agentes' });
    fillAndSubmit();
    expect(await screen.findByText('Credenciais inválidas')).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it('links to forgot-password carrying produto and next (never prompt)', async () => {
    renderAt('/login?produto=agents&next=/leads&prompt=login');
    const link = await screen.findByRole('link', { name: 'Esqueci minha senha' });
    expect(link).toHaveAttribute('href', '/esqueci-senha?produto=agents&next=%2Fleads');
  });
});

describe('OAuth round trip', () => {
  it('stashes produto/next before leaving for the provider', async () => {
    renderAt('/login?produto=agents&next=/leads');
    fireEvent.click(await screen.findByRole('button', { name: /Google/ }));
    const stash = JSON.parse(sessionStorage.getItem('noctus:sso-entry')!);
    expect(stash).toMatchObject({ produto: 'agents', next: '/leads' });
    expect(window.location.href).toBe('http://localhost/oauth');
  });

  it('on return (bare /login, session now present) the stash launches the product once and is consumed', async () => {
    sessionStorage.setItem('noctus:sso-entry', JSON.stringify({ produto: 'agents', next: '/leads', prompt: 'login', at: Date.now() }));
    h.auth.user = { email: 'a@b.com' };
    renderAt('/login');
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`${TOKEN.redirect_url}&next=%2Fleads`));
    expect(tokenCalls()).toHaveLength(1);
    expect(sessionStorage.getItem('noctus:sso-entry')).toBeNull();
  });

  it('an expired stash is ignored: plain login', () => {
    sessionStorage.setItem('noctus:sso-entry', JSON.stringify({ produto: 'agents', next: null, prompt: 'login', at: Date.now() - 11 * 60 * 1000 }));
    h.auth.user = { email: 'a@b.com' };
    renderAt('/login');
    expect(screen.getByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
    expect(tokenCalls()).toHaveLength(0);
    expect(sessionStorage.getItem('noctus:sso-entry')).toBeNull();
  });

  it('a stash for an unknown product is cleared and never redirects', async () => {
    sessionStorage.setItem('noctus:sso-entry', JSON.stringify({ produto: 'ghost', next: null, prompt: 'login', at: Date.now() }));
    renderAt('/login');
    await screen.findByRole('alert');
    expect(sessionStorage.getItem('noctus:sso-entry')).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
