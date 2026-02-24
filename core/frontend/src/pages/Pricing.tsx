import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';

interface Plan {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  price_monthly: number;
  price_yearly: number;
  max_users: number;
  max_products: number;
  features: Record<string, any>;
  is_custom: boolean;
  is_active: boolean;
}

export function Pricing() {
  const { user, organization, loading: authLoading, logout } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [checkingOut, setCheckingOut] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate('/login'); return; }

    async function fetchPlans() {
      try {
        const res = await api.get('/api/plans');
        const activePlans = (res.data || []).filter((p: Plan) => p.is_active && !p.is_custom);
        setPlans(activePlans);
      } catch (err) {
        console.error('Erro ao carregar planos:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchPlans();
  }, [authLoading, user]);

  async function handleCheckout(planId: string) {
    setCheckingOut(planId);
    try {
      const res = await api.post('/api/billing/checkout', {
        plan_id: planId,
        billing_period: billingPeriod,
      });
      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      }
    } catch (err: any) {
      alert(err.message || 'Erro ao iniciar checkout');
    } finally {
      setCheckingOut(null);
    }
  }

  function formatPrice(plan: Plan): string {
    const price = billingPeriod === 'monthly' ? plan.price_monthly : plan.price_yearly;
    if (price === 0) return 'Grátis';
    return `R$ ${price.toFixed(2).replace('.', ',')}`;
  }

  function formatLimit(value: number): string {
    return value === -1 ? 'Ilimitado' : String(value);
  }

  function getFeatureList(plan: Plan): string[] {
    const features: string[] = [];
    features.push(`${formatLimit(plan.max_users)} ${plan.max_users === 1 ? 'usuário' : 'usuários'}`);
    features.push(`${formatLimit(plan.max_products)} ${plan.max_products === 1 ? 'produto' : 'produtos'}`);

    if (plan.features) {
      Object.entries(plan.features).forEach(([key, value]) => {
        if (typeof value === 'boolean' && value) {
          features.push(key.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase()));
        } else if (typeof value === 'string') {
          features.push(value);
        }
      });
    }

    return features;
  }

  function isPopular(plan: Plan): boolean {
    return plan.slug === 'pro';
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  if (authLoading || loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando planos...</p>
      </div>
    );
  }

  const yearlySavings = plans.length > 0 && plans.some(p => p.price_yearly > 0 && p.price_monthly > 0);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <span className="logo-icon">⚡</span>
          <h1>NoctusAI</h1>
        </div>
        <div className="header-right">
          <div className="user-info">
            <span className="user-name">{user?.nome}</span>
            <span className="org-name">{organization?.nome}</span>
          </div>
          <button className="btn-secondary" onClick={() => navigate('/')}>Voltar</button>
          <button className="btn-logout" onClick={handleLogout}>Sair</button>
        </div>
      </header>

      <main className="pricing-page">
        <div className="pricing-header">
          <h2>Escolha seu plano</h2>
          <p>Encontre o plano ideal para sua organização. Todos incluem acesso à plataforma NoctusAI.</p>
        </div>

        {yearlySavings && (
          <div className="pricing-toggle">
            <button
              className={`pricing-toggle-btn ${billingPeriod === 'monthly' ? 'active' : ''}`}
              onClick={() => setBillingPeriod('monthly')}
            >
              Mensal
            </button>
            <button
              className={`pricing-toggle-btn ${billingPeriod === 'yearly' ? 'active' : ''}`}
              onClick={() => setBillingPeriod('yearly')}
            >
              Anual
              <span className="pricing-toggle-save">Economize</span>
            </button>
          </div>
        )}

        <div className="pricing-grid">
          {plans.map(plan => (
            <div key={plan.id} className={`pricing-card ${isPopular(plan) ? 'popular' : ''}`}>
              {isPopular(plan) && <div className="pricing-popular-tag">Mais Popular</div>}
              <div className="pricing-card-header">
                <h3>{plan.name}</h3>
                {plan.description && <p>{plan.description}</p>}
              </div>

              <div className="pricing-price">
                <span className="pricing-price-value">{formatPrice(plan)}</span>
                {(billingPeriod === 'monthly' ? plan.price_monthly : plan.price_yearly) > 0 && (
                  <span className="pricing-price-period">
                    /{billingPeriod === 'monthly' ? 'mês' : 'ano'}
                  </span>
                )}
              </div>

              <ul className="pricing-features">
                {getFeatureList(plan).map((feature, i) => (
                  <li key={i}>
                    <span className="pricing-feature-check">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>

              <button
                className={`pricing-cta ${isPopular(plan) ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => handleCheckout(plan.id)}
                disabled={checkingOut === plan.id}
              >
                {checkingOut === plan.id ? 'Redirecionando...' : plan.price_monthly === 0 ? 'Começar Grátis' : 'Assinar'}
              </button>
            </div>
          ))}

          {plans.length === 0 && (
            <div className="pricing-empty">
              <p>Nenhum plano disponível no momento.</p>
              <button className="btn-secondary" onClick={() => navigate('/')}>Voltar ao Dashboard</button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
