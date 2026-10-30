/**
 * Equipe — the org's members, invitations and (multi-org S5, owner D2–D5 2026-10-14) the
 * cross-org admin actions: pick WHICH org's team to manage (`?org_id=`, orgs the viewer manages
 * or any org for platform staff), move a member to another managed org (transfer | add, chosen
 * each time), and block/unblock a member per licensed product. Contract: roadmap
 * multi-org-membership-2026-10 § "S4b API contract". The server re-checks every call.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Button, Dialog, DialogBody, DialogFooter, DialogHeader, ErrorState, Field, FormError, Select, TableSkeleton,
} from '@noctusai/lib/design-system';

import { useAuth } from '../lib/auth-context';
import { CoreHeader } from '../components/layout/CoreHeader';
import {
  teamScopeOrgs, useAllOrgs, useCancelInvitation, useChangeMemberRole, useInviteMember, useRemoveMember,
  useTeamAccess, useTeamInvitations, useTeamMembers, useTeamRoles,
} from '../hooks/useTeam';
import type { TeamMember } from '../hooks/useTeam';
import { teamErrorMessage } from '../lib/team-errors';
import { MoveMemberDialog } from './team/MoveMemberDialog';
import { ProductAccessDialog } from './team/ProductAccessDialog';
import { removeMemberMessage } from './team/removeMessage';
import { roleName } from './team/roleName';

export function TeamManagement() {
  const { user, organization } = useAuth();
  const navigate = useNavigate();

  // --- which org's team (D2 scope) ---
  const accessQ = useTeamAccess();
  const staff = accessQ.data?.org_selection?.manage_any_org === true;
  const allOrgsQ = useAllOrgs(staff);
  const profileOrg = useMemo(() => {
    const id = organization?.id ?? user?.org_id;
    return id ? { id, nome: organization?.nome ?? 'Minha organização' } : null;
  }, [organization?.id, organization?.nome, user?.org_id]);
  const scopeOrgs = useMemo(
    () => teamScopeOrgs(accessQ.data, allOrgsQ.data, profileOrg),
    [accessQ.data, allOrgsQ.data, profileOrg],
  );
  const [orgId, setOrgId] = useState<string | null>(null);
  useEffect(() => {
    if (orgId === null && profileOrg) setOrgId(profileOrg.id);
  }, [orgId, profileOrg]);
  const currentOrg = scopeOrgs.find((o) => o.id === orgId) ?? null;
  const canManageOrg = currentOrg?.actorRole != null;
  const moveTargets = scopeOrgs.filter((o) => o.id !== orgId && o.actorRole != null);

  // --- lists ---
  const membersQ = useTeamMembers(orgId);
  const invitesQ = useTeamInvitations(orgId);
  const rolesQ = useTeamRoles();
  const members = membersQ.data ?? [];
  const invitations = invitesQ.data ?? [];
  const roles = rolesQ.data ?? [];
  const assignableRoles = roles.filter((r) => r.slug !== 'owner');
  // Row role selector: `owner` is offered to platform staff only (owner decision P1, 2026-10-14).
  const rowRoles = staff ? roles : assignableRoles;
  const showMembersSkeleton = (membersQ.isPending && !membersQ.data) || orgId === null;
  const membersRefreshing = membersQ.isFetching && !!membersQ.data;

  // --- actions ---
  const invite = useInviteMember(orgId);
  const remove = useRemoveMember(orgId);
  const changeRole = useChangeMemberRole(orgId);
  const cancelInvite = useCancelInvitation(orgId);

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<TeamMember | null>(null);
  const [moving, setMoving] = useState<TeamMember | null>(null);
  const [accessFor, setAccessFor] = useState<TeamMember | null>(null);

  const orgNome = currentOrg?.nome ?? profileOrg?.nome ?? 'organização';

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteError(null);
    try {
      await invite.mutateAsync({ email: inviteEmail, role: inviteRole });
      setShowInviteModal(false);
      setInviteEmail('');
      setInviteRole('member');
      toast.success('Convite enviado.');
    } catch (err) {
      setInviteError(teamErrorMessage(err, 'Erro ao enviar convite'));
    }
  }

  async function handleRemoveMember() {
    if (!confirmRemove) return;
    try {
      const result = await remove.mutateAsync(confirmRemove.id);
      toast.success(removeMemberMessage(
        confirmRemove.nome, orgNome, result,
        (id) => scopeOrgs.find((o) => o.id === id)?.nome,
      ));
      setConfirmRemove(null);
    } catch (err) {
      toast.error(teamErrorMessage(err, 'Erro ao remover membro'));
    }
  }

  async function handleRoleChange(memberId: string, role: string) {
    try {
      await changeRole.mutateAsync({ userId: memberId, role });
    } catch (err) {
      toast.error(teamErrorMessage(err, 'Erro ao alterar papel'));
    }
  }

  async function handleCancelInvite(inviteId: string) {
    try {
      await cancelInvite.mutateAsync(inviteId);
    } catch (err) {
      toast.error(teamErrorMessage(err, 'Erro ao cancelar convite'));
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <CoreHeader
        actions={
          <button
            className="h-9 rounded-md border border-border bg-background px-4 text-sm font-medium text-foreground hover:bg-muted transition-colors"
            onClick={() => navigate('/')}
          >
            Dashboard
          </button>
        }
      />

      <main className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-foreground">Equipe</h2>
            <p className="mt-1 text-sm text-muted-foreground" data-testid="team-count">
              {showMembersSkeleton
                ? 'Carregando membros…'
                : `${members.length} membro${members.length !== 1 ? 's' : ''} em ${orgNome}`}
              {membersRefreshing && <span className="ml-2 text-xs">Atualizando…</span>}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            {scopeOrgs.length > 1 && (
              <div className="w-full sm:w-64">
                <Field label="Organização">
                  <Select
                    data-testid="team-org-select"
                    value={orgId ?? ''}
                    onChange={(e) => setOrgId(e.target.value)}
                    className="h-10"
                  >
                    {scopeOrgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
                  </Select>
                </Field>
              </div>
            )}
            <Button type="button" className="h-10" onClick={() => setShowInviteModal(true)} disabled={!orgId}>
              Convidar
            </Button>
          </div>
        </div>

        {accessQ.isError && !accessQ.data && (
          <div role="status" className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Não foi possível carregar as outras organizações que você administra.
            <button type="button" className="underline" onClick={() => void accessQ.refetch()}>Tentar novamente</button>
          </div>
        )}

        {/* Members */}
        {showMembersSkeleton ? (
          <div data-testid="team-skeleton"><TableSkeleton rows={4} columns={5} /></div>
        ) : membersQ.isError && !membersQ.data ? (
          <div className="rounded-lg border border-border">
            <ErrorState message={teamErrorMessage(membersQ.error, 'Erro ao carregar dados da equipe')} />
            <div className="pb-6 text-center">
              <Button type="button" variant="outline" onClick={() => void membersQ.refetch()}>Tentar novamente</Button>
            </div>
          </div>
        ) : (
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
                {members.map((member) => {
                  const self = member.id === user?.id;
                  return (
                    <tr key={member.id} className="bg-card" data-testid={`member-row-${member.id}`}>
                      <td className="px-4 py-3 font-medium text-foreground">
                        {member.nome}
                        {self && (
                          <span className="ml-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                            Você
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-foreground">{member.email}</td>
                      <td className="px-4 py-3">
                        {member.org_role === 'owner' || self ? (
                          <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                            {roleName(member.org_role, roles)}
                          </span>
                        ) : (
                          <Select
                            aria-label={`Papel de ${member.nome}`}
                            className="h-8 w-auto"
                            value={member.org_role || 'member'}
                            onChange={(e) => void handleRoleChange(member.id, e.target.value)}
                          >
                            {rowRoles.map((role) => (
                              <option key={role.slug} value={role.slug}>{role.name}</option>
                            ))}
                          </Select>
                        )}
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {member.created_at ? new Date(member.created_at).toLocaleDateString('pt-BR') : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          {canManageOrg && (
                            <Button type="button" size="sm" variant="outline" onClick={() => setAccessFor(member)}>
                              Acessos
                            </Button>
                          )}
                          {canManageOrg && !self && moveTargets.length > 0 && (
                            <Button type="button" size="sm" variant="outline" onClick={() => setMoving(member)}>
                              Mover
                            </Button>
                          )}
                          {!self && member.org_role !== 'owner' && (
                            <button
                              className="rounded-md border border-destructive/40 bg-danger-light px-3 py-1 text-xs font-medium text-destructive hover:bg-danger-light"
                              onClick={() => setConfirmRemove(member)}
                            >
                              Remover
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
        )}

        {/* Pending Invitations */}
        <section className="mt-10">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-foreground">
            Convites pendentes
            {invitations.length > 0 && (
              <span className="inline-flex rounded-full bg-warning-light px-2 py-0.5 text-xs font-medium text-warning-foreground">
                {invitations.length}
              </span>
            )}
          </h3>

          {invitesQ.isPending && !invitesQ.data ? (
            <div data-testid="invites-skeleton"><TableSkeleton rows={2} columns={5} /></div>
          ) : invitesQ.isError && !invitesQ.data ? (
            <div className="flex flex-wrap items-center gap-3 text-sm text-destructive" role="alert">
              {teamErrorMessage(invitesQ.error, 'Erro ao carregar os convites')}
              <Button type="button" size="sm" variant="outline" onClick={() => void invitesQ.refetch()}>Tentar novamente</Button>
            </div>
          ) : invitations.length === 0 ? (
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
                  {invitations.map((inv) => (
                    <tr key={inv.id} className="bg-card">
                      <td className="px-4 py-3 font-medium text-foreground">{inv.email}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                          {roleName(inv.role, roles)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString('pt-BR') : '—'}
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {inv.created_at ? new Date(inv.created_at).toLocaleDateString('pt-BR') : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="rounded-md border border-destructive/40 bg-danger-light px-3 py-1 text-xs font-medium text-destructive hover:bg-danger-light disabled:opacity-50"
                          disabled={cancelInvite.isPending}
                          onClick={() => void handleCancelInvite(inv.id)}
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

      {/* Invite */}
      <Dialog open={showInviteModal} onClose={() => setShowInviteModal(false)} title="Convidar membro">
        <form onSubmit={handleInvite}>
          <DialogHeader>
            <h2 className="text-base font-semibold text-foreground">Convidar membro para {orgNome}</h2>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <FormError message={inviteError} />
            <Field label="E-mail" required>
              <input
                type="email"
                placeholder="colaborador@empresa.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </Field>
            <Field label="Papel">
              <Select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="h-10">
                {assignableRoles.map((role) => (
                  <option key={role.slug} value={role.slug}>{role.name}</option>
                ))}
              </Select>
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowInviteModal(false)}>Cancelar</Button>
            <Button type="submit" disabled={invite.isPending || !inviteEmail}>
              {invite.isPending ? 'Enviando...' : 'Enviar convite'}
            </Button>
          </DialogFooter>
        </form>
      </Dialog>

      {/* Remove */}
      <Dialog open={!!confirmRemove} onClose={() => setConfirmRemove(null)} title="Remover membro">
        <DialogHeader>
          <h2 className="text-base font-semibold text-foreground">Remover membro</h2>
        </DialogHeader>
        <DialogBody className="space-y-3 text-sm text-muted-foreground">
          <p>
            Remover <strong className="text-foreground">{confirmRemove?.nome}</strong> ({confirmRemove?.email}) de{' '}
            <strong className="text-foreground">{orgNome}</strong>? A pessoa sai desta organização em TODOS os
            produtos NoctusAI, não apenas aqui.
          </p>
          <p data-testid="remove-keeps-profile">
            A conta da pessoa não é apagada: ela continua nas outras organizações de que participa. Se esta for a
            única, ela passa a ter uma organização pessoal própria, com o histórico preservado.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setConfirmRemove(null)}>Cancelar</Button>
          <Button type="button" variant="destructive" onClick={() => void handleRemoveMember()} disabled={remove.isPending}>
            {remove.isPending ? 'Removendo...' : 'Confirmar remoção'}
          </Button>
        </DialogFooter>
      </Dialog>

      {moving && currentOrg && (
        <MoveMemberDialog
          member={moving}
          sourceOrg={currentOrg}
          targets={moveTargets}
          roles={roles}
          staff={staff}
          onClose={() => setMoving(null)}
        />
      )}
      {accessFor && currentOrg && (
        <ProductAccessDialog member={accessFor} org={currentOrg} onClose={() => setAccessFor(null)} />
      )}
    </div>
  );
}
