import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { Search, Pencil, Trash2, X } from 'lucide-react';
import { ORG_ROLE_LABELS, ASSIGNABLE_ROLES } from '@noctusai/lib';

interface User {
  id: string;
  nome: string;
  email: string;
  role: string;
  org_role: string;
  org_id: string;
  avatar_url?: string;
  created_at: string;
  organization?: { nome: string };
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
}

// Platform roles — `noctus_users.role` only ever holds these two. `manager` is
// an ORG role (see ORG_ROLE_LABELS); listing it here offered a value the API
// rejects with 422 and a filter that could never match a row.
const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  user: 'Usuario',
};

export function AdminUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [editUser, setEditUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ nome: '', role: '', org_role: '', org_id: '' });
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  // Org assign/revoke needs the full org list to pick from. `noctus_users.org_id`
  // is NOT NULL and there is no membership join table, so a user is in exactly
  // one org — "revoke" is a move to another org, not a detach.
  const [orgs, setOrgs] = useState<Organization[]>([]);

  // Create path = invite. A user account is created by inviting an e-mail
  // (POST /api/team/invite → the invitee accepts via /accept-invite and is
  // provisioned into the admin's org). There is no direct "insert a user row"
  // API — the canonical create for a person IS the invite flow, so the
  // page-scoped CRUD "Create" leg (KB § PATTERNS/product-internal-wiring.md §7)
  // is the invite modal below.
  const [showInvite, setShowInvite] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'member' });
  const [inviting, setInviting] = useState(false);

  async function fetchUsers() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      // `busca` is the parameter the API declares; the box sent `search`, which
      // FastAPI silently ignored — the search field was inert.
      if (search) params.set('busca', search);
      if (roleFilter) params.set('role', roleFilter);
      const res = await api.get(`/api/admin/users?${params}`);
      setUsers(res.data || []);
      setTotal(res.total || 0);
    } catch {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }

  async function fetchOrgs() {
    try {
      const res = await api.get('/api/organizations');
      setOrgs(res.data || []);
    } catch {
      setOrgs([]);
    }
  }

  useEffect(() => { fetchUsers(); }, [page, search, roleFilter]);
  useEffect(() => { fetchOrgs(); }, []);

  async function handleUpdate() {
    if (!editUser) return;
    setSaving(true);
    try {
      // `org_id` is UUID-typed server-side — omit it rather than sending '' if
      // the org list never loaded, so a failed org fetch can't 422 a name edit.
      const { org_id, ...rest } = editForm;
      const payload = org_id ? { ...rest, org_id } : rest;
      await api.patch(`/api/admin/users/${editUser.id}`, payload);
      setEditUser(null);
      fetchUsers();
    } catch (err: any) {
      alert(err.message || 'Erro ao atualizar');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await api.delete(`/api/admin/users/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchUsers();
    } catch (err: any) {
      alert(err.message || 'Erro ao excluir');
    }
  }

  async function handleInvite() {
    setInviting(true);
    try {
      await api.post('/api/team/invite', inviteForm);
      setShowInvite(false);
      setInviteForm({ email: '', role: 'member' });
      fetchUsers();
      alert('Convite enviado. O usuario sera adicionado ao aceitar.');
    } catch (err: any) {
      alert(err.message || 'Erro ao convidar');
    } finally {
      setInviting(false);
    }
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-foreground">Usuarios</h1>
          <p className="text-sm text-muted-foreground mt-1">{total} usuarios cadastrados</p>
        </div>
        <button
          onClick={() => { setInviteForm({ email: '', role: 'member' }); setShowInvite(true); }}
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          + Convidar Usuario
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Buscar por nome ou email..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full h-10 md:h-9 rounded-md border border-border bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
          className="h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">Todos os cargos</option>
          <option value="admin">Administrador</option>
          <option value="user">Usuário</option>
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <span className="ml-3 text-sm text-muted-foreground">Carregando...</span>
        </div>
      ) : users.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">Nenhum usuario encontrado</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Email</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Cargo</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Org</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Criado em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground text-right">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div>{u.nome}</div>
                    <div className="sm:hidden text-xs text-muted-foreground">{u.email}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden sm:table-cell">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      u.role === 'admin' ? 'bg-primary/10 text-primary' :
                      u.role === 'manager' ? 'bg-info/10 text-info' :
                      'bg-muted text-muted-foreground'
                    }`}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden md:table-cell truncate max-w-[200px]">
                    {u.organization?.nome || '—'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden lg:table-cell">
                    {new Date(u.created_at).toLocaleDateString('pt-BR')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => {
                          setEditUser(u);
                          setEditForm({
                            nome: u.nome,
                            role: u.role,
                            org_role: u.org_role,
                            org_id: u.org_id || '',
                          });
                        }}
                        className="h-8 w-8 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(u)}
                        className="h-8 w-8 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            Pagina {page} de {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="h-9 px-3 rounded-md border border-border bg-background text-sm hover:bg-accent disabled:opacity-50 transition-colors"
            >
              Anterior
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="h-9 px-3 rounded-md border border-border bg-background text-sm hover:bg-accent disabled:opacity-50 transition-colors"
            >
              Proximo
            </button>
          </div>
        </div>
      )}

      {/* Invite (Create) Modal */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowInvite(false)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">Convidar Usuario</h3>
              <button onClick={() => setShowInvite(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              O usuario sera criado ao aceitar o convite e entrara na sua organizacao.
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">E-mail</label>
                <input
                  type="email"
                  value={inviteForm.email}
                  onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                  placeholder="pessoa@empresa.com"
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Cargo Organizacao</label>
                <select
                  value={inviteForm.role}
                  onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm"
                >
                  {ASSIGNABLE_ROLES.map((r) => (
                    <option key={r} value={r}>{ORG_ROLE_LABELS[r]}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setShowInvite(false)}
                  className="flex-1 h-10 md:h-9 rounded-md border border-border bg-background text-sm hover:bg-accent transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleInvite}
                  disabled={inviting || !inviteForm.email}
                  className="flex-1 h-10 md:h-9 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {inviting ? 'Enviando...' : 'Enviar Convite'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editUser && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setEditUser(null)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">Editar Usuario</h3>
              <button onClick={() => setEditUser(null)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Nome</label>
                <input
                  value={editForm.nome}
                  onChange={(e) => setEditForm({ ...editForm, nome: e.target.value })}
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Cargo Plataforma</label>
                <select
                  value={editForm.role}
                  onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm"
                >
                  <option value="user">Usuário</option>
                  <option value="admin">Administrador</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Acesso ao painel administrativo. Nao concede acesso a dados de
                  produto — isso e definido pela organizacao.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Organizacao</label>
                <select
                  value={editForm.org_id}
                  onChange={(e) => setEditForm({ ...editForm, org_id: e.target.value })}
                  disabled={orgs.length === 0}
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm disabled:opacity-50"
                >
                  {orgs.length === 0 && <option value="">Carregando organizacoes...</option>}
                  {orgs.map((o) => (
                    <option key={o.id} value={o.id}>{o.nome}</option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Define quais dados o usuario enxerga em todos os produtos. Um
                  usuario pertence a exatamente uma organizacao — revogar e mover
                  para outra.
                </p>
                {editUser && editForm.org_id !== editUser.org_id && (
                  // The org also rides on the user's token, which is only
                  // re-minted at login. Without this warning the admin sees a
                  // success toast and the user sees an empty board.
                  <p className="text-xs text-warning mt-1" data-testid="org-relogin-warning">
                    O usuario precisa sair e entrar novamente para a mudanca
                    valer nos produtos.
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Cargo Organizacao</label>
                <select
                  value={editForm.org_role}
                  onChange={(e) => setEditForm({ ...editForm, org_role: e.target.value })}
                  className="w-full h-10 md:h-9 rounded-md border border-border bg-background px-3 text-sm"
                >
                  <option value="owner">{ORG_ROLE_LABELS.owner}</option>
                  {ASSIGNABLE_ROLES.map((r) => (
                    <option key={r} value={r}>{ORG_ROLE_LABELS[r]}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setEditUser(null)}
                  className="flex-1 h-10 md:h-9 rounded-md border border-border bg-background text-sm hover:bg-accent transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleUpdate}
                  disabled={saving}
                  className="flex-1 h-10 md:h-9 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {saving ? 'Salvando...' : 'Salvar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setDeleteTarget(null)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-foreground mb-2">Confirmar Exclusao</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Tem certeza que deseja excluir <strong>{deleteTarget.nome}</strong>? Esta acao nao pode ser desfeita.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="flex-1 h-10 md:h-9 rounded-md border border-border bg-background text-sm hover:bg-accent transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleDelete}
                className="flex-1 h-10 md:h-9 rounded-md bg-destructive text-destructive-foreground text-sm hover:bg-destructive/90 transition-colors"
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
