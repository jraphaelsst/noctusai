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

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'active': return 'badge-active';
    case 'trial': return 'badge-warning';
    case 'canceled':
    case 'expired': return 'badge-danger';
    default: return '';
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
    return <div className="loading-screen"><div className="spinner" /><p>Carregando analytics...</p></div>;
  }

  return (
    <div className="analytics-page">
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Analytics</h1>
          <p className="admin-page-subtitle">Metricas e saude da plataforma</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="admin-stats-grid">
        <div className="admin-stat-card">
          <div className="admin-stat-icon">💰</div>
          <div className="admin-stat-value">{overview ? formatCurrency(overview.mrr) : '-'}</div>
          <div className="admin-stat-label">MRR</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">🏢</div>
          <div className="admin-stat-value">{overview?.total_orgs ?? 0}</div>
          <div className="admin-stat-label">Total Organizacoes</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">✅</div>
          <div className="admin-stat-value">{overview?.active_orgs ?? 0}</div>
          <div className="admin-stat-label">Orgs Ativas</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">👥</div>
          <div className="admin-stat-value">{overview?.total_users ?? 0}</div>
          <div className="admin-stat-label">Total Usuarios</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">📉</div>
          <div className="admin-stat-value">{overview?.churn_rate ?? 0}%</div>
          <div className="admin-stat-label">Churn (30d)</div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="analytics-tabs">
        <button
          className={`analytics-tab ${activeTab === 'revenue' ? 'active' : ''}`}
          onClick={() => setActiveTab('revenue')}
        >
          Receita Mensal
        </button>
        <button
          className={`analytics-tab ${activeTab === 'tenants' ? 'active' : ''}`}
          onClick={() => setActiveTab('tenants')}
        >
          Saude dos Tenants
        </button>
      </div>

      {/* Revenue Table */}
      {activeTab === 'revenue' && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Mes</th>
                <th>Novas Assinaturas</th>
                <th>Canceladas</th>
                <th>MRR</th>
              </tr>
            </thead>
            <tbody>
              {revenue.length === 0 ? (
                <tr>
                  <td colSpan={4} className="admin-table-empty">
                    Nenhum dado de receita disponivel
                  </td>
                </tr>
              ) : (
                revenue.map(row => (
                  <tr key={row.month}>
                    <td className="admin-table-primary">{formatMonth(row.month)}</td>
                    <td>
                      <span className="badge badge-sm badge-active">+{row.new_subs}</span>
                    </td>
                    <td>
                      {row.churned > 0 ? (
                        <span className="badge badge-sm badge-danger">-{row.churned}</span>
                      ) : (
                        <span className="badge badge-sm">0</span>
                      )}
                    </td>
                    <td className="admin-table-primary">{formatCurrency(row.mrr)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tenants Table */}
      {activeTab === 'tenants' && (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Organizacao</th>
                <th>Usuarios</th>
                <th>Plano</th>
                <th>Status</th>
                <th>Ultima Atividade</th>
                <th>Criado em</th>
              </tr>
            </thead>
            <tbody>
              {tenants.length === 0 ? (
                <tr>
                  <td colSpan={6} className="admin-table-empty">
                    Nenhum tenant encontrado
                  </td>
                </tr>
              ) : (
                tenants.map(tenant => (
                  <tr key={tenant.org_id}>
                    <td className="admin-table-primary">{tenant.org_nome}</td>
                    <td>{tenant.user_count}</td>
                    <td>{tenant.plan}</td>
                    <td>
                      <span className={`badge badge-sm ${statusBadgeClass(tenant.status)}`}>
                        {statusLabel(tenant.status)}
                      </span>
                    </td>
                    <td>{formatDate(tenant.last_active)}</td>
                    <td>{formatDate(tenant.created_at)}</td>
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
