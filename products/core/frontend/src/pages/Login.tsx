import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, setToken } from '../lib/api';
import { useAuth } from '../lib/auth-context';


interface OAuthProvider {
  id: string;
  name: string;
  auth_url: string;
}

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isSignup, setIsSignup] = useState(false);
  const [nome, setNome] = useState('');
  const [empresa, setEmpresa] = useState('');
  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([]);
  const [oauthLoading, setOauthLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  useEffect(() => {
    // Fetch available OAuth providers
    api.get('/api/auth/oauth/providers')
      .then(res => setOauthProviders(res.data || []))
      .catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isSignup) {
        await api.post('/api/auth/signup', { nome, email, password, empresa });
        // After signup, auto-login
      }
      const res = await api.post('/api/auth/login', { email, password });
      setToken(res.access_token);
      if (res.refresh_token) {
        const { setRefreshToken } = await import('../lib/api');
        setRefreshToken(res.refresh_token);
      }
      await refresh();
      navigate('/');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleOAuth(provider: OAuthProvider) {
    setOauthLoading(true);
    // Redirect to Supabase OAuth URL
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
            {isSignup ? 'Criar conta' : 'Entrar'}
          </h2>

          {isSignup && (
            <>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Seu nome</label>
                <input
                  type="text"
                  value={nome}
                  onChange={e => setNome(e.target.value)}
                  placeholder="João Silva"
                  required
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">Nome da empresa</label>
                <input
                  type="text"
                  value={empresa}
                  onChange={e => setEmpresa(e.target.value)}
                  placeholder="Imobiliária Silva"
                  required
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
              </div>
            </>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="voce@empresa.com"
              required
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">Senha</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
          </div>

          {error && (
            <div className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger-foreground">
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
    </div>
  );
}
