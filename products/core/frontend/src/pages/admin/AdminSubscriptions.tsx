import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Subscription {
  id: string;
  org_id: string;
  plan_id: string;
  status: string;
  started_at: string;
  expires_at: string | null;
  organizations?: { id: string; nome: string };
  plans?: { id: string; nome: string; slug: string };
  created_at: string;
}

interface Plan {
  id: string;
  nome: string;
  slug: string;
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
}

function statusBadgeClasses(s: string): string {
  if (s === 'active') return 'bg-success/10 text-success';
  if (s === 'canceled' || s === 'expired') return 'bg-danger/10 text-danger';
  if (s === 'trial') return 'bg-warning/10 text-warning';
  return 'bg-muted text-muted-foreground';
}

export function AdminSubscriptions() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({ org_id: '', plan_id: '', status: 'active' });

  async function fetchData() {
    try {
      const [subsRes, plansRes, orgsRes] = await Promise.all([
        api.get('/api/subscriptions'),
        api.get('/api/plans'),
        api.get('/api/organizations'),
      ]);
      setSubs(subsRes.data || []);
      setPlans(plansRes.data || []);
      setOrgs(orgsRes.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchData(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.post('/api/subscriptions', formData);
      setShowModal(false);
      setFormData({ org_id: '', plan_id: '', status: 'active' });
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleCancel(id: string) {
    if (!confirm('Cancelar esta assinatura?')) return;
    try {
      await api.delete(`/api/subscriptions/${id}`);
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
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
          <h1 className="text-2xl font-bold text-foreground">Assinaturas</h1>
          <p className="text-muted-foreground mt-1">{subs.length} assinaturas</p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={() => setShowModal(true)}
        >
          + Nova Assinatura
        </button>
      </div>

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organizacao</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Plano</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Inicio</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Expira</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {subs.map(sub => (
              <tr key={sub.id} className="hover:bg-muted/50 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">{sub.organizations?.nome || sub.org_id}</td>
                <td className="px-4 py-3 text-foreground">{sub.plans?.nome || sub.plan_id}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClasses(sub.status)}`}>
                    {sub.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{new Date(sub.started_at).toLocaleDateString('pt-BR')}</td>
                <td className="px-4 py-3 text-muted-foreground">{sub.expires_at ? new Date(sub.expires_at).toLocaleDateString('pt-BR') : 'Sem limite'}</td>
                <td className="px-4 py-3">
                  {sub.status === 'active' && (
                    <button
                      className="text-xs bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                      onClick={() => handleCancel(sub.id)}
                    >
                      Cancelar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {subs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhuma assinatura encontrada
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">Nova Assinatura</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Organizacao</label>
                <select
                  value={formData.org_id}
                  onChange={e => setFormData({ ...formData, org_id: e.target.value })}
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="">Selecione...</option>
                  {orgs.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Plano</label>
                <select
                  value={formData.plan_id}
                  onChange={e => setFormData({ ...formData, plan_id: e.target.value })}
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="">Selecione...</option>
                  {plans.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                <select
                  value={formData.status}
                  onChange={e => setFormData({ ...formData, status: e.target.value })}
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="active">Ativo</option>
                  <option value="trial">Trial</option>
                </select>
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
                  Criar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
