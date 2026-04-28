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
    return value === 0 ? 'Gratis' : `R$ ${value.toFixed(2)}`;
  }

  function formatLimit(value: number) {
    return value === -1 ? 'Ilimitado' : String(value);
  }

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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Planos</h1>
          <p className="text-muted-foreground mt-1">{plans.length} planos ativos</p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          + Novo Plano
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {plans.map(plan => (
          <div key={plan.id} className={`bg-card rounded-lg border shadow-sm p-6 ${plan.is_custom ? 'border-warning' : 'border-border'}`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-semibold text-foreground">{plan.name}</h3>
              {plan.is_custom && (
                <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-warning/10 text-warning">
                  Custom
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground mb-4">{plan.description || 'Sem descricao'}</p>
            <div className="mb-4">
              <span className="text-2xl font-bold text-foreground">{formatPrice(plan.price_monthly)}</span>
              <span className="text-sm text-muted-foreground">/mes</span>
            </div>
            <div className="text-sm text-foreground space-y-1 mb-4">
              <div>Usuarios: <strong>{formatLimit(plan.max_users)}</strong></div>
              <div>Produtos: <strong>{formatLimit(plan.max_products)}</strong></div>
            </div>
            <div className="flex gap-2">
              <button
                className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                onClick={() => openEdit(plan)}
              >
                Editar
              </button>
              <button
                className="text-sm bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                onClick={() => handleDelete(plan.id)}
              >
                Desativar
              </button>
            </div>
          </div>
        ))}
        {plans.length === 0 && (
          <div className="col-span-full text-center py-8 text-muted-foreground">
            Nenhum plano cadastrado. Crie o primeiro!
          </div>
        )}
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-lg p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">{editingId ? 'Editar Plano' : 'Novo Plano'}</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Nome</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Ex: Pro"
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              {!editingId && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Slug</label>
                  <input
                    type="text"
                    value={formData.slug}
                    onChange={e => setFormData({ ...formData, slug: e.target.value })}
                    placeholder="Ex: pro"
                    required
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Descricao</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={e => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Descricao do plano"
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Preco Mensal (R$)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formData.price_monthly}
                    onChange={e => setFormData({ ...formData, price_monthly: parseFloat(e.target.value) || 0 })}
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Preco Anual (R$)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formData.price_yearly}
                    onChange={e => setFormData({ ...formData, price_yearly: parseFloat(e.target.value) || 0 })}
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Max Usuarios (-1 = ilimitado)</label>
                  <input
                    type="number"
                    min="-1"
                    value={formData.max_users}
                    onChange={e => setFormData({ ...formData, max_users: parseInt(e.target.value) || -1 })}
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Max Produtos (-1 = ilimitado)</label>
                  <input
                    type="number"
                    min="-1"
                    value={formData.max_products}
                    onChange={e => setFormData({ ...formData, max_products: parseInt(e.target.value) || -1 })}
                    className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_custom}
                    onChange={e => setFormData({ ...formData, is_custom: e.target.checked })}
                    className="rounded border-border"
                  />
                  Plano customizado (per-org)
                </label>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                  onClick={() => setShowModal(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  {editingId ? 'Salvar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
