import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';

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
  const { user, organization, logout } = useAuth();
  const navigate = useNavigate();

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
    try {
      const [membersRes, invitesRes, rolesRes] = await Promise.all([
        api.get('/api/team'),
        api.get('/api/team/invitations').catch(() => ({ data: [] })),
        api.get('/api/roles').catch(() => ({ data: [] })),
      ]);
      setMembers(membersRes.data || []);
      setInvitations(invitesRes.data || []);
      setRoles(rolesRes.data || []);
    } catch (err: any) {
      setError(err.message || 'Erro ao carregar dados da equipe');
    } finally {
      setLoading(false);
    }
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
      <div className="loading-screen">
        <div className="spinner" />
        <p>Carregando equipe...</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <span className="logo-icon">⚡</span>
          <h1>NoctusAI</h1>
        </div>
        <div className="header-right">
          <button className="btn-sm" onClick={() => navigate('/')}>
            Dashboard
          </button>
          <div className="user-info">
            <span className="user-name">{user?.nome}</span>
            <span className="org-name">{organization?.nome}</span>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Sair</button>
        </div>
      </header>

      {/* Main */}
      <main className="team-page">
        <div className="team-page-header">
          <div>
            <h2 className="team-page-title">Equipe</h2>
            <p className="team-page-subtitle">
              {members.length} membro{members.length !== 1 ? 's' : ''} na organização
            </p>
          </div>
          <button
            className="btn-primary team-invite-btn"
            onClick={() => setShowInviteModal(true)}
          >
            Convidar
          </button>
        </div>

        {error && <div className="error">{error}</div>}

        {/* Members Table */}
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Papel</th>
                <th>Entrou em</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {members.map(member => (
                <tr key={member.id}>
                  <td className="admin-table-primary">
                    {member.nome}
                    {member.id === user?.id && (
                      <span className="badge badge-sm badge-inline">Você</span>
                    )}
                  </td>
                  <td>{member.email}</td>
                  <td>
                    {member.org_role === 'owner' || member.id === user?.id ? (
                      <span className="badge">
                        {getRoleName(member.org_role, roles)}
                      </span>
                    ) : (
                      <select
                        className="role-select"
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
                  <td>
                    {member.created_at
                      ? new Date(member.created_at).toLocaleDateString('pt-BR')
                      : '—'}
                  </td>
                  <td>
                    {member.id !== user?.id && member.org_role !== 'owner' && (
                      <button
                        className="btn-sm btn-danger"
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
                  <td colSpan={5} className="admin-table-empty">
                    Nenhum membro encontrado
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pending Invitations */}
        <section className="pending-invitations">
          <h3 className="pending-invitations-title">
            Convites pendentes
            {invitations.length > 0 && (
              <span className="badge badge-sm badge-warning badge-inline">
                {invitations.length}
              </span>
            )}
          </h3>

          {invitations.length === 0 ? (
            <p className="pending-invitations-empty">Nenhum convite pendente</p>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>E-mail</th>
                    <th>Papel</th>
                    <th>Expira em</th>
                    <th>Enviado em</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {invitations.map(inv => (
                    <tr key={inv.id}>
                      <td className="admin-table-primary">{inv.email}</td>
                      <td>
                        <span className="badge">{getRoleName(inv.role, roles)}</span>
                      </td>
                      <td>
                        {inv.expires_at
                          ? new Date(inv.expires_at).toLocaleDateString('pt-BR')
                          : '—'}
                      </td>
                      <td>
                        {inv.created_at
                          ? new Date(inv.created_at).toLocaleDateString('pt-BR')
                          : '—'}
                      </td>
                      <td>
                        <button
                          className="btn-sm btn-danger"
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
        <div className="modal-overlay" onClick={() => setShowInviteModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>Convidar membro</h2>
            <form onSubmit={handleInvite}>
              {inviteError && <div className="error">{inviteError}</div>}
              <div className="field">
                <label>E-mail</label>
                <input
                  type="email"
                  placeholder="colaborador@empresa.com"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label>Papel</label>
                <select
                  value={inviteRole}
                  onChange={e => setInviteRole(e.target.value)}
                >
                  {assignableRoles.map(role => (
                    <option key={role.slug} value={role.slug}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowInviteModal(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={inviting || !inviteEmail}
                  style={{ width: 'auto', padding: '10px 24px' }}
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
        <div className="modal-overlay" onClick={() => setConfirmRemove(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>Remover membro</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
              Tem certeza que deseja remover <strong>{confirmRemove.nome}</strong> ({confirmRemove.email}) da organização? Esta ação não pode ser desfeita.
            </p>
            <div className="modal-actions">
              <button
                className="btn-secondary"
                onClick={() => setConfirmRemove(null)}
              >
                Cancelar
              </button>
              <button
                className="btn-primary"
                onClick={handleRemoveMember}
                disabled={removing}
                style={{
                  width: 'auto',
                  padding: '10px 24px',
                  background: 'var(--danger)',
                }}
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

  // Fallback display names
  const fallback: Record<string, string> = {
    owner: 'Proprietário',
    admin: 'Administrador',
    member: 'Membro',
    viewer: 'Visualizador',
  };
  return fallback[slug] || slug;
}
