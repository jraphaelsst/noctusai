/**
 * <AdminProductControl/> — the centralized board for the product WORKING GUIDE.
 *
 * The same two toggles live on the products table and on the dashboard cards
 * (for quick, in-context changes). This page exists for the other job: seeing
 * the WHOLE fleet's working state at once, grouped by what it means for us.
 *
 *     PROD   ativo + live → dev-validate, then promote
 *     DEV    ativo + dev  → worked in dev only; never reaches prod
 *     IGNORE inativo      → do not touch this product at all
 *
 * Grouping is the point. A flat list with two badges per row makes you compute
 * the buckets in your head every time; the buckets ARE the decision, so the
 * page renders them directly.
 *
 * Runtime reachability (/api/products/deployment-status) is shown alongside but
 * deliberately NOT merged into the buckets — it answers "is it up?", which is a
 * different question from "do we work it here?". Where the two disagree, that
 * mismatch is surfaced rather than hidden, because it is usually the
 * interesting thing on the page.
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { api } from '../../lib/api';
import { ProductIcon } from '../../lib/product-icon';
import {
  BUCKETS,
  bucketOf,
  DeployScopeToggle,
  StatusToggle,
  type DeployScope,
} from '../../components/ProductStateControls';

interface Product {
  id: string;
  nome: string;
  slug: string;
  descricao: string | null;
  icone: string | null;
  url_base: string;
  cor: string;
  ativo: boolean;
  deploy_scope: DeployScope;
}

export function AdminProductControl() {
  const [products, setProducts] = useState<Product[]>([]);
  const [deployed, setDeployed] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchProducts() {
    // include_inactive: the ignored bucket is the whole reason this page
    // exists, so it must see rows the marketplace hides.
    const res = await api.get('/api/products?include_inactive=true');
    setProducts(res.data || []);
  }

  async function fetchAll() {
    try {
      await Promise.all([
        fetchProducts(),
        api
          .get('/api/products/deployment-status')
          .then((r: any) => setDeployed(r.deployed || {}))
          // Best-effort: the probe is auxiliary context, never a reason to
          // fail the page that governs the fleet.
          .catch(() => setDeployed({})),
      ]);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Falha ao carregar produtos');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAll();
  }, []);

  async function mutate(id: string, fn: () => Promise<unknown>) {
    setBusyId(id);
    try {
      await fn();
      await fetchProducts();
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Falha ao aplicar a alteracao');
    } finally {
      setBusyId(null);
    }
  }

  const setActivation = (id: string, ativo: boolean) =>
    mutate(id, () => api.post(`/api/products/${id}/activation`, { ativo }));

  const setScope = (id: string, deploy_scope: DeployScope) =>
    mutate(id, () => api.post(`/api/products/${id}/deploy-scope`, { deploy_scope }));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  const counts = {
    prod: products.filter(p => bucketOf(p) === 'prod').length,
    dev: products.filter(p => bucketOf(p) === 'dev').length,
    ignore: products.filter(p => bucketOf(p) === 'ignore').length,
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Controle de Produtos</h1>
        <p className="text-muted-foreground mt-1">
          Onde trabalhamos cada produto — {counts.prod} em producao · {counts.dev} em dev ·{' '}
          {counts.ignore} ignorados
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="space-y-6">
        {BUCKETS.map(bucket => {
          const rows = products.filter(p => bucketOf(p) === bucket.key);
          return (
            <section
              key={bucket.key}
              className={`bg-card rounded-lg border-2 ${bucket.tone} shadow-sm overflow-hidden`}
            >
              <header className="px-4 py-3 border-b border-border bg-muted/40">
                <div className="flex items-baseline gap-2">
                  <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">
                    {bucket.title}
                  </h2>
                  <span className="text-xs text-muted-foreground">({rows.length})</span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{bucket.rule}</p>
              </header>

              {rows.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted-foreground text-center">
                  Nenhum produto neste grupo.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {rows.map(p => {
                    // "We work this in prod" but the container is not up — or
                    // the reverse. Neither is an error; both are worth seeing.
                    const reachable = deployed[p.slug];
                    const mismatch =
                      reachable !== undefined &&
                      ((bucketOf(p) === 'prod' && !reachable) ||
                        (bucketOf(p) === 'ignore' && reachable));

                    return (
                      <li key={p.id} className="flex items-center gap-3 px-4 py-3">
                        <ProductIcon name={p.icone || 'Box'} color={p.cor} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-foreground truncate">{p.nome}</span>
                            {mismatch && (
                              <span
                                className="inline-flex items-center gap-1 text-[10px] text-warning"
                                title={
                                  bucketOf(p) === 'prod'
                                    ? 'Marcado para producao, mas o container nao esta alcancavel neste ambiente'
                                    : 'Produto ignorado, mas o container ainda esta rodando'
                                }
                              >
                                <AlertTriangle className="w-3 h-3" />
                                container
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-muted-foreground">{p.slug}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <StatusToggle
                            ativo={p.ativo}
                            deployScope={p.deploy_scope}
                            busy={busyId === p.id}
                            onToggle={next => setActivation(p.id, next)}
                          />
                          <DeployScopeToggle
                            ativo={p.ativo}
                            deployScope={p.deploy_scope}
                            busy={busyId === p.id}
                            onToggle={next => setScope(p.id, next)}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
