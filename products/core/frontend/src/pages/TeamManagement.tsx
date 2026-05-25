import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { NotificationBell } from '../components/NotificationBell';
import { Header, useTheme } from "@noctusai/lib/design-system";
import { ORG_ROLE_LABELS } from "@noctusai/lib";

interface Member {
  id: string;
  nome: string;
  email: string;
  org_role: string;
  created_at: string;
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  invited_by: string;
  expires_at: string;
  created_at: string;
}

interface Role {
  id: string;
  name: string;
  slug: string;
  permissions: string[];
  is_system: boolean;
}

export function TeamManagement() {
  const { user, organization, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Invite modal state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState('');

  // Confirm remove modal state
  const [confirmRemove, setConfirmRemove] = useState<Member | null>(null);
  const [removing, setRemoving] = useState(false);

  async function fetchData() {
    // product-internal-wiring §4: each fetch degrades independently via its own
    // `.catch()` — a failure in one (members vs invitations vs roles) must not
    // zero the others. The members fetch is the primary surface; its failure
    // sets the page-level error, the auxiliary lists fall back to empty.
    setError('');
    const [membersRes, invitesRes, rolesRes] = await Promise.all([
      api.get('/api/team').catch((err: any) => {
        setError(err?.message || 'Erro ao carregar dados da equipe');
        return { data: [] };
      }),
      api.get('/api/team/invitations').catch(() => ({ data: [] })),
      api.get('/api/roles').catch(() => ({ data: [] })),
    ]);
    setMembers(membersRes.data || []);
    setInvitations(invitesRes.data || []);
    setRoles(rolesRes.data || []);
    setLoading(false);
  }

  useEffect(() => {
    fetchData();
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteError('');

    try {
      await api.post('/api/team/invite', { email: inviteEmail, role: inviteRole });
      setShowInviteModal(false);
      setInviteEmail('');
      setInviteRole('member');
      fetchData();
    } catch (err: any) {
      setInviteError(err.message || 'Erro ao enviar convite');
    } finally {
      setInviting(false);
    }
  }

  async function handleRemoveMember() {
    if (!confirmRemove) return;
    setRemoving(true);

    try {
      await api.delete(`/api/team/${confirmRemove.id}`);
      setConfirmRemove(null);
      fetchData();
    } catch (err: any) {
      alert(err.message || 'Erro ao remover membro');
    } finally {
      setRemoving(false);
    }
  }

  async function handleRoleChange(memberId: string, newRole: string) {
    try {
      await api.patch(`/api/team/${memberId}/role`, { role: newRole });
      fetchData();
    } catch (err: any) {
      alert(err.message || 'Erro ao alterar papel');
    }
  }

  async function handleCancelInvite(inviteId: string) {
    try {
      await api.delete(`/api/team/invitations/${inviteId}`);
      fetchData();
    } catch (err: any) {
      alert(err.message || 'Erro ao cancelar convite');
    }
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  // Filter roles for assignment (non-owner roles)
  const assignableRoles = roles.filter(r => r.slug !== 'owner');

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
        <p className="mt-4 text-muted-foreground">Carregando equipe...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <Header
        user={{ name: user?.nome || '', email: user?.email || '', role: isAdmin ? 'Administrador' : 'Membro' }}
        onLogout={handleLogout}
        theme={theme}
        onThemeToggle={toggleTheme}
        actions={
          <div className="flex items-center gap-2">
            <button
              className="h-9 rounded-md border border-border bg-background px-4 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              onClick={() => navigate('/')}
            >
              Dashboard
            </button>
            <NotificationBell />
          </div>
        }
      />

      {/* Main */}
      <main className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Equipe</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {members.length} membro{members.length !== 1 ? 's' : ''} na organização
            </p>
          </div>
          <button
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => setShowInviteModal(true)}
          >
            Convidar
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
        )}

        {/* Members Table */}
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Entrou em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {members.map(member => (
                <tr key={member.id} className="bg-card">
                  <td className="px-4 py-3 font-medium text-foreground">
                    {member.nome}
                    {member.id === user?.id && (
                      <span className="ml-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                        Você
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground">{member.email}</td>
                  <td className="px-4 py-3">
                    {member.org_role === 'owner' || member.id === user?.id ? (
                      <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                        {getRoleName(member.org_role, roles)}
                      </span>
                    ) : (
                      <select
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                        value={member.org_role || 'member'}
                        onChange={e => handleRoleChange(member.id, e.target.value)}
                      >
                        {assignableRoles.map(role => (
                          <option key={role.slug} value={role.slug}>
                            {role.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground">
                    {member.created_at
                      ? new Date(member.created_at).toLocaleDateString('pt-BR')
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {member.id !== user?.id && member.org_role !== 'owner' && (
                      <button
                        className="rounded-md border border-red-200 bg-red-50 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
                        onClick={() => setConfirmRemove(member)}
                      >
                        Remover
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {members.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum membro encontrado
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pending Invitations */}
        <section className="mt-10">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-foreground">
            Convites pendentes
            {invitations.length > 0 && (
              <span className="inline-flex rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                {invitations.length}
              </span>
            )}
          </h3>

          {invitations.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum convite pendente</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Expira em</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Enviado em</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {invitations.map(inv => (
                    <tr key={inv.id} className="bg-card">
                      <td className="px-4 py-3 font-medium text-foreground">{inv.email}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                          {getRoleName(inv.role, roles)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {inv.expires_at
                          ? new Date(inv.expires_at).toLocaleDateString('pt-BR')
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {inv.created_at
                          ? new Date(inv.created_at).toLocaleDateString('pt-BR')
                          : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="rounded-md border border-red-200 bg-red-50 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
                          onClick={() => handleCancelInvite(inv.id)}
                        >
                          Cancelar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {/* Invite Modal */}
      {showInviteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowInviteModal(false)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={e => e.stopPropagation()}
          >
            <h2 className="mb-4 text-lg font-semibold text-foreground">Convidar membro</h2>
            <form onSubmit={handleInvite}>
              {inviteError && (
                <div className="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
                  {inviteError}
                </div>
              )}
              <div className="mb-4">
                <label className="mb-1 block text-sm font-medium text-foreground">E-mail</label>
                <input
                  type="email"
                  placeholder="colaborador@empresa.com"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  required
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="mb-6">
                <label className="mb-1 block text-sm font-medium text-foreground">Papel</label>
                <select
                  value={inviteRole}
                  onChange={e => setInviteRole(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  {assignableRoles.map(role => (
                    <option key={role.slug} value={role.slug}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
                  onClick={() => setShowInviteModal(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={inviting || !inviteEmail}
                >
                  {inviting ? 'Enviando...' : 'Enviar convite'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Confirm Remove Modal */}
      {confirmRemove && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmRemove(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={e => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover membro</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover <strong className="text-foreground">{confirmRemove.nome}</strong> ({confirmRemove.email}) da organização? Esta ação não pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted"
                onClick={() => setConfirmRemove(null)}
              >
                Cancelar
              </button>
              <button
                className="rounded-md bg-red-600 px-6 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleRemoveMember}
                disabled={removing}
              >
                {removing ? 'Removendo...' : 'Confirmar remoção'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Map a role slug to a human-readable name using the roles list. */
function getRoleName(slug: string, roles: Role[]): string {
  const role = roles.find(r => r.slug === slug);
  if (role) return role.name;

  return ORG_ROLE_LABELS[slug as keyof typeof ORG_ROLE_LABELS] || slug;
}
