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

function deliveryStatusClasses(status: string): string {
  if (status === 'success') return 'bg-success/10 text-success';
  if (status === 'failed') return 'bg-danger/10 text-danger';
  return 'bg-warning/10 text-warning';
}

export function AdminWebhooks() {
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  const [formUrl, setFormUrl] = useState('');
  const [formEvents, setFormEvents] = useState<string[]>([]);
  const [formActive, setFormActive] = useState(true);

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
          <h1 className="text-2xl font-bold text-foreground">Webhooks</h1>
          <p className="text-muted-foreground mt-1">
            {endpoints.length} endpoint{endpoints.length !== 1 ? 's' : ''} configurado{endpoints.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          + Novo Webhook
        </button>
      </div>

      {/* Created secret alert */}
      {createdSecret && (
        <div className="mb-4 bg-warning/10 border border-warning/30 rounded-lg p-4 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-foreground">Webhook criado! Copie o signing secret agora, ele nao sera exibido novamente:</span>
          <code className="bg-muted px-3 py-1.5 rounded text-sm font-mono break-all">{createdSecret}</code>
          <button
            className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
            onClick={() => { navigator.clipboard.writeText(createdSecret); }}
          >
            Copiar
          </button>
          <button
            className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
            onClick={() => { setCreatedSecret(null); setShowCreate(false); resetForm(); }}
          >
            Fechar
          </button>
        </div>
      )}

      {/* Endpoints table */}
      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">URL</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Eventos</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Criado em</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {endpoints.map(ep => (
              <tr key={ep.id} className={`hover:bg-muted/50 transition-colors ${!ep.is_active ? 'opacity-50' : ''}`}>
                <td className="px-4 py-3 font-medium text-foreground max-w-xs truncate">{ep.url}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {(ep.events || []).length === 0 ? (
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">todos</span>
                    ) : (
                      (ep.events || []).map(ev => (
                        <span key={ev} className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">{ev}</span>
                      ))
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <button
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      ep.is_active ? 'bg-success' : 'bg-muted'
                    }`}
                    onClick={() => handleToggleActive(ep)}
                    title={ep.is_active ? 'Desativar' : 'Ativar'}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                        ep.is_active ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{new Date(ep.created_at).toLocaleDateString('pt-BR')}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                      onClick={() => fetchDeliveries(ep.id)}
                    >
                      Entregas
                    </button>
                    <button
                      className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                      onClick={() => openEdit(ep)}
                    >
                      Editar
                    </button>
                    <button
                      className="text-xs bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                      onClick={() => handleDelete(ep.id)}
                    >
                      Excluir
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {endpoints.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhum webhook configurado
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Deliveries view */}
      {viewDeliveriesId && (
        <div className="mt-6 bg-card rounded-lg border border-border shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/50">
            <h2 className="text-lg font-semibold text-foreground">Log de Entregas</h2>
            <button
              className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
              onClick={() => { setViewDeliveriesId(null); setDeliveries([]); }}
            >
              Fechar
            </button>
          </div>

          {deliveriesLoading ? (
            <div className="p-6 text-center text-muted-foreground">Carregando...</div>
          ) : deliveries.length === 0 ? (
            <div className="p-6 text-center text-muted-foreground">
              Nenhuma entrega registrada
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Evento</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">HTTP</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Tentativas</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Data</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Resposta</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {deliveries.map(d => (
                  <tr key={d.id} className="hover:bg-muted/50 transition-colors">
                    <td className="px-4 py-3">
                      <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{d.event_type}</code>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${deliveryStatusClasses(d.status)}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground">{d.response_status || '\u2014'}</td>
                    <td className="px-4 py-3 text-foreground">{d.attempts}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(d.created_at).toLocaleString('pt-BR')}</td>
                    <td className="px-4 py-3 text-muted-foreground max-w-xs truncate">
                      {d.response_body ? d.response_body.substring(0, 100) : '\u2014'}
                    </td>
                    <td className="px-4 py-3">
                      {d.status !== 'success' && (
                        <button
                          className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors disabled:opacity-50"
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
          )}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showCreate && !createdSecret && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => { setShowCreate(false); resetForm(); }}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-lg p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">{editingId ? 'Editar Webhook' : 'Novo Webhook'}</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">URL de destino</label>
                <input
                  type="url"
                  value={formUrl}
                  onChange={e => setFormUrl(e.target.value)}
                  placeholder="https://example.com/webhooks"
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">Eventos</label>
                <div className="grid grid-cols-2 gap-2">
                  {EVENT_OPTIONS.map(event => (
                    <label key={event} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formEvents.includes(event)}
                        onChange={() => toggleEvent(event)}
                        className="rounded border-border"
                      />
                      {event === '*' ? 'Todos (*)' : event}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formActive}
                    onChange={e => setFormActive(e.target.checked)}
                    className="rounded border-border"
                  />
                  Ativo
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                  onClick={() => { setShowCreate(false); resetForm(); }}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
                >
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
