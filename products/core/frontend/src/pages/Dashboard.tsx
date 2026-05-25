import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';
import { NotificationBell } from '../components/NotificationBell';
import { Header, useTheme } from "@noctusai/lib/design-system";
import { ProductIcon } from '../lib/product-icon';

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
  plans?: { nome: string; slug: string };
}

export function Dashboard() {
  const { user, organization, isAdmin, loading: authLoading, logout, refresh } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  // slug -> is the product's container deployed (reachable) in THIS env.
  // Undefined while loading; a slug mapped to `false` shows a "dev" badge.
  const [deployed, setDeployed] = useState<Record<string, boolean>>({});
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState<string | null>(null);
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate('/login'); return; }

    async function fetchData() {
      try {
        const [meRes, subRes, deployRes] = await Promise.all([
          api.get('/api/auth/me'),
          api.get('/api/subscriptions/me').catch(() => ({ data: null })),
          // Deployment status is best-effort: a failure must never block the
          // dashboard, it just means no "dev" badges are shown.
          api.get('/api/products/deployment-status').catch(() => ({ deployed: {} })),
        ]);
        setProducts(meRes.products || []);
        setSubscription(subRes.data);
        setDeployed(deployRes.deployed || {});
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
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="text-sm text-muted-foreground">Carregando NoctusAI...</p>
      </div>
    );
  }

  const headerUser = {
    name: user?.nome || '',
    email: user?.email || '',
    role: isAdmin ? 'Administrador' : 'Membro',
  };

  const handleUpdateProfile = async (data: { name: string; email: string; phone: string }) => {
    await api.patch('/api/auth/profile', { nome: data.name });
    refresh();
  };

  const handleUpdatePassword = async (newPassword: string) => {
    await api.post('/api/auth/change-password', { new_password: newPassword });
  };

  return (
    <div className="min-h-screen bg-background">
      <Header
        variant="dark"
        user={headerUser}
        onLogout={handleLogout}
        theme={theme}
        onThemeToggle={toggleTheme}
        onUpdateProfile={handleUpdateProfile}
        onUpdatePassword={handleUpdatePassword}
        actions={
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button
                className="h-9 rounded-md bg-primary text-primary-foreground px-4 text-sm font-medium hover:bg-primary/90 transition-colors"
                onClick={() => navigate('/admin')}
              >
                Admin Panel
              </button>
            )}
            <NotificationBell />
          </div>
        }
      />

      {/* Main content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {/* Trial countdown */}
        {isTrial && trialDays !== null && (
          <div className="mb-6 rounded-lg border border-warning bg-warning-light px-4 py-3 flex items-center gap-3 text-sm">
            <span className="text-lg">⏳</span>
            <span className="text-warning-foreground flex-1">
              {trialDays > 0
                ? `Seu período de teste expira em ${trialDays} dia${trialDays !== 1 ? 's' : ''}.`
                : 'Seu período de teste expirou.'}
            </span>
            <button
              className="rounded-md bg-warning text-warning-foreground px-4 py-1.5 text-sm font-medium hover:opacity-90 transition-opacity"
              onClick={() => navigate('/pricing')}
            >
              Assinar agora
            </button>
          </div>
        )}

        {/* Upgrade banner for free orgs (not test) */}
        {isFreeOrg && !isTestOrg && !isTrial && (
          <div className="mb-6 rounded-lg border border-primary/20 bg-primary/5 p-5 flex items-center gap-4">
            <div className="flex-1">
              <p className="font-semibold text-foreground">Desbloqueie todo o potencial do NoctusAI</p>
              <p className="text-sm text-muted-foreground mt-1">
                Atualize seu plano para acessar recursos avançados, mais usuários e suporte prioritário.
              </p>
            </div>
            <button
              className="rounded-md bg-primary text-primary-foreground px-5 py-2 text-sm font-medium hover:bg-primary/90 transition-colors whitespace-nowrap"
              onClick={() => navigate('/pricing')}
            >
              Ver planos
            </button>
          </div>
        )}

        {/* Welcome */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-foreground">
            Bem-vindo, {user?.nome?.split(' ')[0]}!
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Seus produtos NoctusAI
            {isTestOrg && (
              <span className="ml-2 inline-flex items-center rounded-full bg-warning-light text-warning-foreground px-2.5 py-0.5 text-xs font-medium">
                Conta Teste
              </span>
            )}
            {subscription && !isTestOrg && (
              <span className={`ml-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                subscription.status === 'active'
                  ? 'bg-success-light text-success-foreground'
                  : 'bg-muted text-muted-foreground'
              }`}>
                {subscription.plans?.nome || subscription.status}
              </span>
            )}
          </p>
        </div>

        {/* Products grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...products].sort((a, b) => Number(b.has_access) - Number(a.has_access)).map(product => (
            <div
              key={product.id}
              className={`relative bg-card rounded-lg border border-border shadow-sm p-6 transition-all ${
                product.has_access
                  ? 'cursor-pointer hover:shadow-md hover:border-primary/30'
                  : 'opacity-60 cursor-not-allowed'
              }`}
              onClick={() => launchProduct(product)}
            >
              {deployed[product.slug] === false && (
                <span
                  className="absolute top-3 right-3 inline-flex items-center rounded-full bg-warning-light text-warning-foreground px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                  title="Em desenvolvimento — ainda não publicado neste ambiente"
                >
                  dev
                </span>
              )}
              <div className="mb-3"><ProductIcon name={product.icone} color={product.cor} /></div>
              <h3 className="text-lg font-semibold text-foreground mb-1">{product.nome}</h3>
              <p className="text-sm text-muted-foreground mb-4">{product.descricao}</p>

              {product.has_access ? (
                <div className="flex items-center gap-1.5 text-sm font-medium text-success-foreground">
                  <span className="text-success">●</span>
                  {launching === product.slug ? 'Abrindo...' : 'Acessar'}
                  <span className="ml-auto">→</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <span>🔒</span>
                  Solicitar acesso
                </div>
              )}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
