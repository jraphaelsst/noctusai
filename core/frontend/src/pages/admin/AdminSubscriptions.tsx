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
  plans?: { id: string; name: string; slug: string };
  created_at: string;
}

interface Plan {
  id: string;
  name: string;
  slug: string;
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
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

  const statusClass = (s: string) => {
    if (s === 'active') return 'badge-active';
    if (s === 'canceled') return 'badge-danger';
    if (s === 'expired') return 'badge-danger';
    if (s === 'trial') return 'badge-warning';
    return '';
  };

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Assinaturas</h1>
          <p className="admin-page-subtitle">{subs.length} assinaturas</p>
        </div>
        <button className="btn-primary admin-btn" onClick={() => setShowModal(true)}>
          + Nova Assinatura
        </button>
      </div>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Organização</th>
              <th>Plano</th>
              <th>Status</th>
              <th>Início</th>
              <th>Expira</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {subs.map(sub => (
              <tr key={sub.id}>
                <td className="admin-table-primary">{sub.organizations?.nome || sub.org_id}</td>
                <td>{sub.plans?.name || sub.plan_id}</td>
                <td><span className={`badge ${statusClass(sub.status)}`}>{sub.status}</span></td>
                <td>{new Date(sub.started_at).toLocaleDateString('pt-BR')}</td>
                <td>{sub.expires_at ? new Date(sub.expires_at).toLocaleDateString('pt-BR') : 'Sem limite'}</td>
                <td>
                  {sub.status === 'active' && (
                    <button className="btn-sm btn-danger" onClick={() => handleCancel(sub.id)}>
                      Cancelar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {subs.length === 0 && (
              <tr><td colSpan={6} className="admin-table-empty">Nenhuma assinatura encontrada</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>Nova Assinatura</h2>
            <form onSubmit={handleCreate}>
              <div className="field">
                <label>Organização</label>
                <select
                  value={formData.org_id}
                  onChange={e => setFormData({ ...formData, org_id: e.target.value })}
                  required
                >
                  <option value="">Selecione...</option>
                  {orgs.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Plano</label>
                <select
                  value={formData.plan_id}
                  onChange={e => setFormData({ ...formData, plan_id: e.target.value })}
                  required
                >
                  <option value="">Selecione...</option>
                  {plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Status</label>
                <select
                  value={formData.status}
                  onChange={e => setFormData({ ...formData, status: e.target.value })}
                >
                  <option value="active">Ativo</option>
                  <option value="trial">Trial</option>
                </select>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn-primary admin-btn">Criar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
