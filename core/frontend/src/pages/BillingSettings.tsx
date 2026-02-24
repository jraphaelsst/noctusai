import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';

interface BillingStatus {
  plan_name: string;
  plan_slug: string;
  status: string;
  billing_period: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  price: number;
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
  const { user, organization, loading: authLoading, logout } = useAuth();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const navigate = useNavigate();

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
      if (res.portal_url) {
        window.location.href = res.portal_url;
      }
    } catch (err: any) {
      alert(err.message || 'Erro ao abrir portal de pagamento');
    } finally {
      setPortalLoading(false);
    }
  }

  function formatDate(dateStr: string | null): string {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  }

  function formatCurrency(value: number): string {
    if (value === 0) return 'Grátis';
    return `R$ ${value.toFixed(2).replace('.', ',')}`;
  }

  function getStatusBadgeClass(status: string): string {
    switch (status) {
      case 'active': return 'badge-active';
      case 'trialing': return 'badge-warning';
      case 'canceled':
      case 'expired':
      case 'past_due':
        return 'badge-danger';
      default: return '';
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

  function getInvoiceStatusBadge(status: string): string {
    switch (status) {
      case 'paid': return 'badge-active';
      case 'open': return 'badge-warning';
      case 'void':
      case 'uncollectible':
        return 'badge-danger';
      default: return '';
    }
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  if (authLoading || loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando faturamento...</p>
      </div>
    );
  }

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

      <main className="billing-page">
        <div className="billing-header">
          <div>
            <h2>Faturamento</h2>
            <p>Gerencie seu plano e histórico de pagamentos</p>
          </div>
          <button className="btn-secondary" onClick={() => navigate('/pricing')}>
            Ver Planos
          </button>
        </div>

        {/* Current Plan Card */}
        <div className="billing-plan-card">
          <div className="billing-plan-info">
            <div className="billing-plan-top">
              <h3>{billing?.plan_name || 'Sem plano'}</h3>
              {billing && (
                <span className={`badge ${getStatusBadgeClass(billing.status)}`}>
                  {getStatusLabel(billing.status)}
                </span>
              )}
            </div>
            {billing && (
              <div className="billing-plan-details">
                <div className="billing-detail">
                  <span className="billing-detail-label">Valor</span>
                  <span className="billing-detail-value">
                    {formatCurrency(billing.price)}
                    {billing.price > 0 && (
                      <span className="billing-detail-period">
                        /{billing.billing_period === 'monthly' ? 'mês' : 'ano'}
                      </span>
                    )}
                  </span>
                </div>
                <div className="billing-detail">
                  <span className="billing-detail-label">Próxima cobrança</span>
                  <span className="billing-detail-value">
                    {billing.cancel_at_period_end
                      ? 'Cancela em ' + formatDate(billing.current_period_end)
                      : formatDate(billing.current_period_end)
                    }
                  </span>
                </div>
                <div className="billing-detail">
                  <span className="billing-detail-label">Período</span>
                  <span className="billing-detail-value">
                    {billing.billing_period === 'monthly' ? 'Mensal' : 'Anual'}
                  </span>
                </div>
              </div>
            )}
            {billing?.cancel_at_period_end && (
              <div className="billing-cancel-notice">
                Seu plano será cancelado ao final do período atual.
              </div>
            )}
          </div>
          <div className="billing-plan-actions">
            <button
              className="btn-primary billing-portal-btn"
              onClick={openPortal}
              disabled={portalLoading}
            >
              {portalLoading ? 'Redirecionando...' : 'Gerenciar Pagamento'}
            </button>
            <button className="btn-secondary" onClick={() => navigate('/pricing')}>
              Alterar Plano
            </button>
          </div>
        </div>

        {/* Invoices */}
        <div className="billing-invoices">
          <h3>Histórico de Faturas</h3>
          {invoices.length > 0 ? (
            <div className="admin-table-wrapper">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Descrição</th>
                    <th>Valor</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map(invoice => (
                    <tr key={invoice.id}>
                      <td>{formatDate(invoice.date)}</td>
                      <td>{invoice.description || 'Fatura NoctusAI'}</td>
                      <td className="admin-table-primary">{formatCurrency(invoice.amount)}</td>
                      <td>
                        <span className={`badge badge-sm ${getInvoiceStatusBadge(invoice.status)}`}>
                          {getInvoiceStatusLabel(invoice.status)}
                        </span>
                      </td>
                      <td>
                        {invoice.pdf_url ? (
                          <a
                            href={invoice.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-sm"
                          >
                            PDF
                          </a>
                        ) : (
                          <span className="billing-no-pdf">--</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="billing-empty-invoices">
              <p>Nenhuma fatura encontrada.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
