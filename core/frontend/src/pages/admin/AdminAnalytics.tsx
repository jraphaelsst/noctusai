import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Overview {
  mrr: number;
  total_orgs: number;
  active_orgs: number;
  total_users: number;
  churn_rate: number;
}

interface RevenueMonth {
  month: string;
  new_subs: number;
  churned: number;
  mrr: number;
}

interface Tenant {
  org_id: string;
  org_nome: string;
  slug: string;
  user_count: number;
  plan: string;
  status: string;
  last_active: string | null;
  created_at: string | null;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  try {
    return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(dateStr));
  } catch {
    return dateStr;
  }
}

function formatMonth(monthStr: string): string {
  try {
    const [year, month] = monthStr.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: 'numeric' }).format(date);
  } catch {
    return monthStr;
  }
}

function statusBadgeClasses(status: string): string {
  switch (status) {
    case 'active': return 'bg-success/10 text-success';
    case 'trial': return 'bg-warning/10 text-warning';
    case 'canceled':
    case 'expired': return 'bg-danger/10 text-danger';
    default: return 'bg-muted text-muted-foreground';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'active': return 'Ativo';
    case 'trial': return 'Trial';
    case 'canceled': return 'Cancelado';
    case 'expired': return 'Expirado';
    case 'none': return 'Sem plano';
    default: return status;
  }
}

export function AdminAnalytics() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [revenue, setRevenue] = useState<RevenueMonth[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'revenue' | 'tenants'>('revenue');

  useEffect(() => {
    async function fetchData() {
      try {
        const [overviewRes, revenueRes, tenantsRes] = await Promise.all([
          api.get('/api/admin/analytics/overview'),
          api.get('/api/admin/analytics/revenue'),
          api.get('/api/admin/analytics/tenants'),
        ]);
        setOverview(overviewRes.data);
        setRevenue(revenueRes.data || []);
        setTenants(tenantsRes.data || []);
      } catch (err) {
        console.error('Error fetching analytics:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando analytics...</p>
      </div>
    );
  }

  const kpiCards = [
    { icon: '💰', value: overview ? formatCurrency(overview.mrr) : '-', label: 'MRR' },
    { icon: '🏢', value: overview?.total_orgs ?? 0, label: 'Total Organizacoes' },
    { icon: '✅', value: overview?.active_orgs ?? 0, label: 'Orgs Ativas' },
    { icon: '👥', value: overview?.total_users ?? 0, label: 'Total Usuarios' },
    { icon: '📉', value: `${overview?.churn_rate ?? 0}%`, label: 'Churn (30d)' },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
          <p className="text-muted-foreground mt-1">Metricas e saude da plataforma</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {kpiCards.map(({ icon, value, label }) => (
          <div key={label} className="bg-card rounded-lg border border-border shadow-sm p-6">
            <div className="text-2xl mb-2">{icon}</div>
            <div className="text-2xl font-bold text-foreground">{value}</div>
            <div className="text-sm text-muted-foreground mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 mt-8 mb-4 border-b border-border">
        <button
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === 'revenue'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          onClick={() => setActiveTab('revenue')}
        >
          Receita Mensal
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === 'tenants'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          onClick={() => setActiveTab('tenants')}
        >
          Saude dos Tenants
        </button>
      </div>

      {/* Revenue Table */}
      {activeTab === 'revenue' && (
        <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Mes</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Novas Assinaturas</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Canceladas</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">MRR</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {revenue.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum dado de receita disponivel
                  </td>
                </tr>
              ) : (
                revenue.map(row => (
                  <tr key={row.month} className="hover:bg-muted/50 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">{formatMonth(row.month)}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-success/10 text-success">
                        +{row.new_subs}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {row.churned > 0 ? (
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-danger/10 text-danger">
                          -{row.churned}
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">0</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">{formatCurrency(row.mrr)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tenants Table */}
      {activeTab === 'tenants' && (
        <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organizacao</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Usuarios</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plano</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Ultima Atividade</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Criado em</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tenants.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum tenant encontrado
                  </td>
                </tr>
              ) : (
                tenants.map(tenant => (
                  <tr key={tenant.org_id} className="hover:bg-muted/50 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">{tenant.org_nome}</td>
                    <td className="px-4 py-3 text-foreground">{tenant.user_count}</td>
                    <td className="px-4 py-3 text-foreground">{tenant.plan}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClasses(tenant.status)}`}>
                        {statusLabel(tenant.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDate(tenant.last_active)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDate(tenant.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
