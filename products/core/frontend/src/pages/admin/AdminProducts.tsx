import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { ProductIcon } from '../../lib/product-icon';
import {
  BUCKETS,
  bucketOf,
  ColorPickerButton,
  DeployScopeToggle,
  EditIconButton,
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
  // Working scope — stored INTENT ("where do we work this product?"), distinct
  // from `/api/products/deployment-status`, which reports runtime reachability.
  deploy_scope: DeployScope;
  created_at: string;
}

interface License {
  id: string;
  org_id: string;
  product_id: string;
  status: string;
  created_at: string;
  fim?: string | null;
  products?: Product;
  organizations?: { id: string; nome: string; slug: string };
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
}

const EMPTY_PRODUCT_FORM = {
  nome: '',
  slug: '',
  descricao: '',
  // A product must ship a real icon (icone is required + non-empty server-side).
  // Default to the scaffolder default "Box"; pick any registered ProductIcon
  // name (see lib/product-icon.tsx ICONS) or an emoji.
  icone: 'Box',
  url_base: '',
  cor: '#6366f1',
};

function statusBadgeClasses(s: string): string {
  if (s === 'active') return 'bg-success/10 text-success';
  if (s === 'revoked') return 'bg-danger/10 text-danger';
  return 'bg-muted text-muted-foreground';
}

// Deployment (prod/dev) badge — consumes the SAME /api/products/deployment-status
// the marketplace launcher uses. `deployed` is per-slug container reachability in
// THIS environment (live when reachable — i.e. running in prod when core runs in
// prod; "dev" when the container isn't up here). `undefined` = still probing.
function DeploymentBadge({ deployed }: { deployed: boolean | undefined }) {
  if (deployed === undefined) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return deployed ? (
    <span
      className="inline-flex items-center rounded-full bg-success/10 text-success px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      title="Container reachable in this environment (live / prod)"
    >
      live
    </span>
  ) : (
    <span
      className="inline-flex items-center rounded-full bg-warning-light text-warning-foreground px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      title="Container not reachable in this environment — dev only"
    >
      dev
    </span>
  );
}

export function AdminProducts() {
  const [products, setProducts] = useState<Product[]>([]);
  // slug -> container reachable in THIS env (prod/dev). Same source the
  // marketplace launcher consumes (/api/products/deployment-status).
  const [deployed, setDeployed] = useState<Record<string, boolean>>({});
  const [licenses, setLicenses] = useState<License[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);

  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);
  const [productForm, setProductForm] = useState(EMPTY_PRODUCT_FORM);
  // Per-row in-flight guard: the guide toggles write to the server, so the row
  // being mutated disables its own controls rather than letting a double-click
  // race two transitions against each other.
  const [busyId, setBusyId] = useState<string | null>(null);

  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [productLicenses, setProductLicenses] = useState<License[]>([]);
  const [loadingLicenses, setLoadingLicenses] = useState(false);

  const [showLicenseModal, setShowLicenseModal] = useState(false);
  const [licenseForm, setLicenseForm] = useState({ org_id: '', fim: '' });
  const [licenseFilter, setLicenseFilter] = useState<'all' | 'active' | 'revoked'>('all');

  async function fetchProducts() {
    try {
      // include_inactive=true (admin-only): see ALL rows so deactivated
      // products stay visible + reactivatable — same table the marketplace reads.
      const res = await api.get('/api/products?include_inactive=true');
      setProducts(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  async function fetchDeploymentStatus() {
    try {
      const res = await api.get('/api/products/deployment-status');
      setDeployed(res.deployed || {});
    } catch (err) {
      // Best-effort — a probe failure just means no live/dev badges.
      console.error('Error:', err);
    }
  }

  async function fetchOrgs() {
    try {
      const res = await api.get('/api/organizations');
      setOrgs(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    }
  }

  async function fetchAllLicenses() {
    try {
      const res = await api.get('/api/licenses/all');
      setLicenses(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    }
  }

  async function fetchProductLicenses(productId: string) {
    setLoadingLicenses(true);
    try {
      const res = await api.get(`/api/licenses/product/${productId}`);
      setProductLicenses(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoadingLicenses(false);
    }
  }

  useEffect(() => {
    Promise.all([fetchProducts(), fetchOrgs(), fetchAllLicenses(), fetchDeploymentStatus()]);
  }, []);

  function licenseCount(productId: string) {
    return licenses.filter(l => l.product_id === productId && l.status === 'active').length;
  }

  function openCreateProduct() {
    setEditingProductId(null);
    setProductForm(EMPTY_PRODUCT_FORM);
    setShowProductModal(true);
  }

  function openEditProduct(product: Product) {
    setEditingProductId(product.id);
    setProductForm({
      nome: product.nome,
      slug: product.slug,
      descricao: product.descricao || '',
      icone: product.icone || '',
      url_base: product.url_base,
      cor: product.cor || '#6366f1',
    });
    setShowProductModal(true);
  }

  async function handleProductSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (editingProductId) {
        // Send ONLY the three human-owned presentation fields. Previously the
        // whole form went up minus the slug, which meant an edit re-asserted
        // `icone` and `url_base` from whatever the form happened to hold —
        // quietly overwriting values the system owns.
        await api.patch(`/api/products/${editingProductId}`, {
          nome: productForm.nome,
          descricao: productForm.descricao,
          cor: productForm.cor,
        });
      } else {
        await api.post('/api/products', productForm);
      }
      setShowProductModal(false);
      await Promise.all([fetchProducts(), fetchAllLicenses()]);
      if (selectedProduct && editingProductId === selectedProduct.id) {
        const res = await api.get(`/api/products/${selectedProduct.id}`);
        setSelectedProduct(res.data);
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  /** Re-read the row after any guide mutation and keep the detail pane honest.
   *  The server is the authority on the resulting state — deactivating also
   *  demotes the scope, so echoing an optimistic local guess would show a
   *  combination the backend just refused to persist. */
  async function refreshAfterMutation(id: string) {
    await fetchProducts();
    if (selectedProduct?.id === id) {
      const res = await api.get(`/api/products/${id}`);
      setSelectedProduct(res.data);
    }
  }

  async function handleSetActivation(id: string, ativo: boolean) {
    setBusyId(id);
    try {
      await api.post(`/api/products/${id}/activation`, { ativo });
      await refreshAfterMutation(id);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleSetDeployScope(id: string, deploy_scope: DeployScope) {
    setBusyId(id);
    try {
      await api.post(`/api/products/${id}/deploy-scope`, { deploy_scope });
      await refreshAfterMutation(id);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleSetColor(id: string, cor: string) {
    setBusyId(id);
    try {
      await api.patch(`/api/products/${id}`, { cor });
      await refreshAfterMutation(id);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  }

  function selectProduct(product: Product) {
    setSelectedProduct(product);
    setLicenseFilter('all');
    fetchProductLicenses(product.id);
  }

  function openGrantLicense() {
    setLicenseForm({ org_id: '', fim: '' });
    setShowLicenseModal(true);
  }

  function setPresetDays(days: number) {
    const date = new Date();
    date.setDate(date.getDate() + days);
    setLicenseForm(prev => ({ ...prev, fim: date.toISOString().split('T')[0] }));
  }

  async function handleGrantLicense(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProduct) return;
    try {
      await api.post('/api/licenses', {
        org_id: licenseForm.org_id,
        product_id: selectedProduct.id,
        fim: licenseForm.fim || null,
      });
      setShowLicenseModal(false);
      await Promise.all([fetchProductLicenses(selectedProduct.id), fetchAllLicenses()]);
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleRevokeLicense(licenseId: string) {
    if (!confirm('Revogar acesso desta organizacao?')) return;
    try {
      await api.delete(`/api/licenses/${licenseId}`);
      if (selectedProduct) {
        await Promise.all([fetchProductLicenses(selectedProduct.id), fetchAllLicenses()]);
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  function formatTimeDistance(dateStr: string, future: boolean): string {
    const now = new Date();
    const target = new Date(dateStr);
    const diffMs = future ? target.getTime() - now.getTime() : now.getTime() - target.getTime();
    if (diffMs < 0 && future) return 'Expirada';
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (days >= 365) {
      const years = Math.floor(days / 365);
      const remainDays = days % 365;
      const months = Math.floor(remainDays / 30);
      return future
        ? `Faltam ${years}a${months > 0 ? ` ${months}m` : ''}`
        : `${years}a${months > 0 ? ` ${months}m` : ''} atras`;
    }
    if (days >= 30) {
      const months = Math.floor(days / 30);
      const remainDays = days % 30;
      return future
        ? `Faltam ${months}m${remainDays > 0 ? ` ${remainDays}d` : ''}`
        : `${months}m${remainDays > 0 ? ` ${remainDays}d` : ''} atras`;
    }
    if (days > 0) return future ? `Faltam ${days}d` : `${days}d atras`;
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    if (hours > 0) return future ? `Faltam ${hours}h` : `${hours}h atras`;
    return future ? 'Expira hoje' : 'Agora';
  }

  function licenseTimeInfo(lic: License): { text: string; className: string } {
    if (lic.status === 'revoked' && lic.fim) {
      return { text: formatTimeDistance(lic.fim, false), className: 'text-danger' };
    }
    if (lic.status === 'active' && lic.fim) {
      const daysLeft = Math.floor((new Date(lic.fim).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
      if (daysLeft < 0) return { text: 'Expirada', className: 'text-danger' };
      if (daysLeft <= 7) return { text: formatTimeDistance(lic.fim, true), className: 'text-warning' };
      if (daysLeft <= 30) return { text: formatTimeDistance(lic.fim, true), className: 'text-warning' };
      return { text: formatTimeDistance(lic.fim, true), className: 'text-success' };
    }
    return { text: '\u2014', className: 'text-muted-foreground' };
  }

  function renderProductModal() {
    if (!showProductModal) return null;
    return (
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowProductModal(false)}>
        <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-lg p-6" onClick={e => e.stopPropagation()}>
          <h2 className="text-lg font-semibold text-foreground mb-4">{editingProductId ? 'Editar Produto' : 'Novo Produto'}</h2>
          <form onSubmit={handleProductSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Nome</label>
              <input
                type="text"
                value={productForm.nome}
                onChange={e => setProductForm({ ...productForm, nome: e.target.value })}
                placeholder="Ex: ERP Imobiliario"
                required
                className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            {!editingProductId && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Slug</label>
                <input
                  type="text"
                  value={productForm.slug}
                  onChange={e => setProductForm({ ...productForm, slug: e.target.value })}
                  placeholder="Ex: erp-imobiliario"
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Descricao</label>
              <input
                type="text"
                value={productForm.descricao}
                onChange={e => setProductForm({ ...productForm, descricao: e.target.value })}
                placeholder="Descricao do produto"
                className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            {/* Icone / URL Base / Slug are SYSTEM-managed — the scaffolder and
                the url-roster tooling own them, and hand-editing them here is
                how the catalog drifts away from the fleet it describes. They
                stay on the API for those tools; they are deliberately absent
                from this modal on EDIT. Creation still needs them, since there
                is no scaffolder run behind a hand-made row. */}
            {!editingProductId && (
              <>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Icone</label>
                  <input
                    type="text"
                    value={productForm.icone}
                    onChange={e => setProductForm({ ...productForm, icone: e.target.value })}
                    placeholder="Ex: Box"
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">URL Base</label>
                  <input
                    type="text"
                    value={productForm.url_base}
                    onChange={e => setProductForm({ ...productForm, url_base: e.target.value })}
                    placeholder="Ex: http://localhost:8080"
                    required
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </>
            )}
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Cor</label>
              <div className="flex gap-3 items-center">
                <ColorPickerButton
                  cor={productForm.cor}
                  onPick={hex => setProductForm({ ...productForm, cor: hex })}
                />
                <input
                  type="text"
                  value={productForm.cor}
                  onChange={e => setProductForm({ ...productForm, cor: e.target.value })}
                  placeholder="#6366f1"
                  className="flex-1 h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                onClick={() => setShowProductModal(false)}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                {editingProductId ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  const orgsWithAccess = new Set(
    productLicenses.filter(l => l.status === 'active').map(l => l.org_id)
  );
  const availableOrgs = orgs.filter(o => !orgsWithAccess.has(o.id));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  // --- Detail View ---
  if (selectedProduct) {
    const filteredLicenses = productLicenses.filter(l => licenseFilter === 'all' || l.status === licenseFilter);

    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <div>
            <button
              className="border border-border bg-card text-foreground rounded-md px-3 py-1.5 text-sm hover:bg-accent transition-colors mb-2"
              onClick={() => setSelectedProduct(null)}
            >
              &larr; Voltar
            </button>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <ProductIcon name={selectedProduct.icone || 'Box'} color={selectedProduct.cor} size="sm" />
              {selectedProduct.nome}
            </h1>
            <p className="text-muted-foreground mt-1">{selectedProduct.slug}</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusToggle
              ativo={selectedProduct.ativo}
              deployScope={selectedProduct.deploy_scope}
              busy={busyId === selectedProduct.id}
              onToggle={next => handleSetActivation(selectedProduct.id, next)}
            />
            <DeployScopeToggle
              ativo={selectedProduct.ativo}
              deployScope={selectedProduct.deploy_scope}
              busy={busyId === selectedProduct.id}
              onToggle={next => handleSetDeployScope(selectedProduct.id, next)}
            />
            <EditIconButton onClick={() => openEditProduct(selectedProduct)} />
          </div>
        </div>

        {/* Product Info */}
        <div className="bg-card rounded-lg border border-border shadow-sm p-6 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div><strong className="text-foreground">Descricao:</strong> <span className="text-muted-foreground">{selectedProduct.descricao || 'Sem descricao'}</span></div>
            <div><strong className="text-foreground">URL Base:</strong> <span className="text-muted-foreground">{selectedProduct.url_base}</span></div>
            <div className="flex items-center gap-2">
              <strong className="text-foreground">Cor:</strong>
              <span
                className="inline-block w-3.5 h-3.5 rounded-full"
                style={{ backgroundColor: selectedProduct.cor }}
              />
              <span className="text-muted-foreground">{selectedProduct.cor}</span>
            </div>
            <div className="flex items-center gap-2">
              <strong className="text-foreground">Escopo de trabalho:</strong>
              <span className="text-muted-foreground">
                {!selectedProduct.ativo
                  ? 'Inativo — nao tocamos neste produto'
                  : selectedProduct.deploy_scope === 'live'
                    ? 'Ativo + LIVE — trabalhamos em producao'
                    : 'Ativo + DEV — trabalhamos apenas em dev'}
              </span>
            </div>
            {/* Runtime reachability is a SEPARATE fact from the working scope
                above: the scope is what we intend, this is what is actually
                up right now. Showing both makes a mismatch visible instead of
                letting one silently stand in for the other. */}
            <div className="flex items-center gap-2">
              <strong className="text-foreground">Container agora:</strong>
              <DeploymentBadge deployed={deployed[selectedProduct.slug]} />
              <span className="text-muted-foreground text-xs">
                {deployed[selectedProduct.slug] === undefined
                  ? 'verificando...'
                  : deployed[selectedProduct.slug]
                    ? 'alcancavel neste ambiente'
                    : 'nao alcancavel neste ambiente'}
              </span>
            </div>
          </div>
        </div>

        {/* License Management */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Licencas</h2>
            <p className="text-sm text-muted-foreground">
              {productLicenses.filter(l => l.status === 'active').length} ativas
              {productLicenses.filter(l => l.status === 'revoked').length > 0 &&
                ` \u00B7 ${productLicenses.filter(l => l.status === 'revoked').length} revogadas`}
            </p>
          </div>
          <button
            className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
            onClick={openGrantLicense}
          >
            + Conceder Acesso
          </button>
        </div>

        {/* License Filter */}
        <div className="flex gap-2 mb-4">
          {(['all', 'active', 'revoked'] as const).map(filter => (
            <button
              key={filter}
              className={`text-sm rounded-md px-3 py-1.5 transition-colors ${
                licenseFilter === filter
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-foreground hover:bg-accent'
              }`}
              onClick={() => setLicenseFilter(filter)}
            >
              {filter === 'all' ? 'Todas' : filter === 'active' ? 'Ativas' : 'Revogadas'}
            </button>
          ))}
        </div>

        {loadingLicenses ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            <p className="ml-3 text-muted-foreground">Carregando...</p>
          </div>
        ) : (
          <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organizacao</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Data de Concessao</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Validade</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Tempo</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredLicenses.map(lic => {
                  const timeInfo = licenseTimeInfo(lic);
                  return (
                    <tr key={lic.id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-foreground">
                        {lic.organizations?.nome || lic.org_id}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClasses(lic.status)}`}>
                          {lic.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{new Date(lic.created_at).toLocaleDateString('pt-BR')}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {lic.status === 'revoked' && lic.fim
                          ? `Revogada em ${new Date(lic.fim).toLocaleDateString('pt-BR')}`
                          : lic.fim
                            ? new Date(lic.fim).toLocaleDateString('pt-BR')
                            : 'Sem validade'}
                      </td>
                      <td className={`px-4 py-3 font-medium text-sm ${timeInfo.className}`}>
                        {timeInfo.text}
                      </td>
                      <td className="px-4 py-3">
                        {lic.status === 'active' && (
                          <button
                            className="text-xs bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                            onClick={() => handleRevokeLicense(lic.id)}
                          >
                            Revogar
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {filteredLicenses.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      {licenseFilter === 'all' ? 'Nenhuma organizacao com acesso' :
                       licenseFilter === 'active' ? 'Nenhuma licenca ativa' : 'Nenhuma licenca revogada'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Grant License Modal */}
        {showLicenseModal && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowLicenseModal(false)}>
            <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
              <h2 className="text-lg font-semibold text-foreground mb-2">Conceder Acesso</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Selecione a organizacao que recebera acesso a <strong>{selectedProduct.nome}</strong>.
              </p>
              <form onSubmit={handleGrantLicense} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Organizacao</label>
                  <select
                    value={licenseForm.org_id}
                    onChange={e => setLicenseForm(prev => ({ ...prev, org_id: e.target.value }))}
                    required
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  >
                    <option value="">Selecione...</option>
                    {availableOrgs.map(o => (
                      <option key={o.id} value={o.id}>{o.nome}</option>
                    ))}
                  </select>
                  {availableOrgs.length === 0 && (
                    <p className="text-xs text-warning mt-2">
                      Todas as organizacoes ja possuem acesso a este produto.
                    </p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Validade</label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {[
                      { label: '7 dias', days: 7 },
                      { label: '30 dias', days: 30 },
                      { label: '90 dias', days: 90 },
                      { label: '180 dias', days: 180 },
                      { label: '1 ano', days: 365 },
                    ].map(preset => (
                      <button
                        key={preset.days}
                        type="button"
                        className="text-xs border border-border bg-card text-foreground rounded-md px-2.5 py-1 hover:bg-accent transition-colors"
                        onClick={() => setPresetDays(preset.days)}
                      >
                        {preset.label}
                      </button>
                    ))}
                    {licenseForm.fim && (
                      <button
                        type="button"
                        className="text-xs border border-border bg-card text-warning rounded-md px-2.5 py-1 hover:bg-accent transition-colors"
                        onClick={() => setLicenseForm(prev => ({ ...prev, fim: '' }))}
                      >
                        Sem validade
                      </button>
                    )}
                  </div>
                  <input
                    type="date"
                    value={licenseForm.fim}
                    onChange={e => setLicenseForm(prev => ({ ...prev, fim: e.target.value }))}
                    min={new Date().toISOString().split('T')[0]}
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    {licenseForm.fim
                      ? `Expira em ${new Date(licenseForm.fim + 'T00:00:00').toLocaleDateString('pt-BR')}`
                      : 'Sem validade (acesso permanente)'}
                  </p>
                </div>
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                    onClick={() => setShowLicenseModal(false)}
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                    disabled={availableOrgs.length === 0}
                  >
                    Conceder
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {renderProductModal()}
      </div>
    );
  }

  // --- List View ---
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Produtos</h1>
          <p className="text-muted-foreground mt-1">{products.length} produtos cadastrados</p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={openCreateProduct}
        >
          + Novo Produto
        </button>
      </div>

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Slug</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">URL Base</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Cor</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Deploy</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Licencas</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          {/* Sectorized by working state — the SAME three buckets as
              /admin/product-control, from the same shared `bucketOf`. The
              catalog is no longer a flat alphabetical list: which bucket a
              product sits in is the thing you actually scan for, so the table
              groups by it and sorts by name within each group.

              One <tbody> per bucket keeps every column aligned across sections
              (a nested table per group would let column widths drift apart).
              Empty buckets render nothing rather than an empty header — a
              section that says "0" is noise on a page whose job is the list. */}
          {BUCKETS.map(bucket => {
            const rows = products
              .filter(p => bucketOf(p) === bucket.key)
              .sort((a, b) => a.nome.localeCompare(b.nome));
            if (rows.length === 0) return null;
            return (
              <tbody key={bucket.key} className="divide-y divide-border">
                <tr>
                  <td colSpan={8} className="px-4 py-2 border-y border-border bg-muted/40">
                    <div className="flex items-baseline gap-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${bucket.headerTone}`}
                      >
                        {bucket.title}
                      </span>
                      <span className="text-xs text-muted-foreground">({rows.length})</span>
                      <span className="text-xs text-muted-foreground">· {bucket.rule}</span>
                    </div>
                  </td>
                </tr>
                {rows.map(product => (
              <tr
                key={product.id}
                className="cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => selectProduct(product)}
              >
                <td className="px-4 py-3 font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <ProductIcon name={product.icone || 'Box'} color={product.cor} size="sm" />
                    {product.nome}
                  </div>
                </td>
                <td className="px-4 py-3 text-foreground">{product.slug}</td>
                <td className="px-4 py-3 text-muted-foreground">{product.url_base}</td>
                <td className="px-4 py-3">
                  <ColorPickerButton
                    cor={product.cor}
                    busy={busyId === product.id}
                    onPick={hex => handleSetColor(product.id, hex)}
                  />
                </td>
                <td className="px-4 py-3">
                  <StatusToggle
                    ativo={product.ativo}
                    deployScope={product.deploy_scope}
                    busy={busyId === product.id}
                    onToggle={next => handleSetActivation(product.id, next)}
                  />
                </td>
                <td className="px-4 py-3">
                  <DeployScopeToggle
                    ativo={product.ativo}
                    deployScope={product.deploy_scope}
                    busy={busyId === product.id}
                    onToggle={next => handleSetDeployScope(product.id, next)}
                  />
                </td>
                <td className="px-4 py-3 text-foreground">{licenseCount(product.id)}</td>
                <td className="px-4 py-3">
                  <div onClick={e => e.stopPropagation()}>
                    <EditIconButton onClick={() => openEditProduct(product)} />
                  </div>
                </td>
              </tr>
                ))}
              </tbody>
            );
          })}
          {products.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhum produto cadastrado. Crie o primeiro!
                </td>
              </tr>
            </tbody>
          )}
        </table>
      </div>

      {renderProductModal()}
    </div>
  );
}
