import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';

interface Product {
  id: string;
  nome: string;
  slug: string;
  descricao: string;
  icone: string;
  url_base: string;
  cor: string;
  has_access: boolean;
}

interface Subscription {
  id: string;
  status: string;
  started_at?: string;
  expires_at?: string | null;
  plans?: { name: string; slug: string };
}

export function Dashboard() {
  const { user, organization, isAdmin, loading: authLoading, logout } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate('/login'); return; }

    async function fetchData() {
      try {
        const [meRes, subRes] = await Promise.all([
          api.get('/api/auth/me'),
          api.get('/api/subscriptions/me').catch(() => ({ data: null })),
        ]);
        setProducts(meRes.products || []);
        setSubscription(subRes.data);
      } catch {
        logout();
        navigate('/login');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [authLoading, user]);

  async function launchProduct(product: Product) {
    if (!product.has_access) return;
    setLaunching(product.slug);

    try {
      const res = await api.post('/api/sso/token', { product_slug: product.slug });
      window.open(`${product.url_base}/sso?token=${res.sso_token}`, '_blank');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLaunching(null);
    }
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  const isTestOrg = organization?.category === 'test';
  const isFreeOrg = !subscription || subscription.plans?.slug === 'free';
  const isTrial = subscription?.status === 'trial';

  function getTrialDaysRemaining(): number | null {
    if (!isTrial || !subscription?.expires_at) return null;
    const now = new Date();
    const expiry = new Date(subscription.expires_at);
    const diff = expiry.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  const trialDays = getTrialDaysRemaining();

  if (authLoading || loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando NoctusAI...</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <span className="logo-icon">⚡</span>
          <h1>NoctusAI</h1>
        </div>
        <div className="header-right">
          {isAdmin && (
            <button className="btn-admin" onClick={() => navigate('/admin')}>
              Admin Panel
            </button>
          )}
          <div className="user-info">
            <span className="user-name">{user?.nome}</span>
            <span className="org-name">
              {organization?.nome}
              {isTestOrg && (
                <span className="badge badge-sm badge-inline test-badge">Conta Teste</span>
              )}
              {subscription && !isTestOrg && (
                <span className={`badge badge-sm badge-inline ${subscription.status === 'active' ? 'badge-active' : ''}`}>
                  {subscription.plans?.name || subscription.status}
                </span>
              )}
            </span>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Sair</button>
        </div>
      </header>

      {/* Main content */}
      <main className="dashboard-main">
        {/* Trial countdown */}
        {isTrial && trialDays !== null && (
          <div className="trial-info">
            <span className="trial-info-icon">⏳</span>
            <span>
              {trialDays > 0
                ? `Seu período de teste expira em ${trialDays} dia${trialDays !== 1 ? 's' : ''}.`
                : 'Seu período de teste expirou.'}
            </span>
            <button className="trial-info-btn" onClick={() => navigate('/pricing')}>
              Assinar agora
            </button>
          </div>
        )}

        {/* Upgrade banner for free orgs (not test) */}
        {isFreeOrg && !isTestOrg && !isTrial && (
          <div className="upgrade-banner">
            <div className="upgrade-banner-content">
              <div className="upgrade-banner-text">
                <strong>Desbloqueie todo o potencial do NoctusAI</strong>
                <p>Atualize seu plano para acessar recursos avançados, mais usuários e suporte prioritário.</p>
              </div>
              <button className="upgrade-banner-btn" onClick={() => navigate('/pricing')}>
                Ver planos
              </button>
            </div>
          </div>
        )}

        <section className="welcome">
          <h2>Bem-vindo, {user?.nome?.split(' ')[0]}!</h2>
          <p>Seus produtos NoctusAI</p>
        </section>

        <section className="products-grid">
          {[...products].sort((a, b) => Number(b.has_access) - Number(a.has_access)).map(product => (
            <div
              key={product.id}
              className={`product-card ${product.has_access ? 'unlocked' : 'locked'}`}
              onClick={() => launchProduct(product)}
              style={{ '--product-color': product.cor } as React.CSSProperties}
            >
              <div className="product-icon">{product.icone}</div>
              <h3>{product.nome}</h3>
              <p>{product.descricao}</p>

              {product.has_access ? (
                <div className="product-status unlocked">
                  <span className="status-dot">●</span>
                  {launching === product.slug ? 'Abrindo...' : 'Acessar'}
                  <span className="arrow">→</span>
                </div>
              ) : (
                <div className="product-status locked">
                  <span className="lock-icon">🔒</span>
                  Solicitar acesso
                </div>
              )}
            </div>
          ))}

          {/* Coming soon placeholder cards */}
          {[
            { nome: 'ERP Construtoras', icone: '🏗️', desc: 'Gestão de obras e empreendimentos' },
            { nome: 'CRM Vendas', icone: '📊', desc: 'Funil de vendas inteligente com IA' },
            { nome: 'BI Analytics', icone: '📈', desc: 'Dashboards e relatórios avançados' },
          ].map((p, i) => (
            <div key={`soon-${i}`} className="product-card coming-soon">
              <div className="product-icon">{p.icone}</div>
              <h3>{p.nome}</h3>
              <p>{p.desc}</p>
              <div className="product-status locked">
                <span className="soon-badge">Em breve</span>
              </div>
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}
