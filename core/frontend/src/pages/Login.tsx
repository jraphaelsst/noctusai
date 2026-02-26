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
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="logo">
            <span className="logo-icon">⚡</span>
            <h1>NoctusAI</h1>
          </div>
          <p className="subtitle">Plataforma de Produtos Digitais AI-First</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <h2>{isSignup ? 'Criar conta' : 'Entrar'}</h2>

          {isSignup && (
            <>
              <div className="field">
                <label>Seu nome</label>
                <input type="text" value={nome} onChange={e => setNome(e.target.value)}
                       placeholder="João Silva" required />
              </div>
              <div className="field">
                <label>Nome da empresa</label>
                <input type="text" value={empresa} onChange={e => setEmpresa(e.target.value)}
                       placeholder="Imobiliária Silva" required />
              </div>
            </>
          )}

          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                   placeholder="voce@empresa.com" required />
          </div>

          <div className="field">
            <label>Senha</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                   placeholder="••••••••" required minLength={6} />
          </div>

          {error && <div className="error">{error}</div>}

          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Carregando...' : isSignup ? 'Criar conta' : 'Entrar'}
          </button>

          <button type="button" className="btn-link" onClick={() => { setIsSignup(!isSignup); setError(''); }}>
            {isSignup ? 'Já tem conta? Entrar' : 'Não tem conta? Criar agora'}
          </button>
        </form>

        {/* OAuth Section */}
        {oauthProviders.length > 0 && (
          <div className="oauth-section">
            <div className="oauth-divider">
              <span>ou continuar com</span>
            </div>
            <div className="oauth-buttons">
              {oauthProviders.map(provider => (
                <button
                  key={provider.id}
                  type="button"
                  className={`btn-oauth btn-${provider.id === 'azure' ? 'microsoft' : provider.id}`}
                  onClick={() => handleOAuth(provider)}
                  disabled={oauthLoading}
                >
                  <span className="oauth-icon">{getOAuthIcon(provider.id)}</span>
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
