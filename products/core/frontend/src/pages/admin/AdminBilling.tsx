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
  plans?: { id: string; nome: string; slug: string; price_monthly: number; price_yearly: number };
  created_at: string;
}

function statusBadgeClasses(s: string): string {
  if (s === 'active') return 'bg-success/10 text-success';
  if (s === 'canceled' || s === 'expired') return 'bg-danger/10 text-danger';
  if (s === 'trial') return 'bg-warning/10 text-warning';
  return 'bg-muted text-muted-foreground';
}

function statusLabel(s: string): string {
  if (s === 'active') return 'Ativo';
  if (s === 'canceled') return 'Cancelado';
  if (s === 'expired') return 'Expirado';
  if (s === 'trial') return 'Trial';
  return s;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('pt-BR');
}

const STAT_ICONS = ['💰', '📈', '✅', '⏳', '❌'] as const;

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

  const mrr = activeSubs.reduce((total, sub) => total + (sub.plans?.price_monthly || 0), 0);
  const arr = mrr * 12;

  const filteredSubs = subs.filter(sub => {
    if (!search) return true;
    const term = search.toLowerCase();
    return (
      (sub.organizations?.nome || '').toLowerCase().includes(term) ||
      (sub.plans?.nome || '').toLowerCase().includes(term) ||
      sub.status.toLowerCase().includes(term) ||
      (sub.stripe_subscription_id || '').toLowerCase().includes(term)
    );
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  const statCards = [
    { icon: STAT_ICONS[0], value: formatCurrency(mrr), label: 'MRR (Receita Mensal Recorrente)' },
    { icon: STAT_ICONS[1], value: formatCurrency(arr), label: 'ARR (Projecao Anual)' },
    { icon: STAT_ICONS[2], value: activeSubs.length, label: 'Assinaturas Ativas' },
    { icon: STAT_ICONS[3], value: trialSubs.length, label: 'Em Trial' },
    { icon: STAT_ICONS[4], value: canceledSubs.length, label: 'Canceladas/Expiradas' },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Faturamento</h1>
          <p className="text-muted-foreground mt-1">Receita e assinaturas da plataforma</p>
        </div>
      </div>

      {/* Revenue Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {statCards.map(({ icon, value, label }) => (
          <div key={label} className="bg-card rounded-lg border border-border shadow-sm p-6">
            <div className="text-2xl mb-2">{icon}</div>
            <div className="text-2xl font-bold text-foreground">{value}</div>
            <div className="text-sm text-muted-foreground mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Subscriptions Table */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-foreground mb-4">Todas as Assinaturas</h2>

        <div className="mb-4">
          <input
            type="text"
            placeholder="Buscar por organizacao, plano, status..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full max-w-md h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organizacao</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plano</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Valor Mensal</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Stripe ID</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Inicio</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Expira</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredSubs.map(sub => (
                <tr
                  key={sub.id}
                  className={`hover:bg-muted/50 transition-colors ${
                    sub.status !== 'active' && sub.status !== 'trial' ? 'opacity-50' : ''
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    {sub.organizations?.nome || sub.org_id}
                  </td>
                  <td className="px-4 py-3 text-foreground">{sub.plans?.nome || sub.plan_id}</td>
                  <td className="px-4 py-3 text-foreground">{formatCurrency(sub.plans?.price_monthly || 0)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClasses(sub.status)}`}>
                      {statusLabel(sub.status)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {sub.stripe_subscription_id ? (
                      <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{sub.stripe_subscription_id}</code>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(sub.started_at)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(sub.expires_at)}</td>
                </tr>
              ))}
              {filteredSubs.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
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
