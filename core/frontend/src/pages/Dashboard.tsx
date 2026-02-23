import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, clearToken } from '../lib/api';

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

interface UserProfile {
  user: { id: string; nome: string; email: string; role: string };
  organization: { id: string; nome: string; plano: string } | null;
  products: Product[];
}

export function Dashboard() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/api/auth/me')
      .then(data => setProfile(data))
      .catch(() => { clearToken(); navigate('/login'); })
      .finally(() => setLoading(false));
  }, []);

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
    clearToken();
    navigate('/login');
  }

  if (loading) {
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
          <div className="user-info">
            <span className="user-name">{profile?.user.nome}</span>
            <span className="org-name">{profile?.organization?.nome}</span>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Sair</button>
        </div>
      </header>

      {/* Main content */}
      <main className="dashboard-main">
        <section className="welcome">
          <h2>Bem-vindo, {profile?.user.nome?.split(' ')[0]}! 👋</h2>
          <p>Seus produtos NoctusAI</p>
        </section>

        <section className="products-grid">
          {profile?.products.map(product => (
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
