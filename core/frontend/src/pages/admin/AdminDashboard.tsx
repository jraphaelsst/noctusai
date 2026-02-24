import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Stats {
  totalOrgs: number;
  activeSubscriptions: number;
  totalApiKeys: number;
  totalPlans: number;
}

export function AdminDashboard() {
  const [stats, setStats] = useState<Stats>({ totalOrgs: 0, activeSubscriptions: 0, totalApiKeys: 0, totalPlans: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const [orgs, subs, keys, plans] = await Promise.all([
          api.get('/api/organizations'),
          api.get('/api/subscriptions'),
          api.get('/api/admin/api-keys'),
          api.get('/api/plans'),
        ]);
        setStats({
          totalOrgs: orgs.data?.length || 0,
          activeSubscriptions: (subs.data || []).filter((s: any) => s.status === 'active').length,
          totalApiKeys: (keys.data || []).filter((k: any) => k.is_active).length,
          totalPlans: plans.data?.length || 0,
        });
      } catch (err) {
        console.error('Error fetching admin stats:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <h1 className="admin-page-title">Dashboard</h1>
      <p className="admin-page-subtitle">Visão geral da plataforma NoctusAI</p>

      <div className="admin-stats-grid">
        <div className="admin-stat-card">
          <div className="admin-stat-icon">🏢</div>
          <div className="admin-stat-value">{stats.totalOrgs}</div>
          <div className="admin-stat-label">Organizações</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">💳</div>
          <div className="admin-stat-value">{stats.activeSubscriptions}</div>
          <div className="admin-stat-label">Assinaturas Ativas</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">🔑</div>
          <div className="admin-stat-value">{stats.totalApiKeys}</div>
          <div className="admin-stat-label">Chaves API</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">📋</div>
          <div className="admin-stat-value">{stats.totalPlans}</div>
          <div className="admin-stat-label">Planos</div>
        </div>
      </div>
    </div>
  );
}
