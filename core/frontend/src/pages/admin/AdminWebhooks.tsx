import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface WebhookEndpoint {
  id: string;
  org_id: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
  signing_secret?: string;
}

interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  response_status: number | null;
  response_body: string | null;
  attempts: number;
  status: string;
  created_at: string;
}

const EVENT_OPTIONS = [
  'subscription.created',
  'subscription.updated',
  'subscription.canceled',
  'license.granted',
  'license.revoked',
  'user.invited',
  'user.removed',
  'api_key.created',
  'api_key.revoked',
  '*',
];

export function AdminWebhooks() {
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  // Form state
  const [formUrl, setFormUrl] = useState('');
  const [formEvents, setFormEvents] = useState<string[]>([]);
  const [formActive, setFormActive] = useState(true);

  // Deliveries view
  const [viewDeliveriesId, setViewDeliveriesId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  async function fetchEndpoints() {
    try {
      const res = await api.get('/api/webhooks');
      setEndpoints(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchEndpoints(); }, []);

  function resetForm() {
    setFormUrl('');
    setFormEvents([]);
    setFormActive(true);
    setEditingId(null);
    setCreatedSecret(null);
  }

  function openCreate() {
    resetForm();
    setShowCreate(true);
  }

  function openEdit(endpoint: WebhookEndpoint) {
    setFormUrl(endpoint.url);
    setFormEvents(endpoint.events || []);
    setFormActive(endpoint.is_active);
    setEditingId(endpoint.id);
    setCreatedSecret(null);
    setShowCreate(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    try {
      if (editingId) {
        await api.patch(`/api/webhooks/${editingId}`, {
          url: formUrl,
          events: formEvents,
          is_active: formActive,
        });
      } else {
        const res = await api.post('/api/webhooks', {
          url: formUrl,
          events: formEvents,
          is_active: formActive,
        });
        if (res.data?.signing_secret) {
          setCreatedSecret(res.data.signing_secret);
        }
      }
      fetchEndpoints();
      if (editingId) {
        setShowCreate(false);
        resetForm();
      }
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Excluir este webhook endpoint?')) return;
    try {
      await api.delete(`/api/webhooks/${id}`);
      fetchEndpoints();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleToggleActive(endpoint: WebhookEndpoint) {
    try {
      await api.patch(`/api/webhooks/${endpoint.id}`, {
        is_active: !endpoint.is_active,
      });
      fetchEndpoints();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function fetchDeliveries(endpointId: string) {
    setViewDeliveriesId(endpointId);
    setDeliveriesLoading(true);
    try {
      const res = await api.get(`/api/webhooks/${endpointId}/deliveries?page=1&page_size=50`);
      setDeliveries(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setDeliveriesLoading(false);
    }
  }

  async function handleRetryDelivery(delivery: WebhookDelivery) {
    setRetryingId(delivery.id);
    try {
      await api.post(`/api/webhooks/deliveries/${delivery.id}/retry`);
      // Refresh deliveries list
      if (viewDeliveriesId) {
        await fetchDeliveries(viewDeliveriesId);
      }
    } catch (err: any) {
      alert(err.message || 'Erro ao reenviar webhook');
    } finally {
      setRetryingId(null);
    }
  }

  function toggleEvent(event: string) {
    setFormEvents(prev =>
      prev.includes(event) ? prev.filter(e => e !== event) : [...prev, event]
    );
  }

  function statusBadge(status: string) {
    if (status === 'success') return 'badge-active';
    if (status === 'failed') return 'badge-danger';
    return 'badge-warning';
  }

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Webhooks</h1>
          <p className="admin-page-subtitle">
            {endpoints.length} endpoint{endpoints.length !== 1 ? 's' : ''} configurado{endpoints.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button className="btn-primary admin-btn" onClick={openCreate}>
          + Novo Webhook
        </button>
      </div>

      {/* Created secret alert */}
      {createdSecret && (
        <div className="admin-alert admin-alert-warning">
          <strong>Webhook criado!</strong> Copie o signing secret agora, ele não será exibido novamente:
          <code className="admin-key-display">{createdSecret}</code>
          <button className="btn-sm" onClick={() => { navigator.clipboard.writeText(createdSecret); }}>
            Copiar
          </button>
          <button className="btn-sm" onClick={() => { setCreatedSecret(null); setShowCreate(false); resetForm(); }}>
            Fechar
          </button>
        </div>
      )}

      {/* Endpoints table */}
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>URL</th>
              <th>Eventos</th>
              <th>Status</th>
              <th>Criado em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {endpoints.map(ep => (
              <tr key={ep.id} className={!ep.is_active ? 'admin-row-inactive' : ''}>
                <td className="admin-table-primary webhook-url-cell">{ep.url}</td>
                <td>
                  <div className="webhook-events-list">
                    {(ep.events || []).length === 0 ? (
                      <span className="badge badge-sm">todos</span>
                    ) : (
                      (ep.events || []).map(ev => (
                        <span key={ev} className="badge badge-sm">{ev}</span>
                      ))
                    )}
                  </div>
                </td>
                <td>
                  <button
                    className={`webhook-toggle ${ep.is_active ? 'webhook-toggle-active' : ''}`}
                    onClick={() => handleToggleActive(ep)}
                    title={ep.is_active ? 'Desativar' : 'Ativar'}
                  >
                    <span className="webhook-toggle-slider" />
                  </button>
                </td>
                <td>{new Date(ep.created_at).toLocaleDateString('pt-BR')}</td>
                <td>
                  <div className="webhook-actions">
                    <button className="btn-sm" onClick={() => fetchDeliveries(ep.id)}>
                      Entregas
                    </button>
                    <button className="btn-sm" onClick={() => openEdit(ep)}>
                      Editar
                    </button>
                    <button className="btn-sm btn-danger" onClick={() => handleDelete(ep.id)}>
                      Excluir
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {endpoints.length === 0 && (
              <tr><td colSpan={5} className="admin-table-empty">Nenhum webhook configurado</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Deliveries view */}
      {viewDeliveriesId && (
        <div className="webhook-deliveries-section">
          <div className="webhook-deliveries-header">
            <h2>Log de Entregas</h2>
            <button className="btn-sm" onClick={() => { setViewDeliveriesId(null); setDeliveries([]); }}>
              Fechar
            </button>
          </div>

          {deliveriesLoading ? (
            <div className="notification-empty">Carregando...</div>
          ) : deliveries.length === 0 ? (
            <div className="notification-empty" style={{ padding: '24px', textAlign: 'center' as const }}>
              Nenhuma entrega registrada
            </div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Evento</th>
                    <th>Status</th>
                    <th>HTTP</th>
                    <th>Tentativas</th>
                    <th>Data</th>
                    <th>Resposta</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {deliveries.map(d => (
                    <tr key={d.id}>
                      <td><code>{d.event_type}</code></td>
                      <td>
                        <span className={`badge badge-sm ${statusBadge(d.status)}`}>
                          {d.status}
                        </span>
                      </td>
                      <td>{d.response_status || '—'}</td>
                      <td>{d.attempts}</td>
                      <td>{new Date(d.created_at).toLocaleString('pt-BR')}</td>
                      <td className="webhook-response-cell">
                        {d.response_body ? d.response_body.substring(0, 100) : '—'}
                      </td>
                      <td>
                        {d.status !== 'success' && (
                          <button
                            className="btn-sm"
                            onClick={() => handleRetryDelivery(d)}
                            disabled={retryingId === d.id}
                          >
                            {retryingId === d.id ? 'Reenviando...' : 'Reenviar'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showCreate && !createdSecret && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); resetForm(); }}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>{editingId ? 'Editar Webhook' : 'Novo Webhook'}</h2>
            <form onSubmit={handleSubmit}>
              <div className="field">
                <label>URL de destino</label>
                <input
                  type="url"
                  value={formUrl}
                  onChange={e => setFormUrl(e.target.value)}
                  placeholder="https://example.com/webhooks"
                  required
                />
              </div>

              <div className="field">
                <label>Eventos</label>
                <div className="webhook-events-grid">
                  {EVENT_OPTIONS.map(event => (
                    <label key={event} className="admin-scope-option">
                      <input
                        type="checkbox"
                        checked={formEvents.includes(event)}
                        onChange={() => toggleEvent(event)}
                      />
                      {event === '*' ? 'Todos (*)' : event}
                    </label>
                  ))}
                </div>
              </div>

              <div className="field">
                <label className="admin-scope-option">
                  <input
                    type="checkbox"
                    checked={formActive}
                    onChange={e => setFormActive(e.target.checked)}
                  />
                  Ativo
                </label>
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => { setShowCreate(false); resetForm(); }}>
                  Cancelar
                </button>
                <button type="submit" className="btn-primary admin-btn">
                  {editingId ? 'Salvar' : 'Criar Webhook'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
