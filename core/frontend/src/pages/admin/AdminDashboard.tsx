import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../lib/api';

interface Stats {
  totalOrgs: number;
  activeSubscriptions: number;
  totalApiKeys: number;
  totalPlans: number;
  totalProducts: number;
  activeLicenses: number;
}

interface Product {
  id: string;
  nome: string;
  slug: string;
  icone: string | null;
  cor: string;
  ativo: boolean;
}

interface License {
  id: string;
  product_id: string;
  org_id: string;
  status: string;
  created_at: string;
  fim?: string | null;
  organizations?: { id: string; nome: string };
}

interface ProductStats {
  product: Product;
  active: number;
  revoked: number;
  total: number;
}

export function AdminDashboard() {
  const [stats, setStats] = useState<Stats>({
    totalOrgs: 0, activeSubscriptions: 0, totalApiKeys: 0,
    totalPlans: 0, totalProducts: 0, activeLicenses: 0,
  });
  const [productStats, setProductStats] = useState<ProductStats[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    async function fetchStats() {
      try {
        const [orgs, subs, keys, plans, products, licenses] = await Promise.all([
          api.get('/api/organizations'),
          api.get('/api/subscriptions'),
          api.get('/api/admin/api-keys'),
          api.get('/api/plans'),
          api.get('/api/products'),
          api.get('/api/licenses/all'),
        ]);

        const productList: Product[] = products.data || [];
        const licenseList: License[] = licenses.data || [];
        const activeLicenses = licenseList.filter((l) => l.status === 'active');

        setStats({
          totalOrgs: orgs.data?.length || 0,
          activeSubscriptions: (subs.data || []).filter((s: any) => s.status === 'active').length,
          totalApiKeys: (keys.data || []).filter((k: any) => k.is_active).length,
          totalPlans: plans.data?.length || 0,
          totalProducts: productList.length,
          activeLicenses: activeLicenses.length,
        });

        // Per-product license breakdown
        const pStats: ProductStats[] = productList.map((p) => {
          const pLicenses = licenseList.filter((l) => l.product_id === p.id);
          return {
            product: p,
            active: pLicenses.filter((l) => l.status === 'active').length,
            revoked: pLicenses.filter((l) => l.status === 'revoked').length,
            total: pLicenses.length,
          };
        });
        // Sort by active licenses descending
        pStats.sort((a, b) => b.active - a.active);
        setProductStats(pStats);
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
          <div className="admin-stat-icon">📦</div>
          <div className="admin-stat-value">{stats.totalProducts}</div>
          <div className="admin-stat-label">Produtos</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">🔓</div>
          <div className="admin-stat-value">{stats.activeLicenses}</div>
          <div className="admin-stat-label">Licenças Ativas</div>
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

      {/* Products Overview */}
      <div style={{ marginTop: '2rem' }}>
        <div className="admin-page-header">
          <div>
            <h2 className="admin-page-title" style={{ fontSize: '1.25rem' }}>Produtos</h2>
            <p className="admin-page-subtitle">Licenças por produto</p>
          </div>
          <button className="btn-secondary" onClick={() => navigate('/admin/products')}>
            Ver todos
          </button>
        </div>

        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Produto</th>
                <th>Status</th>
                <th>Ativas</th>
                <th>Revogadas</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {productStats.map(({ product, active, revoked, total }) => (
                <tr
                  key={product.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate('/admin/products')}
                >
                  <td className="admin-table-primary">
                    <span style={{ marginRight: '0.5rem' }}>{product.icone || '📦'}</span>
                    {product.nome}
                  </td>
                  <td>
                    <span className={`badge ${product.ativo ? 'badge-active' : 'badge-danger'}`}>
                      {product.ativo ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-active">{active}</span>
                  </td>
                  <td>
                    {revoked > 0
                      ? <span className="badge badge-danger">{revoked}</span>
                      : <span style={{ color: '#64748b' }}>0</span>}
                  </td>
                  <td>{total}</td>
                </tr>
              ))}
              {productStats.length === 0 && (
                <tr><td colSpan={5} className="admin-table-empty">Nenhum produto cadastrado</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
