import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Product {
  id: string;
  nome: string;
  slug: string;
  descricao: string | null;
  icone: string | null;
  url_base: string;
  cor: string;
  ativo: boolean;
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
  icone: '',
  url_base: '',
  cor: '#6366f1',
};

export function AdminProducts() {
  const [products, setProducts] = useState<Product[]>([]);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);

  // Product CRUD
  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);
  const [productForm, setProductForm] = useState(EMPTY_PRODUCT_FORM);

  // Product detail view
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [productLicenses, setProductLicenses] = useState<License[]>([]);
  const [loadingLicenses, setLoadingLicenses] = useState(false);

  // License grant modal
  const [showLicenseModal, setShowLicenseModal] = useState(false);
  const [licenseForm, setLicenseForm] = useState({ org_id: '', fim: '' });

  // License status filter: 'all' | 'active' | 'revoked'
  const [licenseFilter, setLicenseFilter] = useState<'all' | 'active' | 'revoked'>('all');

  async function fetchProducts() {
    try {
      const res = await api.get('/api/products');
      setProducts(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
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
    Promise.all([fetchProducts(), fetchOrgs(), fetchAllLicenses()]);
  }, []);

  // Count active licenses per product
  function licenseCount(productId: string) {
    return licenses.filter(l => l.product_id === productId && l.status === 'active').length;
  }

  // --- Product CRUD ---

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
        const { slug, ...updateData } = productForm;
        await api.patch(`/api/products/${editingProductId}`, updateData);
      } else {
        await api.post('/api/products', productForm);
      }
      setShowProductModal(false);
      await Promise.all([fetchProducts(), fetchAllLicenses()]);
      // Refresh detail view if editing the selected product
      if (selectedProduct && editingProductId === selectedProduct.id) {
        const res = await api.get(`/api/products/${selectedProduct.id}`);
        setSelectedProduct(res.data);
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleDeactivateProduct(id: string) {
    if (!confirm('Desativar este produto?')) return;
    try {
      await api.delete(`/api/products/${id}`);
      await fetchProducts();
      if (selectedProduct?.id === id) {
        setSelectedProduct(null);
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  function selectProduct(product: Product) {
    setSelectedProduct(product);
    setLicenseFilter('all');
    fetchProductLicenses(product.id);
  }

  // --- License Management ---

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
    if (!confirm('Revogar acesso desta organização?')) return;
    try {
      await api.delete(`/api/licenses/${licenseId}`);
      if (selectedProduct) {
        await Promise.all([fetchProductLicenses(selectedProduct.id), fetchAllLicenses()]);
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  const statusClass = (s: string) => {
    if (s === 'active') return 'badge-active';
    if (s === 'revoked') return 'badge-danger';
    return '';
  };

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
        : `${years}a${months > 0 ? ` ${months}m` : ''} atrás`;
    }
    if (days >= 30) {
      const months = Math.floor(days / 30);
      const remainDays = days % 30;
      return future
        ? `Faltam ${months}m${remainDays > 0 ? ` ${remainDays}d` : ''}`
        : `${months}m${remainDays > 0 ? ` ${remainDays}d` : ''} atrás`;
    }
    if (days > 0) return future ? `Faltam ${days}d` : `${days}d atrás`;
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    if (hours > 0) return future ? `Faltam ${hours}h` : `${hours}h atrás`;
    return future ? 'Expira hoje' : 'Agora';
  }

  function licenseTimeInfo(lic: License): { text: string; color: string } {
    if (lic.status === 'revoked' && lic.fim) {
      return { text: formatTimeDistance(lic.fim, false), color: '#ef4444' };
    }
    if (lic.status === 'active' && lic.fim) {
      const daysLeft = Math.floor((new Date(lic.fim).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
      if (daysLeft < 0) return { text: 'Expirada', color: '#ef4444' };
      if (daysLeft <= 7) return { text: formatTimeDistance(lic.fim, true), color: '#f59e0b' };
      if (daysLeft <= 30) return { text: formatTimeDistance(lic.fim, true), color: '#eab308' };
      return { text: formatTimeDistance(lic.fim, true), color: '#22c55e' };
    }
    return { text: '—', color: '#94a3b8' };
  }

  function renderProductModal() {
    if (!showProductModal) return null;
    return (
      <div className="modal-overlay" onClick={() => setShowProductModal(false)}>
        <div className="modal-content" onClick={e => e.stopPropagation()}>
          <h2>{editingProductId ? 'Editar Produto' : 'Novo Produto'}</h2>
          <form onSubmit={handleProductSubmit}>
            <div className="field">
              <label>Nome</label>
              <input
                type="text"
                value={productForm.nome}
                onChange={e => setProductForm({ ...productForm, nome: e.target.value })}
                placeholder="Ex: ERP Imobiliário"
                required
              />
            </div>
            {!editingProductId && (
              <div className="field">
                <label>Slug</label>
                <input
                  type="text"
                  value={productForm.slug}
                  onChange={e => setProductForm({ ...productForm, slug: e.target.value })}
                  placeholder="Ex: erp-imobiliario"
                  required
                />
              </div>
            )}
            <div className="field">
              <label>Descrição</label>
              <input
                type="text"
                value={productForm.descricao}
                onChange={e => setProductForm({ ...productForm, descricao: e.target.value })}
                placeholder="Descrição do produto"
              />
            </div>
            <div className="field">
              <label>Ícone (emoji)</label>
              <input
                type="text"
                value={productForm.icone}
                onChange={e => setProductForm({ ...productForm, icone: e.target.value })}
                placeholder="Ex: 🏠"
              />
            </div>
            <div className="field">
              <label>URL Base</label>
              <input
                type="text"
                value={productForm.url_base}
                onChange={e => setProductForm({ ...productForm, url_base: e.target.value })}
                placeholder="Ex: http://localhost:8080"
                required={!editingProductId}
              />
            </div>
            <div className="field">
              <label>Cor</label>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <input
                  type="color"
                  value={productForm.cor}
                  onChange={e => setProductForm({ ...productForm, cor: e.target.value })}
                  style={{ width: 40, height: 32, padding: 0, border: 'none', cursor: 'pointer' }}
                />
                <input
                  type="text"
                  value={productForm.cor}
                  onChange={e => setProductForm({ ...productForm, cor: e.target.value })}
                  placeholder="#6366f1"
                  style={{ flex: 1 }}
                />
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={() => setShowProductModal(false)}>
                Cancelar
              </button>
              <button type="submit" className="btn-primary admin-btn">
                {editingProductId ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // Orgs that already have an active license for this product
  const orgsWithAccess = new Set(
    productLicenses.filter(l => l.status === 'active').map(l => l.org_id)
  );
  const availableOrgs = orgs.filter(o => !orgsWithAccess.has(o.id));

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  // --- Detail View ---
  if (selectedProduct) {
    return (
      <div>
        <div className="admin-page-header">
          <div>
            <button
              className="btn-secondary"
              onClick={() => setSelectedProduct(null)}
              style={{ marginBottom: '0.5rem' }}
            >
              &larr; Voltar
            </button>
            <h1 className="admin-page-title">
              {selectedProduct.icone && <span style={{ marginRight: '0.5rem' }}>{selectedProduct.icone}</span>}
              {selectedProduct.nome}
            </h1>
            <p className="admin-page-subtitle">{selectedProduct.slug}</p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn-primary admin-btn" onClick={() => openEditProduct(selectedProduct)}>
              Editar
            </button>
            {selectedProduct.ativo && (
              <button className="btn-sm btn-danger" onClick={() => handleDeactivateProduct(selectedProduct.id)}>
                Desativar
              </button>
            )}
          </div>
        </div>

        {/* Product Info */}
        <div className="admin-table-wrapper" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div><strong>Descrição:</strong> {selectedProduct.descricao || 'Sem descrição'}</div>
            <div><strong>URL Base:</strong> {selectedProduct.url_base}</div>
            <div>
              <strong>Cor:</strong>{' '}
              <span
                style={{
                  display: 'inline-block',
                  width: 14,
                  height: 14,
                  borderRadius: '50%',
                  backgroundColor: selectedProduct.cor,
                  verticalAlign: 'middle',
                  marginRight: '0.25rem',
                }}
              />
              {selectedProduct.cor}
            </div>
            <div>
              <strong>Status:</strong>{' '}
              <span className={`badge ${selectedProduct.ativo ? 'badge-active' : 'badge-danger'}`}>
                {selectedProduct.ativo ? 'Ativo' : 'Inativo'}
              </span>
            </div>
          </div>
        </div>

        {/* License Management */}
        <div className="admin-page-header">
          <div>
            <h2 className="admin-page-title" style={{ fontSize: '1.25rem' }}>Licenças</h2>
            <p className="admin-page-subtitle">
              {productLicenses.filter(l => l.status === 'active').length} ativas
              {productLicenses.filter(l => l.status === 'revoked').length > 0 &&
                ` · ${productLicenses.filter(l => l.status === 'revoked').length} revogadas`}
            </p>
          </div>
          <button className="btn-primary admin-btn" onClick={openGrantLicense}>
            + Conceder Acesso
          </button>
        </div>

        {/* License Filter */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          {(['all', 'active', 'revoked'] as const).map(filter => (
            <button
              key={filter}
              className={licenseFilter === filter ? 'btn-primary admin-btn' : 'btn-secondary'}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.85rem' }}
              onClick={() => setLicenseFilter(filter)}
            >
              {filter === 'all' ? 'Todas' : filter === 'active' ? 'Ativas' : 'Revogadas'}
            </button>
          ))}
        </div>

        {loadingLicenses ? (
          <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>
        ) : (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Organização</th>
                  <th>Status</th>
                  <th>Data de Concessão</th>
                  <th>Validade</th>
                  <th>Tempo</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {productLicenses
                  .filter(l => licenseFilter === 'all' || l.status === licenseFilter)
                  .map(lic => (
                  <tr key={lic.id}>
                    <td className="admin-table-primary">
                      {lic.organizations?.nome || lic.org_id}
                    </td>
                    <td>
                      <span className={`badge ${statusClass(lic.status)}`}>{lic.status}</span>
                    </td>
                    <td>{new Date(lic.created_at).toLocaleDateString('pt-BR')}</td>
                    <td>
                      {lic.status === 'revoked' && lic.fim
                        ? `Revogada em ${new Date(lic.fim).toLocaleDateString('pt-BR')}`
                        : lic.fim
                          ? new Date(lic.fim).toLocaleDateString('pt-BR')
                          : 'Sem validade'}
                    </td>
                    <td style={{ color: licenseTimeInfo(lic).color, fontWeight: 500, fontSize: '0.85rem' }}>
                      {licenseTimeInfo(lic).text}
                    </td>
                    <td>
                      {lic.status === 'active' && (
                        <button className="btn-sm btn-danger" onClick={() => handleRevokeLicense(lic.id)}>
                          Revogar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {productLicenses.filter(l => licenseFilter === 'all' || l.status === licenseFilter).length === 0 && (
                  <tr><td colSpan={6} className="admin-table-empty">
                    {licenseFilter === 'all' ? 'Nenhuma organização com acesso' :
                     licenseFilter === 'active' ? 'Nenhuma licença ativa' : 'Nenhuma licença revogada'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Grant License Modal */}
        {showLicenseModal && (
          <div className="modal-overlay" onClick={() => setShowLicenseModal(false)}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
              <h2>Conceder Acesso</h2>
              <p style={{ color: '#94a3b8', marginBottom: '1rem' }}>
                Selecione a organização que receberá acesso a <strong>{selectedProduct.nome}</strong>.
              </p>
              <form onSubmit={handleGrantLicense}>
                <div className="field">
                  <label>Organização</label>
                  <select
                    value={licenseForm.org_id}
                    onChange={e => setLicenseForm(prev => ({ ...prev, org_id: e.target.value }))}
                    required
                  >
                    <option value="">Selecione...</option>
                    {availableOrgs.map(o => (
                      <option key={o.id} value={o.id}>{o.nome}</option>
                    ))}
                  </select>
                  {availableOrgs.length === 0 && (
                    <p style={{ color: '#f59e0b', fontSize: '0.85rem', marginTop: '0.5rem' }}>
                      Todas as organizações já possuem acesso a este produto.
                    </p>
                  )}
                </div>
                <div className="field">
                  <label>Validade</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
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
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
                        onClick={() => setPresetDays(preset.days)}
                      >
                        {preset.label}
                      </button>
                    ))}
                    {licenseForm.fim && (
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', color: '#f59e0b' }}
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
                  />
                  <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                    {licenseForm.fim
                      ? `Expira em ${new Date(licenseForm.fim + 'T00:00:00').toLocaleDateString('pt-BR')}`
                      : 'Sem validade (acesso permanente)'}
                  </p>
                </div>
                <div className="modal-actions">
                  <button type="button" className="btn-secondary" onClick={() => setShowLicenseModal(false)}>
                    Cancelar
                  </button>
                  <button type="submit" className="btn-primary admin-btn" disabled={availableOrgs.length === 0}>
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
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Produtos</h1>
          <p className="admin-page-subtitle">{products.length} produtos cadastrados</p>
        </div>
        <button className="btn-primary admin-btn" onClick={openCreateProduct}>
          + Novo Produto
        </button>
      </div>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Slug</th>
              <th>URL Base</th>
              <th>Cor</th>
              <th>Status</th>
              <th>Licenças</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {products.map(product => (
              <tr
                key={product.id}
                style={{ cursor: 'pointer' }}
                onClick={() => selectProduct(product)}
              >
                <td className="admin-table-primary">
                  {product.icone && <span style={{ marginRight: '0.5rem' }}>{product.icone}</span>}
                  {product.nome}
                </td>
                <td>{product.slug}</td>
                <td>{product.url_base}</td>
                <td>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 14,
                      height: 14,
                      borderRadius: '50%',
                      backgroundColor: product.cor,
                      verticalAlign: 'middle',
                    }}
                  />
                </td>
                <td>
                  <span className={`badge ${product.ativo ? 'badge-active' : 'badge-danger'}`}>
                    {product.ativo ? 'Ativo' : 'Inativo'}
                  </span>
                </td>
                <td>{licenseCount(product.id)}</td>
                <td>
                  <div style={{ display: 'flex', gap: '0.5rem' }} onClick={e => e.stopPropagation()}>
                    <button className="btn-sm" onClick={() => openEditProduct(product)}>
                      Editar
                    </button>
                    {product.ativo && (
                      <button className="btn-sm btn-danger" onClick={() => handleDeactivateProduct(product.id)}>
                        Desativar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {products.length === 0 && (
              <tr><td colSpan={7} className="admin-table-empty">Nenhum produto cadastrado. Crie o primeiro!</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {renderProductModal()}
    </div>
  );
}
