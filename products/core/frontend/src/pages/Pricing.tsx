import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';
import { NotificationBell } from '../components/NotificationBell';
import { Header, useTheme } from "@noctusai/lib/design-system";

interface Plan {
  id: string;
  nome: string;
  slug: string;
  descricao: string | null;
  price_monthly: number;
  price_yearly: number;
  max_users: number;
  max_products: number;
  features: Record<string, any>;
  is_custom: boolean;
  ativo: boolean;
}

export function Pricing() {
  const { user, organization, isAdmin, loading: authLoading, logout } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [checkingOut, setCheckingOut] = useState<string | null>(null);
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

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
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Carregando planos...</p>
      </div>
    );
  }

  const yearlySavings = plans.length > 0 && plans.some(p => p.price_yearly > 0 && p.price_monthly > 0);

  return (
    <div className="min-h-screen bg-background">
      <Header
        user={{ name: user?.nome || '', email: user?.email || '', role: isAdmin ? 'Administrador' : 'Membro' }}
        onLogout={handleLogout}
        theme={theme}
        onThemeToggle={toggleTheme}
        actions={
          <div className="flex items-center gap-2">
            <button
              className="h-9 rounded-md border border-border bg-background px-4 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              onClick={() => navigate('/')}
            >
              Voltar
            </button>
            <NotificationBell />
          </div>
        }
      />

      <main className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-6 sm:py-10 lg:py-12">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold text-foreground">Escolha seu plano</h2>
          <p className="mt-2 text-muted-foreground">
            Encontre o plano ideal para sua organização. Todos incluem acesso à plataforma NoctusAI.
          </p>
        </div>

        {yearlySavings && (
          <div className="mb-10 flex items-center justify-center gap-1 rounded-lg bg-muted p-1">
            <button
              className={`rounded-md px-6 py-2 text-sm font-medium transition-colors ${
                billingPeriod === 'monthly'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setBillingPeriod('monthly')}
            >
              Mensal
            </button>
            <button
              className={`flex items-center gap-2 rounded-md px-6 py-2 text-sm font-medium transition-colors ${
                billingPeriod === 'yearly'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setBillingPeriod('yearly')}
            >
              Anual
              <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                Economize
              </span>
            </button>
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {plans.map(plan => (
            <div
              key={plan.id}
              className={`relative flex flex-col rounded-lg border shadow-sm p-6 ${
                isPopular(plan)
                  ? 'border-primary bg-card ring-2 ring-primary'
                  : 'border-border bg-card'
              }`}
            >
              {isPopular(plan) && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-4 py-1 text-xs font-semibold text-primary-foreground">
                  Mais Popular
                </div>
              )}
              <div className="mb-4">
                <h3 className="text-lg font-semibold text-foreground">{plan.nome}</h3>
                {plan.descricao && (
                  <p className="mt-1 text-sm text-muted-foreground">{plan.descricao}</p>
                )}
              </div>

              <div className="mb-6">
                <span className="text-3xl font-bold text-foreground">{formatPrice(plan)}</span>
                {(billingPeriod === 'monthly' ? plan.price_monthly : plan.price_yearly) > 0 && (
                  <span className="ml-1 text-sm text-muted-foreground">
                    /{billingPeriod === 'monthly' ? 'mês' : 'ano'}
                  </span>
                )}
              </div>

              <ul className="mb-6 flex-1 space-y-3">
                {getFeatureList(plan).map((feature, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-foreground">
                    <span className="font-bold text-primary">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>

              <button
                className={`w-full rounded-md px-4 py-2.5 text-sm font-medium transition-colors ${
                  isPopular(plan)
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'border border-border bg-background text-foreground hover:bg-muted'
                } disabled:cursor-not-allowed disabled:opacity-50`}
                onClick={() => handleCheckout(plan.id)}
                disabled={checkingOut === plan.id}
              >
                {checkingOut === plan.id ? 'Redirecionando...' : plan.price_monthly === 0 ? 'Começar Grátis' : 'Assinar'}
              </button>
            </div>
          ))}

          {plans.length === 0 && (
            <div className="col-span-full py-12 text-center">
              <p className="text-muted-foreground">Nenhum plano disponível no momento.</p>
              <button
                className="mt-4 rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
                onClick={() => navigate('/')}
              >
                Voltar ao Dashboard
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
