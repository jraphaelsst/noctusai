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
      // Sign up via the auth endpoint
      const res = await api.post('/api/auth/signup', { nome, email, password });
      if (res.token) {
        setToken(res.token);
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
      if (res.token) {
        setToken(res.token);
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
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando convite...</p>
      </div>
    );
  }

  // Accepting state
  if (status === 'accepting') {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Aceitando convite...</p>
      </div>
    );
  }

  // Accepted state
  if (status === 'accepted') {
    return (
      <div className="invite-page">
        <div className="invite-card">
          <div className="invite-card-icon invite-card-icon-success">&#10003;</div>
          <h2>Convite aceito!</h2>
          <p className="invite-card-text">
            Você agora faz parte da organização como <strong>{role || 'membro'}</strong>.
          </p>
          <button
            className="btn-primary"
            onClick={() => navigate('/')}
            style={{ marginTop: '24px' }}
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
      <div className="invite-page">
        <div className="invite-card">
          <div className="invite-card-icon invite-card-icon-error">!</div>
          <h2>Erro no convite</h2>
          <p className="invite-card-text">{error}</p>
          <button
            className="btn-primary"
            onClick={() => navigate('/')}
            style={{ marginTop: '24px' }}
          >
            Ir para o Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Needs login / signup
  return (
    <div className="invite-page">
      <div className="invite-card">
        <div className="login-header" style={{ marginBottom: '24px' }}>
          <div className="logo">
            <span className="logo-icon">⚡</span>
            <h1>NoctusAI</h1>
          </div>
          <p className="subtitle">Você recebeu um convite para uma organização</p>
        </div>

        {error && <div className="error">{error}</div>}

        {signupMode ? (
          <form onSubmit={handleSignupAndAccept}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
              Criar conta e aceitar convite
            </h2>
            <div className="field">
              <label>Nome</label>
              <input
                type="text"
                placeholder="Seu nome completo"
                value={nome}
                onChange={e => setNome(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>E-mail</label>
              <input
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Senha</label>
              <input
                type="password"
                placeholder="Mínimo 6 caracteres"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>
            <button type="submit" className="btn-primary" disabled={submitting}>
              Criar conta e aceitar
            </button>
            <button
              type="button"
              className="btn-link"
              onClick={() => setSignupMode(false)}
            >
              Já tenho uma conta
            </button>
          </form>
        ) : (
          <form onSubmit={handleLoginAndAccept}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
              Entrar e aceitar convite
            </h2>
            <div className="field">
              <label>E-mail</label>
              <input
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Senha</label>
              <input
                type="password"
                placeholder="Sua senha"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn-primary" disabled={submitting}>
              Entrar e aceitar
            </button>
            <button
              type="button"
              className="btn-link"
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
