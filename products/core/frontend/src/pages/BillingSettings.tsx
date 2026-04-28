import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/utils';
import { NotificationBell } from '../components/NotificationBell';
import { Header, useTheme } from "@noctusai/lib/design-system";

interface BillingPlan {
  id: string;
  name: string;
  slug: string;
  price_monthly: number;
  price_yearly: number;
  is_active: boolean;
}

interface BillingSubscription {
  id: string;
  status: string;
  started_at: string | null;
  expires_at: string | null;
  canceled_at: string | null;
  stripe_subscription_id: string | null;
  stripe_customer_id: string | null;
  metadata: Record<string, unknown>;
  plans?: BillingPlan;
}

interface BillingStatus {
  has_subscription: boolean;
  subscription: BillingSubscription | null;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  plan: BillingPlan | null;
  next_invoice: {
    amount_due: number;
    currency: string;
    period_start: string | null;
    period_end: string | null;
    next_payment_attempt: string | null;
  } | null;
  payment_method: {
    brand: string;
    last4: string;
    exp_month: number;
    exp_year: number;
  } | null;
}

interface Invoice {
  id: string;
  date: string;
  amount: number;
  status: string;
  pdf_url: string | null;
  description: string | null;
}

export function BillingSettings() {
  const { user, organization, isAdmin, loading: authLoading, logout } = useAuth();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate('/login'); return; }

    async function fetchBilling() {
      try {
        const [statusRes, invoicesRes] = await Promise.all([
          api.get('/api/billing/status'),
          api.get('/api/billing/invoices').catch(() => ({ data: [] })),
        ]);
        setBilling(statusRes.data || statusRes);
        setInvoices(invoicesRes.data || []);
      } catch (err) {
        console.error('Erro ao carregar faturamento:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchBilling();
  }, [authLoading, user]);

  async function openPortal() {
    setPortalLoading(true);
    try {
      const res = await api.post('/api/billing/portal');
      if (res.data?.portal_url) {
        window.location.href = res.data.portal_url;
      }
    } catch (err: any) {
      alert(err.message || 'Erro ao abrir portal de pagamento');
    } finally {
      setPortalLoading(false);
    }
  }

  function getStatusBadgeClasses(status: string): string {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-800';
      case 'trialing': return 'bg-yellow-100 text-yellow-800';
      case 'canceled':
      case 'expired':
      case 'past_due':
        return 'bg-red-100 text-red-800';
      default: return 'bg-muted text-muted-foreground';
    }
  }

  function getStatusLabel(status: string): string {
    switch (status) {
      case 'active': return 'Ativo';
      case 'trialing': return 'Trial';
      case 'canceled': return 'Cancelado';
      case 'expired': return 'Expirado';
      case 'past_due': return 'Pagamento pendente';
      default: return status;
    }
  }

  function getInvoiceStatusLabel(status: string): string {
    switch (status) {
      case 'paid': return 'Pago';
      case 'open': return 'Em aberto';
      case 'void': return 'Cancelado';
      case 'draft': return 'Rascunho';
      case 'uncollectible': return 'Não cobrado';
      default: return status;
    }
  }

  function getInvoiceStatusClasses(status: string): string {
    switch (status) {
      case 'paid': return 'bg-green-100 text-green-800';
      case 'open': return 'bg-yellow-100 text-yellow-800';
      case 'void':
      case 'uncollectible':
        return 'bg-red-100 text-red-800';
      default: return 'bg-muted text-muted-foreground';
    }
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  if (authLoading || loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Carregando faturamento...</p>
      </div>
    );
  }

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

      <main className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Faturamento</h2>
            <p className="mt-1 text-muted-foreground">Gerencie seu plano e histórico de pagamentos</p>
          </div>
          <button
            className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
            onClick={() => navigate('/pricing')}
          >
            Ver Planos
          </button>
        </div>

        {/* Current Plan Card */}
        <div className="mb-8 rounded-lg border border-border bg-card p-6 shadow-sm">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-foreground">
                  {billing?.plan?.name || 'Sem plano'}
                </h3>
                {billing?.subscription && (
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusBadgeClasses(billing.subscription.status)}`}>
                    {getStatusLabel(billing.subscription.status)}
                  </span>
                )}
              </div>
              {billing && (
                <div className="mt-4 grid gap-4 sm:grid-cols-3">
                  <div>
                    <span className="block text-xs text-muted-foreground">Valor</span>
                    <span className="text-sm font-medium text-foreground">
                      {formatCurrency(billing.plan?.price_monthly ?? 0)}
                      {(billing.plan?.price_monthly ?? 0) > 0 && (
                        <span className="text-muted-foreground">/mes</span>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="block text-xs text-muted-foreground">Proxima cobranca</span>
                    <span className="text-sm font-medium text-foreground">
                      {billing.subscription?.metadata?.cancel_at_period_end
                        ? 'Cancela em ' + formatDate(billing.next_invoice?.next_payment_attempt)
                        : formatDate(billing.next_invoice?.next_payment_attempt)
                      }
                    </span>
                  </div>
                  {billing.payment_method && (
                    <div>
                      <span className="block text-xs text-muted-foreground">Pagamento</span>
                      <span className="text-sm font-medium text-foreground">
                        {billing.payment_method.brand} **** {billing.payment_method.last4}
                      </span>
                    </div>
                  )}
                </div>
              )}
              {Boolean(billing?.subscription?.metadata?.cancel_at_period_end) && (
                <div className="mt-4 rounded-md bg-yellow-50 px-4 py-2 text-sm text-yellow-800">
                  Seu plano sera cancelado ao final do periodo atual.
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 border-t border-border pt-4">
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={openPortal}
              disabled={portalLoading}
            >
              {portalLoading ? 'Redirecionando...' : 'Gerenciar Pagamento'}
            </button>
            <button
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
              onClick={() => navigate('/pricing')}
            >
              Alterar Plano
            </button>
          </div>
        </div>

        {/* Invoices */}
        <div>
          <h3 className="mb-4 text-lg font-semibold text-foreground">Histórico de Faturas</h3>
          {invoices.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Data</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Descrição</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Valor</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {invoices.map(invoice => (
                    <tr key={invoice.id} className="bg-card">
                      <td className="px-4 py-3 text-foreground">{formatDate(invoice.date)}</td>
                      <td className="px-4 py-3 text-foreground">{invoice.description || 'Fatura NoctusAI'}</td>
                      <td className="px-4 py-3 font-medium text-foreground">{formatCurrency(invoice.amount)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${getInvoiceStatusClasses(invoice.status)}`}>
                          {getInvoiceStatusLabel(invoice.status)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {invoice.pdf_url ? (
                          <a
                            href={invoice.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-muted"
                          >
                            PDF
                          </a>
                        ) : (
                          <span className="text-muted-foreground">--</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-card py-12 text-center">
              <p className="text-muted-foreground">Nenhuma fatura encontrada.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
