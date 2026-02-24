import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Plan {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  price_monthly: number;
  price_yearly: number;
  max_users: number;
  max_products: number;
  features: Record<string, any>;
  is_custom: boolean;
  is_active: boolean;
  created_at: string;
}

const EMPTY_FORM = {
  name: '',
  slug: '',
  description: '',
  price_monthly: 0,
  price_yearly: 0,
  max_users: -1,
  max_products: -1,
  is_custom: false,
};

export function AdminPlans() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState(EMPTY_FORM);

  async function fetchPlans() {
    try {
      const res = await api.get('/api/plans');
      setPlans(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchPlans(); }, []);

  function openCreate() {
    setEditingId(null);
    setFormData(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(plan: Plan) {
    setEditingId(plan.id);
    setFormData({
      name: plan.name,
      slug: plan.slug,
      description: plan.description || '',
      price_monthly: plan.price_monthly,
      price_yearly: plan.price_yearly,
      max_users: plan.max_users,
      max_products: plan.max_products,
      is_custom: plan.is_custom,
    });
    setShowModal(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (editingId) {
        const { slug, ...updateData } = formData;
        await api.patch(`/api/plans/${editingId}`, updateData);
      } else {
        await api.post('/api/plans', formData);
      }
      setShowModal(false);
      fetchPlans();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Desativar este plano?')) return;
    try {
      await api.delete(`/api/plans/${id}`);
      fetchPlans();
    } catch (err: any) {
      alert(err.message);
    }
  }

  function formatPrice(value: number) {
    return value === 0 ? 'Grátis' : `R$ ${value.toFixed(2)}`;
  }

  function formatLimit(value: number) {
    return value === -1 ? 'Ilimitado' : String(value);
  }

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Planos</h1>
          <p className="admin-page-subtitle">{plans.length} planos ativos</p>
        </div>
        <button className="btn-primary admin-btn" onClick={openCreate}>
          + Novo Plano
        </button>
      </div>

      <div className="admin-plans-grid">
        {plans.map(plan => (
          <div key={plan.id} className={`admin-plan-card ${plan.is_custom ? 'custom' : ''}`}>
            <div className="admin-plan-header">
              <h3>{plan.name}</h3>
              {plan.is_custom && <span className="badge badge-warning">Custom</span>}
            </div>
            <p className="admin-plan-description">{plan.description || 'Sem descrição'}</p>
            <div className="admin-plan-price">
              <span className="admin-plan-price-value">{formatPrice(plan.price_monthly)}</span>
              <span className="admin-plan-price-period">/mês</span>
            </div>
            <div className="admin-plan-limits">
              <div>Usuários: <strong>{formatLimit(plan.max_users)}</strong></div>
              <div>Produtos: <strong>{formatLimit(plan.max_products)}</strong></div>
            </div>
            <div className="admin-plan-actions">
              <button className="btn-sm" onClick={() => openEdit(plan)}>Editar</button>
              <button className="btn-sm btn-danger" onClick={() => handleDelete(plan.id)}>Desativar</button>
            </div>
          </div>
        ))}
        {plans.length === 0 && (
          <div className="admin-table-empty">Nenhum plano cadastrado. Crie o primeiro!</div>
        )}
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>{editingId ? 'Editar Plano' : 'Novo Plano'}</h2>
            <form onSubmit={handleSubmit}>
              <div className="field">
                <label>Nome</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Ex: Pro"
                  required
                />
              </div>
              {!editingId && (
                <div className="field">
                  <label>Slug</label>
                  <input
                    type="text"
                    value={formData.slug}
                    onChange={e => setFormData({ ...formData, slug: e.target.value })}
                    placeholder="Ex: pro"
                    required
                  />
                </div>
              )}
              <div className="field">
                <label>Descrição</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={e => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Descrição do plano"
                />
              </div>
              <div className="admin-form-row">
                <div className="field">
                  <label>Preço Mensal (R$)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formData.price_monthly}
                    onChange={e => setFormData({ ...formData, price_monthly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <div className="field">
                  <label>Preço Anual (R$)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formData.price_yearly}
                    onChange={e => setFormData({ ...formData, price_yearly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
              </div>
              <div className="admin-form-row">
                <div className="field">
                  <label>Max Usuários (-1 = ilimitado)</label>
                  <input
                    type="number"
                    min="-1"
                    value={formData.max_users}
                    onChange={e => setFormData({ ...formData, max_users: parseInt(e.target.value) || -1 })}
                  />
                </div>
                <div className="field">
                  <label>Max Produtos (-1 = ilimitado)</label>
                  <input
                    type="number"
                    min="-1"
                    value={formData.max_products}
                    onChange={e => setFormData({ ...formData, max_products: parseInt(e.target.value) || -1 })}
                  />
                </div>
              </div>
              <div className="field">
                <label className="admin-scope-option">
                  <input
                    type="checkbox"
                    checked={formData.is_custom}
                    onChange={e => setFormData({ ...formData, is_custom: e.target.checked })}
                  />
                  Plano customizado (per-org)
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn-primary admin-btn">{editingId ? 'Salvar' : 'Criar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
