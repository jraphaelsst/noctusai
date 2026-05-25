import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../lib/api';
import { ProductIcon } from '../../lib/product-icon';

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

const STAT_CARDS = [
  { key: 'totalOrgs', label: 'Organizacoes', icon: '🏢', href: '/admin/orgs' },
  { key: 'totalProducts', label: 'Produtos', icon: '📦', href: '/admin/products' },
  // No dedicated licenses route — licenses are managed per-product on AdminProducts.
  { key: 'activeLicenses', label: 'Licencas Ativas', icon: '🔓', href: '/admin/products' },
  { key: 'activeSubscriptions', label: 'Assinaturas Ativas', icon: '💳', href: '/admin/subs' },
  { key: 'totalApiKeys', label: 'Chaves API', icon: '🔑', href: '/admin/api-keys' },
  { key: 'totalPlans', label: 'Planos', icon: '📋', href: '/admin/plans' },
] as const;

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
        // Per-endpoint catch: one failing endpoint must NOT zero the whole
        // dashboard — each stat degrades independently (empty) instead.
        const empty = { data: [] };
        const [orgs, subs, keys, plans, products, licenses] = await Promise.all([
          api.get('/api/organizations').catch(() => empty),
          api.get('/api/subscriptions').catch(() => empty),
          api.get('/api/admin/api-keys').catch(() => empty),
          api.get('/api/plans').catch(() => empty),
          api.get('/api/products').catch(() => empty),
          api.get('/api/licenses/all').catch(() => empty),
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

        const pStats: ProductStats[] = productList.map((p) => {
          const pLicenses = licenseList.filter((l) => l.product_id === p.id);
          return {
            product: p,
            active: pLicenses.filter((l) => l.status === 'active').length,
            revoked: pLicenses.filter((l) => l.status === 'revoked').length,
            total: pLicenses.length,
          };
        });
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
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
      <p className="text-muted-foreground mt-1">Visao geral da plataforma NoctusAI</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
        {STAT_CARDS.map(({ key, label, icon, href }) => (
          <button
            key={key}
            type="button"
            onClick={() => navigate(href)}
            className="bg-card rounded-lg border border-border shadow-sm p-6 text-left cursor-pointer hover:bg-muted/50 hover:border-primary/50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <div className="text-2xl mb-2">{icon}</div>
            <div className="text-3xl font-bold text-foreground">{stats[key]}</div>
            <div className="text-sm text-muted-foreground mt-1">{label}</div>
          </button>
        ))}
      </div>

      {/* Products Overview */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Produtos</h2>
            <p className="text-sm text-muted-foreground">Licencas por produto</p>
          </div>
          <button
            className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
            onClick={() => navigate('/admin/products')}
          >
            Ver todos
          </button>
        </div>

        <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Produto</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Ativas</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Revogadas</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {productStats.map(({ product, active, revoked, total }) => (
                <tr
                  key={product.id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => navigate('/admin/products')}
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <ProductIcon name={product.icone || 'Box'} color={product.cor} size="sm" />
                      {product.nome}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                      product.ativo
                        ? 'bg-success/10 text-success'
                        : 'bg-danger/10 text-danger'
                    }`}>
                      {product.ativo ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-success/10 text-success">
                      {active}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {revoked > 0
                      ? <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-danger/10 text-danger">{revoked}</span>
                      : <span className="text-muted-foreground">0</span>}
                  </td>
                  <td className="px-4 py-3 text-foreground">{total}</td>
                </tr>
              ))}
              {productStats.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum produto cadastrado
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
