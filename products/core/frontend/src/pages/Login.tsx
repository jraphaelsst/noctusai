import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { MfaChallengeDialog } from '@noctusai/lib/components';
import { api, createLoginMfaTransport, setToken, storeMfaTokens } from '../lib/api';
import type { MfaVerifyResult } from '@noctusai/lib';
import { useAuth } from '../lib/auth-context';
import { useSsoProduto } from '../hooks/useSsoProduto';
import {
  clearStashedSsoEntry,
  entryQuery,
  launchProduct,
  loginRequiredUrl,
  peekStashedSsoEntry,
  readSsoEntry,
  stashSsoEntry,
  type SsoEntry,
  type SsoProduto,
} from '../lib/sso-entry';


interface OAuthProvider {
  id: string;
  name: string;
  auth_url: string;
}

/**
 * Central login (contract: products/core/docs/sso-entry-contract.md). Without `produto` this is the
 * plain core login. With `produto` (or one stashed across an OAuth round trip) it is the entry
 * gate of that product: instant launch when core already has a session, a `prompt=none` bounce
 * when it does not, otherwise the form titled with the product's identity.
 */
export function Login() {
  const [params] = useSearchParams();
  const [entry] = useState<SsoEntry | null>(() => readSsoEntry(params) ?? peekStashedSsoEntry());
  return entry ? <EntryGate entry={entry} /> : <CoreCredentialsForm entry={null} />;
}

function StatusCard({ children, tone = 'status' }: { children: React.ReactNode; tone?: 'status' | 'alert' }) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div
        role={tone === 'alert' ? 'alert' : 'status'}
        className="w-full max-w-md bg-card rounded-lg border border-border shadow-md p-8 text-center text-sm text-foreground space-y-4"
      >
        {children}
      </div>
    </div>
  );
}

function EntryGate({ entry }: { entry: SsoEntry }) {
  const { user, loading } = useAuth();
  const { produto, error: produtoError, showSkeleton } = useSsoProduto(entry.produto);
  const launched = useRef(false);
  const [launchError, setLaunchError] = useState('');

  // One POST /api/sso/token per visit, whoever asks first (mount with a live session, or the form
  // right after a sign-in). `force` is the explicit retry / sign-in-as-someone-else path.
  const startLaunch = useCallback(async (force = false) => {
    if (launched.current && !force) return;
    launched.current = true;
    setLaunchError('');
    try {
      await launchProduct(entry);
    } catch (err: any) {
      setLaunchError(err?.message || 'Não foi possível abrir o produto. Tente novamente.');
    }
  }, [entry]);

  useEffect(() => {
    if (produtoError) clearStashedSsoEntry();
  }, [produtoError]);

  useEffect(() => {
    if (!produto || loading) return;
    if (user) {
      void startLaunch();
    } else if (entry.prompt === 'none' && !launched.current) {
      launched.current = true;
      clearStashedSsoEntry();
      window.location.replace(loginRequiredUrl(produto.landing_url));
    }
  }, [produto, user, loading, entry.prompt, startLaunch]);

  if (produtoError) {
    const status = (produtoError as any)?.status;
    const notFound = status === 404 || /^\[404\]/.test(produtoError.message ?? '');
    return (
      <StatusCard tone="alert">
        <p className="font-semibold">Não foi possível abrir este produto</p>
        <p className="text-muted-foreground">
          {notFound
            ? 'Não encontramos este produto ou ele está desativado. Confira o endereço ou volte ao NoctusAI.'
            : produtoError.message || 'Tente novamente em instantes.'}
        </p>
        <Link to="/" className="inline-block text-primary underline">Ir para o NoctusAI</Link>
      </StatusCard>
    );
  }
  if (showSkeleton || loading || !produto) {
    return <StatusCard>Verificando seu acesso…</StatusCard>;
  }
  if (user && !launchError) {
    return <StatusCard>Abrindo {produto.nome}…</StatusCard>;
  }
  if (!user && entry.prompt === 'none') {
    return <StatusCard>Voltando para {produto.nome}…</StatusCard>;
  }
  return (
    <CoreCredentialsForm
      key={launchError}
      entry={entry}
      produto={produto}
      initialError={launchError}
      onSignedIn={() => startLaunch(!!launchError)}
    />
  );
}

interface CoreCredentialsFormProps {
  entry: SsoEntry | null;
  produto?: SsoProduto;
  initialError?: string;
  /** With a product: continue into it instead of core's home. */
  onSignedIn?: () => Promise<void>;
}

function CoreCredentialsForm({ entry, produto, initialError = '', onSignedIn }: CoreCredentialsFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(initialError);
  const [loading, setLoading] = useState(false);
  // `?mode=signup` (the website's "Criar conta" CTAs) opens straight in signup mode.
  const [searchParams] = useSearchParams();
  const [isSignup, setIsSignup] = useState(() => searchParams.get('mode') === 'signup');
  const [nome, setNome] = useState('');
  const [empresa, setEmpresa] = useState('');
  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([]);
  const [oauthLoading, setOauthLoading] = useState(false);
  // Login challenge (platform-admin-mfa M5): set when the password step answered
  // `mfa_required` — holds the pending aal1 token, which is NOT stored yet.
  const [mfaPending, setMfaPending] = useState<string | null>(null);
  const navigate = useNavigate();
  const { refresh, logout, user: liveUser } = useAuth();
  const mfaTransport = useMemo(
    () => (mfaPending ? createLoginMfaTransport(mfaPending) : null),
    [mfaPending],
  );

  useEffect(() => {
    // Fetch available OAuth providers
    api.get('/api/auth/oauth/providers')
      .then(res => setOauthProviders(res.data || []))
      .catch(() => {});
  }, []);

  // P2.5 (sso-identity-hardening): a live core session must not survive a sign-in
  // as someone else -- its product (SSO) sessions would keep acting as the old user.
  // Runs the SAME global logout the header uses, in strict mode: if revocation fails
  // we surface the error and stop (neither signing out locally nor proceeding).
  async function endLiveSession() {
    try {
      await logout({ strict: true });
    } catch {
      throw new Error('Não foi possível encerrar a sessão anterior. Verifique a conexão e tente novamente.');
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // Same user re-signing in: nothing to revoke. Anything else (incl. signup): end it first.
      if (liveUser && liveUser.email.trim().toLowerCase() !== email.trim().toLowerCase()) {
        await endLiveSession();
      }
      if (isSignup) {
        await api.post('/api/auth/signup', { nome, email, password, empresa });
        // After signup, auto-login
      }
      const res = await api.post('/api/auth/login', { email, password });
      if (res.mfa_required) {
        // Second factor first: the session is aal1 until /api/auth/mfa/verify succeeds.
        setMfaPending(res.access_token);
        return;
      }
      setToken(res.access_token);
      if (res.refresh_token) {
        const { setRefreshToken } = await import('../lib/api');
        setRefreshToken(res.refresh_token);
      }
      await refresh();
      if (onSignedIn) await onSignedIn(); else navigate('/');
    } catch (err: any) {
      // Signup can be closed from Website → Configurações (backend answers
      // 403 `signup_closed`); point the visitor at the waitlist instead of
      // echoing the machine code.
      if (isSignup && err?.status === 403 && String(err?.message ?? '').includes('signup_closed')) {
        setError('Os cadastros estão temporariamente fechados. Entre na lista de espera em noctusai.com/lista-de-espera.');
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleMfaVerified(result: MfaVerifyResult) {
    storeMfaTokens(result);
    setMfaPending(null);
    await refresh();
    if (onSignedIn) await onSignedIn(); else navigate('/');
  }

  async function handleOAuth(provider: OAuthProvider) {
    setError('');
    setOauthLoading(true);
    // The identity is unknown until after the redirect, so a live session is ended
    // BEFORE leaving this page (the callback lands on a fresh origin state).
    if (liveUser) {
      try {
        await endLiveSession();
      } catch (err: any) {
        setError(err.message);
        setOauthLoading(false);
        return;
      }
    }
    // The provider returns to a bare /login: keep the product + path across the round trip.
    if (entry) stashSsoEntry(entry);
    window.location.href = provider.auth_url;
  }

  function getOAuthIcon(providerId: string): string {
    switch (providerId) {
      case 'google': return 'G';
      case 'azure': return 'M';
      default: return providerId[0].toUpperCase();
    }
  }

  function getOAuthLabel(providerId: string): string {
    switch (providerId) {
      case 'google': return 'Google';
      case 'azure': return 'Microsoft';
      default: return providerId;
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-md p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <span className="text-2xl">⚡</span>
            <h1 className="text-2xl font-bold text-foreground">NoctusAI</h1>
          </div>
          <p className="text-sm text-muted-foreground">Plataforma de Produtos Digitais AI-First</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <h2 className="text-lg font-semibold text-foreground">
            {produto && !isSignup ? `Entrar no ${produto.nome}` : isSignup ? 'Criar conta' : 'Entrar'}
          </h2>
          {produto && (
            <p className="text-sm text-muted-foreground">
              Use sua conta NoctusAI: o login é único para todos os produtos.
            </p>
          )}

          {isSignup && (
            <>
              <div className="space-y-1.5">
                <label htmlFor="login-nome" className="text-sm font-medium text-foreground">Seu nome</label>
                <input
                  id="login-nome"
                  type="text"
                  value={nome}
                  onChange={e => setNome(e.target.value)}
                  placeholder="João Silva"
                  required
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="login-empresa" className="text-sm font-medium text-foreground">Nome da empresa</label>
                <input
                  id="login-empresa"
                  type="text"
                  value={empresa}
                  onChange={e => setEmpresa(e.target.value)}
                  placeholder="Imobiliária Silva"
                  required
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
              </div>
            </>
          )}

          <div className="space-y-1.5">
            <label htmlFor="login-email" className="text-sm font-medium text-foreground">Email</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="voce@empresa.com"
              required
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="login-senha" className="text-sm font-medium text-foreground">Senha</label>
            <input
              id="login-senha"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
          </div>

          {error && (
            <div role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger-foreground">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Carregando...' : isSignup ? 'Criar conta' : 'Entrar'}
          </button>

          {!isSignup && (
            <Link
              to={`/esqueci-senha${entryQuery(entry)}`}
              className="block w-full text-center text-sm text-primary hover:text-primary/80 transition-colors"
            >
              Esqueci minha senha
            </Link>
          )}

          <button
            type="button"
            className="w-full text-sm text-primary hover:text-primary/80 transition-colors"
            onClick={() => { setIsSignup(!isSignup); setError(''); }}
          >
            {isSignup ? 'Já tem conta? Entrar' : 'Não tem conta? Criar agora'}
          </button>
        </form>

        {/* OAuth Section */}
        {oauthProviders.length > 0 && (
          <div className="mt-6">
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">ou continuar com</span>
              </div>
            </div>
            <div className="grid gap-2">
              {oauthProviders.map(provider => (
                <button
                  key={provider.id}
                  type="button"
                  className="w-full h-10 rounded-md border border-input bg-background text-sm font-medium text-foreground hover:bg-accent transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => handleOAuth(provider)}
                  disabled={oauthLoading}
                >
                  <span className="font-bold">{getOAuthIcon(provider.id)}</span>
                  {getOAuthLabel(provider.id)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {mfaTransport && (
        <MfaChallengeDialog
          open
          enrolled
          api={mfaTransport}
          onVerified={handleMfaVerified}
          onCancel={() => { setMfaPending(null); setPassword(''); }}
        />
      )}
    </div>
  );
}
