import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api, isAuthenticated, setToken } from '../lib/api';
import { useAuth } from '../lib/auth-context';

type InviteStatus = 'loading' | 'ready' | 'accepting' | 'accepted' | 'error' | 'needs-login';

export function AcceptInvite() {
  const { token: inviteToken } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();

  const [status, setStatus] = useState<InviteStatus>('loading');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [orgId, setOrgId] = useState('');
  const [role, setRole] = useState('');

  // Signup fields (for unauthenticated users)
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [signupMode, setSignupMode] = useState(false);

  useEffect(() => {
    if (!inviteToken) {
      setError('Token de convite inválido');
      setStatus('error');
      return;
    }

    if (isAuthenticated() && user) {
      // Auto-accept for authenticated users
      acceptInvite();
    } else if (isAuthenticated()) {
      // Token present but user context not yet loaded — wait
      setStatus('loading');
    } else {
      setStatus('needs-login');
    }
  }, [inviteToken, user]);

  async function acceptInvite(nome?: string) {
    if (!inviteToken) return;

    setSubmitting(true);
    setStatus('accepting');
    setError('');

    try {
      const body: Record<string, string> = { token: inviteToken };
      if (nome) body.nome = nome;

      const res = await api.post('/api/team/accept-invite', body);
      setOrgId(res.data?.org_id || '');
      setRole(res.data?.role || '');
      setStatus('accepted');

      // Refresh auth context to pick up new org
      await refresh();
    } catch (err: any) {
      setError(err.message || 'Erro ao aceitar convite');
      setStatus('error');
    }
  }

  async function handleSignupAndAccept(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    setStatus('accepting');

    try {
      // Sign up via the auth endpoint (returns { data: { user_id, org_id } } — no token)
      await api.post('/api/auth/signup', { nome, email, password, empresa: nome });

      // Login to get the access token
      const loginRes = await api.post('/api/auth/login', { email, password });
      if (loginRes.access_token) {
        setToken(loginRes.access_token);
      }

      // Now accept the invite
      await acceptInvite(nome);
    } catch (err: any) {
      setError(err.message || 'Erro ao criar conta');
      setSubmitting(false);
      setStatus('needs-login');
    }
  }

  async function handleLoginAndAccept(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    setStatus('accepting');

    try {
      const res = await api.post('/api/auth/login', { email, password });
      if (res.access_token) {
        setToken(res.access_token);
      }

      // Now accept the invite
      await acceptInvite();
    } catch (err: any) {
      setError(err.message || 'Erro ao fazer login');
      setSubmitting(false);
      setStatus('needs-login');
    }
  }

  // Loading state
  if (status === 'loading') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Carregando convite...</p>
      </div>
    );
  }

  // Accepting state
  if (status === 'accepting') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Aceitando convite...</p>
      </div>
    );
  }

  // Accepted state
  if (status === 'accepted') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 text-center shadow-sm">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-2xl font-bold text-green-600">
            &#10003;
          </div>
          <h2 className="mb-3 text-2xl font-bold text-foreground">Convite aceito!</h2>
          <p className="mb-6 text-muted-foreground">
            Você agora faz parte da organização como <strong className="text-foreground">{role || 'membro'}</strong>.
          </p>
          <button
            className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => navigate('/')}
          >
            Ir para o Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 text-center shadow-sm">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-2xl font-bold text-red-600">
            !
          </div>
          <h2 className="mb-3 text-2xl font-bold text-foreground">Erro no convite</h2>
          <p className="mb-6 text-muted-foreground">{error}</p>
          <button
            className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => navigate('/')}
          >
            Ir para o Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Needs login / signup
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="flex items-center justify-center gap-2">
            <span className="text-2xl">⚡</span>
            <h1 className="text-2xl font-bold text-foreground">NoctusAI</h1>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Você recebeu um convite para uma organização
          </p>
        </div>

        {error && (
          <div className="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
        )}

        {signupMode ? (
          <form onSubmit={handleSignupAndAccept} className="space-y-4">
            <h2 className="text-lg font-semibold text-foreground">
              Criar conta e aceitar convite
            </h2>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Nome</label>
              <input
                type="text"
                placeholder="Seu nome completo"
                value={nome}
                onChange={e => setNome(e.target.value)}
                required
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">E-mail</label>
              <input
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Senha</label>
              <input
                type="password"
                placeholder="Mínimo 6 caracteres"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={submitting}
            >
              Criar conta e aceitar
            </button>
            <button
              type="button"
              className="w-full text-sm text-primary hover:underline"
              onClick={() => setSignupMode(false)}
            >
              Já tenho uma conta
            </button>
          </form>
        ) : (
          <form onSubmit={handleLoginAndAccept} className="space-y-4">
            <h2 className="text-lg font-semibold text-foreground">
              Entrar e aceitar convite
            </h2>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">E-mail</label>
              <input
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Senha</label>
              <input
                type="password"
                placeholder="Sua senha"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={submitting}
            >
              Entrar e aceitar
            </button>
            <button
              type="button"
              className="w-full text-sm text-primary hover:underline"
              onClick={() => setSignupMode(true)}
            >
              Não tenho conta — criar agora
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
