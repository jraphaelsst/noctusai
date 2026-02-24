import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Subscription {
  id: string;
  org_id: string;
  plan_id: string;
  status: string;
  started_at: string;
  expires_at: string | null;
  canceled_at: string | null;
  stripe_subscription_id: string | null;
  stripe_customer_id: string | null;
  metadata: Record<string, any>;
  organizations?: { id: string; nome: string; slug: string };
  plans?: { id: string; name: string; slug: string; price_monthly: number; price_yearly: number };
  created_at: string;
}

export function AdminBilling() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await api.get('/api/subscriptions');
        setSubs(res.data || []);
      } catch (err) {
        console.error('Error fetching billing data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const activeSubs = subs.filter(s => s.status === 'active');
  const trialSubs = subs.filter(s => s.status === 'trial');
  const canceledSubs = subs.filter(s => s.status === 'canceled' || s.status === 'expired');

  // Calculate MRR from active subscriptions with plan pricing
  const mrr = activeSubs.reduce((total, sub) => {
    const monthlyPrice = sub.plans?.price_monthly || 0;
    return total + monthlyPrice;
  }, 0);

  // Calculate ARR projection
  const arr = mrr * 12;

  const filteredSubs = subs.filter(sub => {
    if (!search) return true;
    const term = search.toLowerCase();
    return (
      (sub.organizations?.nome || '').toLowerCase().includes(term) ||
      (sub.plans?.name || '').toLowerCase().includes(term) ||
      sub.status.toLowerCase().includes(term) ||
      (sub.stripe_subscription_id || '').toLowerCase().includes(term)
    );
  });

  const statusClass = (s: string) => {
    if (s === 'active') return 'badge-active';
    if (s === 'canceled' || s === 'expired') return 'badge-danger';
    if (s === 'trial') return 'badge-warning';
    return '';
  };

  const statusLabel = (s: string) => {
    if (s === 'active') return 'Ativo';
    if (s === 'canceled') return 'Cancelado';
    if (s === 'expired') return 'Expirado';
    if (s === 'trial') return 'Trial';
    return s;
  };

  function formatCurrency(value: number): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  }

  function formatDate(dateStr: string | null): string {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR');
  }

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Faturamento</h1>
          <p className="admin-page-subtitle">Receita e assinaturas da plataforma</p>
        </div>
      </div>

      {/* Revenue Overview */}
      <div className="admin-stats-grid billing-overview">
        <div className="admin-stat-card">
          <div className="admin-stat-icon">💰</div>
          <div className="admin-stat-value">{formatCurrency(mrr)}</div>
          <div className="admin-stat-label">MRR (Receita Mensal Recorrente)</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">📈</div>
          <div className="admin-stat-value">{formatCurrency(arr)}</div>
          <div className="admin-stat-label">ARR (Projeção Anual)</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">✅</div>
          <div className="admin-stat-value">{activeSubs.length}</div>
          <div className="admin-stat-label">Assinaturas Ativas</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">⏳</div>
          <div className="admin-stat-value">{trialSubs.length}</div>
          <div className="admin-stat-label">Em Trial</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">❌</div>
          <div className="admin-stat-value">{canceledSubs.length}</div>
          <div className="admin-stat-label">Canceladas/Expiradas</div>
        </div>
      </div>

      {/* Subscriptions Table */}
      <div style={{ marginTop: '32px' }}>
        <h2 className="admin-page-title" style={{ fontSize: '18px', marginBottom: '16px' }}>
          Todas as Assinaturas
        </h2>

        <div className="admin-toolbar">
          <input
            type="text"
            className="admin-search"
            placeholder="Buscar por organização, plano, status..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Organização</th>
                <th>Plano</th>
                <th>Valor Mensal</th>
                <th>Status</th>
                <th>Stripe ID</th>
                <th>Início</th>
                <th>Expira</th>
              </tr>
            </thead>
            <tbody>
              {filteredSubs.map(sub => (
                <tr key={sub.id} className={sub.status !== 'active' && sub.status !== 'trial' ? 'admin-row-inactive' : ''}>
                  <td className="admin-table-primary">
                    {sub.organizations?.nome || sub.org_id}
                  </td>
                  <td>{sub.plans?.name || sub.plan_id}</td>
                  <td>{formatCurrency(sub.plans?.price_monthly || 0)}</td>
                  <td>
                    <span className={`badge ${statusClass(sub.status)}`}>
                      {statusLabel(sub.status)}
                    </span>
                  </td>
                  <td>
                    {sub.stripe_subscription_id ? (
                      <code>{sub.stripe_subscription_id}</code>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>-</span>
                    )}
                  </td>
                  <td>{formatDate(sub.started_at)}</td>
                  <td>{formatDate(sub.expires_at)}</td>
                </tr>
              ))}
              {filteredSubs.length === 0 && (
                <tr>
                  <td colSpan={7} className="admin-table-empty">
                    {search ? 'Nenhuma assinatura encontrada para esta busca' : 'Nenhuma assinatura encontrada'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
