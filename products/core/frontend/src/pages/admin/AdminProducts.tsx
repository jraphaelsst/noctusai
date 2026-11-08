import { useConfirm } from '@noctusai/lib/components';
import React, { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
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
import { useProductStateActions } from '../../hooks/useProductStateActions';
import { featuredOf, MAX_DESTAQUES, useProductSite } from '../../hooks/useProductSite';

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
  // Public-site controls (noctusai.com showcase), independent of ativo/deploy_scope.
  exibir_no_site?: boolean | null;
  destaque_no_site?: number | null;
  descricao_publica?: string | null;
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
  descricao_publica: '',
  // A product must ship a real icon (icone is required + non-empty server-side).
  // Default to the scaffolder default "Box"; pick any registered ProductIcon
  // name (see lib/product-icon.tsx ICONS) or an emoji.
  icone: 'Box',
  url_base: '',
  cor: '#6366f1',
};

/** Column widths, declared ONCE and reused by every bucket section.
 *
 *  Each section is its own <table>, and independent tables size their columns
 *  independently — without a shared fixed colgroup the sections would visibly
 *  misalign as soon as one bucket held a longer product name than another. */
function ProductCols() {
  return (
    <colgroup>
      <col className="w-[16%]" />
      <col className="w-[10%]" />
      <col className="w-[14%]" />
      <col className="w-[5%]" />
      <col className="w-[8%]" />
      <col className="w-[8%]" />
      <col className="w-[9%]" />
      <col className="w-[13%]" />
      <col className="w-[7%]" />
      <col className="w-[10%]" />
    </colgroup>
  );
}

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
  const [modalError, setModalError] = useState<string | null>(null);
  // Per-row in-flight guard for the colour picker (a PATCH, a different
  // concern from the activation/deploy-scope toggles below — see
  // `handleSetColor`, left as its own mutation rather than folded into the
  // shared hook).
  const [colorBusyId, setColorBusyId] = useState<string | null>(null);

  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [productLicenses, setProductLicenses] = useState<License[]>([]);
  const [loadingLicenses, setLoadingLicenses] = useState(false);

  const [showLicenseModal, setShowLicenseModal] = useState(false);
  const [licenseForm, setLicenseForm] = useState({ org_id: '', fim: '' });
  const [licenseFilter, setLicenseFilter] = useState<'all' | 'active' | 'revoked'>('all');

  const confirm = useConfirm();

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
    setModalError(null);
    setProductForm(EMPTY_PRODUCT_FORM);
    setShowProductModal(true);
  }

  function openEditProduct(product: Product) {
    setEditingProductId(product.id);
    setModalError(null);
    setProductForm({
      nome: product.nome,
      slug: product.slug,
      descricao: product.descricao || '',
      descricao_publica: product.descricao_publica || '',
      icone: product.icone || '',
      url_base: product.url_base,
      cor: product.cor || '#6366f1',
    });
    setShowProductModal(true);
  }

  async function handleProductSubmit(e: React.FormEvent) {
    e.preventDefault();
    setModalError(null);
    try {
      if (editingProductId) {
        // Send ONLY the three human-owned presentation fields. Previously the
        // whole form went up minus the slug, which meant an edit re-asserted
        // `icone` and `url_base` from whatever the form happened to hold —
        // quietly overwriting values the system owns.
        await api.patch(`/api/products/${editingProductId}`, {
          nome: productForm.nome,
          descricao: productForm.descricao,
          descricao_publica: productForm.descricao_publica,
          cor: productForm.cor,
        });
      } else {
        const { descricao_publica: _omit, ...createBody } = productForm;
        await api.post('/api/products', createBody);
      }
      setShowProductModal(false);
      await Promise.all([fetchProducts(), fetchAllLicenses()]);
      if (selectedProduct && editingProductId === selectedProduct.id) {
        const res = await api.get(`/api/products/${selectedProduct.id}`);
        setSelectedProduct(res.data);
      }
    } catch (err: any) {
      // A refusal is never silent: the server's pt-BR reason stays in the form.
      setModalError(err?.message || 'Não foi possível salvar o produto. Tente de novo.');
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

  const { busyId, setActivation: handleSetActivation, setDeployScope: handleSetDeployScope } =
    useProductStateActions(refreshAfterMutation);

  const site = useProductSite<Product>(products, up => setProducts(up), fetchProducts);

  async function handleToggleSite(product: Product) {
    const turningOff = !!product.exibir_no_site;
    if (turningOff && product.destaque_no_site != null) {
      const ok = await confirm({
        title: `Esconder ${product.nome} do site?`,
        description: `${product.nome} é o destaque nº ${product.destaque_no_site}. Esconder do site também o tira dos destaques; os que estão abaixo sobem uma posição.`,
        confirmLabel: 'Esconder e tirar dos destaques',
        cancelLabel: 'Manter no site',
        tone: 'danger',
      });
      if (!ok) return;
    }
    await site.setExibir(product, !turningOff);
  }

  async function handleSetColor(id: string, cor: string) {
    setColorBusyId(id);
    try {
      await api.patch(`/api/products/${id}`, { cor });
      await refreshAfterMutation(id);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setColorBusyId(null);
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
    if (!(await confirm({ title: 'Revogar acesso desta organização?', confirmLabel: 'Revogar', tone: 'danger' }))) return;
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
              <label htmlFor="prod-descricao" className="block text-sm font-medium text-foreground mb-1">Descricao</label>
              <input
                id="prod-descricao"
                type="text"
                value={productForm.descricao}
                onChange={e => setProductForm({ ...productForm, descricao: e.target.value })}
                placeholder="Descricao do produto"
                className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            {editingProductId && (
              <div>
                <label htmlFor="prod-descricao-publica" className="block text-sm font-medium text-foreground mb-1">
                  Descrição pública (aparece no site)
                </label>
                <textarea
                  id="prod-descricao-publica"
                  rows={3}
                  value={productForm.descricao_publica}
                  onChange={e => setProductForm({ ...productForm, descricao_publica: e.target.value })}
                  aria-describedby="prod-descricao-publica-hint"
                  placeholder="Uma ou duas frases para quem visita noctusai.com"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
                <p id="prod-descricao-publica-hint" className="text-xs text-muted-foreground mt-1">
                  Obrigatória para ligar “No site”. A descrição interna acima nunca vai para o site.
                </p>
              </div>
            )}
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
            {modalError && (
              <p role="alert" className="text-sm text-danger">{modalError}</p>
            )}
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
              onToggle={next => handleSetActivation(selectedProduct, next)}
            />
            <DeployScopeToggle
              ativo={selectedProduct.ativo}
              deployScope={selectedProduct.deploy_scope}
              busy={busyId === selectedProduct.id}
              onToggle={next => handleSetDeployScope(selectedProduct, next)}
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
  const featured = featuredOf([...products]);
  const bucketCounts = {
    prod: products.filter(p => bucketOf(p) === 'prod').length,
    dev: products.filter(p => bucketOf(p) === 'dev').length,
    ignore: products.filter(p => bucketOf(p) === 'ignore').length,
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Produtos</h1>
          {/* Working-state counts, carried over from the retired Controle
              page — the catalog total alone does not answer the question this
              page exists for ("what are we actually working on?"). */}
          <p className="text-muted-foreground mt-1">
            {products.length} produtos · {bucketCounts.prod} em producao ·{' '}
            {bucketCounts.dev} em dev · {bucketCounts.ignore} ignorados
          </p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={openCreateProduct}
        >
          + Novo Produto
        </button>
      </div>

      {/* Sectorized by working state — one bordered card per bucket, spaced
          apart, so the three groups read as distinct sets rather than one long
          list. Buckets come from the shared `bucketOf`/`BUCKETS`, so this page
          and the guide can never disagree about what "in production" means.

          `table-fixed` + a shared <ProductCols/> means every section resolves
          identical column widths — separate tables would otherwise size their
          columns independently and the sections would visibly misalign. */}
      <section className="bg-card rounded-lg border border-border shadow-sm p-4 mb-6" aria-labelledby="destaques-h">
        <h2 id="destaques-h" className="text-base font-semibold text-foreground">
          Destaques no site ({featured.length}/{MAX_DESTAQUES})
        </h2>
        <p className="text-xs text-muted-foreground mt-1">
          A seção de produtos de noctusai.com mostra estes, nesta ordem, e depois “Ver todos os produtos”. Escolha na coluna “Destaque no site”.
        </p>
        {featured.length === 0 ? (
          <p className="mt-3 text-sm text-foreground">
            Nenhum destaque escolhido.{' '}
            <span className="text-muted-foreground">
              Enquanto isso, o site mostra os 6 primeiros produtos visíveis: os disponíveis antes, depois em ordem alfabética.
            </span>
          </p>
        ) : (
          <ol className="mt-3 space-y-2">
            {featured.map((p, i) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2">
                <span className="text-xs font-semibold text-muted-foreground w-6">{i + 1}.</span>
                <span className="text-sm font-medium text-foreground flex-1 min-w-[8rem]">{p.nome}</span>
                <button
                  type="button"
                  className="border border-border rounded-md px-2 py-1 text-xs hover:bg-accent disabled:opacity-40"
                  aria-label={`Mover ${p.nome} para cima`}
                  disabled={i === 0 || site.busyId !== null}
                  onClick={() => site.move(p, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="border border-border rounded-md px-2 py-1 text-xs hover:bg-accent disabled:opacity-40"
                  aria-label={`Mover ${p.nome} para baixo`}
                  disabled={i === featured.length - 1 || site.busyId !== null}
                  onClick={() => site.move(p, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="text-xs underline text-muted-foreground hover:text-foreground disabled:opacity-50"
                  aria-label={`Remover ${p.nome} dos destaques`}
                  disabled={site.busyId !== null}
                  onClick={() => site.unfeature(p)}
                >
                  Remover
                </button>
              </li>
            ))}
          </ol>
        )}
        {site.error && site.error.id === null && (
          <p role="alert" className="mt-2 text-sm text-danger">{site.error.message}</p>
        )}
        <p role="status" className="sr-only">{site.status}</p>
      </section>

      <div className="space-y-6">
        {BUCKETS.map(bucket => {
          const rows = products
            .filter(p => bucketOf(p) === bucket.key)
            .sort((a, b) => a.nome.localeCompare(b.nome));
          if (rows.length === 0) return null;
          return (
            <section
              key={bucket.key}
              className={`bg-card rounded-lg border-2 ${bucket.tone} shadow-sm overflow-hidden`}
            >
              <header className="px-4 py-3 border-b border-border bg-muted/40">
                <div className="flex items-baseline gap-2">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${bucket.headerTone}`}
                  >
                    {bucket.title}
                  </span>
                  <span className="text-xs text-muted-foreground">({rows.length})</span>
                  <span className="text-xs text-muted-foreground">· {bucket.rule}</span>
                </div>
              </header>
              <div className="overflow-x-auto">
              <table className="w-full min-w-[1100px] text-sm table-fixed">
                <ProductCols />
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Nome</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Slug</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">URL Base</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Cor</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Deploy</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium text-muted-foreground">No site</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium text-muted-foreground">Destaque no site</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Licencas</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map(product => {
                    // Intent vs reality: this product is marked for prod but its
                    // container is not reachable here, or it is ignored yet still
                    // running. Neither is an error; both are worth seeing, and
                    // this warning is the one thing the retired Controle page
                    // showed that this table did not.
                    const reachable = deployed[product.slug];
                    const mismatch =
                      reachable !== undefined &&
                      ((bucket.key === 'prod' && !reachable) ||
                        (bucket.key === 'ignore' && reachable));
                    return (
                      <tr
                        key={product.id}
                        className="cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() => selectProduct(product)}
                      >
                        <td className="px-4 py-3 font-medium text-foreground">
                          <div className="flex items-center gap-2 min-w-0">
                            <ProductIcon name={product.icone || 'Box'} color={product.cor} size="sm" />
                            <span className="truncate">{product.nome}</span>
                            {mismatch && (
                              <span
                                className="inline-flex items-center gap-1 text-[10px] text-warning shrink-0"
                                title={
                                  bucket.key === 'prod'
                                    ? 'Marcado para producao, mas o container nao esta alcancavel neste ambiente'
                                    : 'Produto ignorado, mas o container ainda esta rodando'
                                }
                              >
                                <AlertTriangle className="w-3 h-3" />
                                container
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-foreground truncate">{product.slug}</td>
                        <td className="px-4 py-3 text-muted-foreground truncate">{product.url_base}</td>
                        <td className="px-4 py-3">
                          <ColorPickerButton
                            cor={product.cor}
                            busy={colorBusyId === product.id}
                            onPick={hex => handleSetColor(product.id, hex)}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <StatusToggle
                            ativo={product.ativo}
                            deployScope={product.deploy_scope}
                            busy={busyId === product.id}
                            onToggle={next => handleSetActivation(product, next)}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <DeployScopeToggle
                            ativo={product.ativo}
                            deployScope={product.deploy_scope}
                            busy={busyId === product.id}
                            onToggle={next => handleSetDeployScope(product, next)}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div onClick={e => e.stopPropagation()}>
                            <button
                              type="button"
                              role="switch"
                              aria-checked={!!product.exibir_no_site}
                              aria-label={`${product.nome} no site`}
                              disabled={site.busyId === product.id}
                              onClick={() => handleToggleSite(product)}
                              className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                                product.exibir_no_site
                                  ? 'bg-success/10 text-success hover:bg-success/20'
                                  : 'bg-muted text-muted-foreground hover:bg-accent'
                              }`}
                            >
                              {product.exibir_no_site ? 'Ligado' : 'Desligado'}
                            </button>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div onClick={e => e.stopPropagation()} className="space-y-1">
                            {product.destaque_no_site != null ? (
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold text-foreground">Nº {product.destaque_no_site}</span>
                                <button
                                  type="button"
                                  className="text-xs underline text-muted-foreground hover:text-foreground disabled:opacity-50"
                                  aria-label={`Tirar ${product.nome} dos destaques`}
                                  disabled={site.busyId === product.id}
                                  onClick={() => site.unfeature(product)}
                                >
                                  Tirar
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-2">
                                <span className="text-muted-foreground" aria-label="sem destaque">—</span>
                                <button
                                  type="button"
                                  className="text-xs border border-border bg-card rounded-md px-2 py-1 hover:bg-accent disabled:opacity-50"
                                  aria-label={`Destacar ${product.nome} no site`}
                                  aria-describedby={product.exibir_no_site ? undefined : `hint-destaque-${product.id}`}
                                  disabled={!product.exibir_no_site || site.busyId === product.id}
                                  onClick={() => site.feature(product)}
                                >
                                  Destacar
                                </button>
                              </div>
                            )}
                            {!product.exibir_no_site && product.destaque_no_site == null && (
                              <p id={`hint-destaque-${product.id}`} className="text-[11px] text-muted-foreground">
                                Ligue “No site” para poder destacar.
                              </p>
                            )}
                            {site.error?.id === product.id && (
                              <p role="alert" className="text-xs text-danger">{site.error.message}</p>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-foreground">{licenseCount(product.id)}</td>
                        <td className="px-4 py-3">
                          <div onClick={e => e.stopPropagation()}>
                            <EditIconButton onClick={() => openEditProduct(product)} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>
            </section>
          );
        })}
        {products.length === 0 && (
          <div className="bg-card rounded-lg border border-border shadow-sm px-4 py-8 text-center text-muted-foreground">
            Nenhum produto cadastrado. Crie o primeiro!
          </div>
        )}
      </div>

      {renderProductModal()}
    </div>
  );
}
