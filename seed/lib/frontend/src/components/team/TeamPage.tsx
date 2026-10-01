/**
 * `<TeamPage/>` — the canonical product **Equipe** page over the seed
 * `/api/team` router (see `createTeamHooks` for the wire contract).
 *
 * Renders, in four honest states (loading / empty / error / success):
 *   - the product's STAFF roster (nome · e-mail · papel · entrou em) — the
 *     backend already filters it by the product's `TeamPolicy`;
 *   - for owner/admin/manager (`MANAGE_TEAM_ROLES`, the backend invite gate):
 *     an invite dialog whose role options come from `GET /api/team/policy`
 *     (`invitable_roles` + `labels`) — never hard-coded, so a product extra
 *     such as community's `moderador` just appears; a non-admin inviter never
 *     sees `ELEVATED_GRANT_ROLES` (the backend `_GRANT_REQUIRES` would 403);
 *   - for owner/admin (`ADMIN_ROLES`, the backend invitations gate): pending
 *     invitations with cancel.
 *
 * There is deliberately NO "Remover" action: `noctus_users` is one platform
 * profile per person, so removal from the org is a NoctusAI Core action
 * (`DELETE /api/team/{id}` answers 409 `TEAM_REMOVE_CORE_ONLY`). The page
 * points there instead, via the seed `env.CORE_URL` resolver.
 *
 * The role gate here is UX only — the backend resolves the caller's role from
 * `noctus_users` and enforces 403 regardless.
 *
 * Usage (the whole product page):
 * ```tsx
 * import { api, useAuthStore } from '@noctusai/seed/infra';
 * import { TeamPage } from '@noctusai/lib';
 *
 * export default function Equipe() {
 *   return <TeamPage api={api} user={useAuthStore((s) => s.user)} />;
 * }
 * ```
 *
 * Requires a `QueryClientProvider` in the host tree (`createProductApp`
 * provides one).
 */
import * as React from 'react';
import { AlertCircle, ExternalLink, Loader2, Mail, RefreshCw, UserPlus, Users } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { Input } from '../../design-system/ui/Input';
import { TableSkeleton } from '../../design-system/ui/TableSkeleton';
import { env } from '../../env';
import { ADMIN_ROLES, ELEVATED_GRANT_ROLES, MANAGE_TEAM_ROLES, ORG_ROLE_LABELS } from '../../roles';
import { resolveSSOContext } from '../../sso';
import { createTeamHooks } from './createTeamHooks';
import type { TeamApi, TeamHooks, TeamMember } from './createTeamHooks';

/** The slice of the auth user the page reads (the seed auth store's `user`). */
export interface TeamPageUser {
  id?: string;
  user_metadata?: Record<string, any> | null;
}

export interface TeamPageProps {
  /** The product's authenticated api client (`@noctusai/seed/infra` `api`). */
  api: TeamApi;
  /** The signed-in user (`useAuthStore((s) => s.user)`). `null` ⇒ auth not
   *  ready yet: nothing is fetched until it is. */
  user: TeamPageUser | null | undefined;
  /** Override BOTH gates — invite and admin-only invitations (default:
   *  derived from the SSO context, mirroring the backend's two gates). */
  canManage?: boolean;
  /** Core frontend base URL for the removal note. Default `env.CORE_URL`. */
  coreUrl?: string;
  /** Pre-built hooks (tests / a custom basePath). Default `createTeamHooks(api)`. */
  hooks?: TeamHooks;
  /** Named seam: product-owned sections rendered below the roster + invitations
   *  (e.g. orbity's page-visibility panel). The organ never fetches for them. */
  children?: React.ReactNode;
}

const SELECT_CLASS =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('pt-BR');
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-8 text-center"
    >
      <AlertCircle className="h-6 w-6 text-destructive" />
      <p className="text-sm text-foreground">{message}</p>
      <Button type="button" size="sm" variant="outline" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Tentar novamente
      </Button>
    </div>
  );
}

function InviteDialog({
  open,
  onClose,
  hooks,
  labelFor,
  canGrantElevated,
}: {
  open: boolean;
  onClose: () => void;
  hooks: TeamHooks;
  labelFor: (role: string | null | undefined) => string;
  canGrantElevated: boolean;
}) {
  const policy = hooks.useTeamPolicy(open);
  const invite = hooks.useInviteMember();
  const roles = React.useMemo(
    () =>
      (policy.data?.invitable_roles ?? []).filter(
        (r) => canGrantElevated || !(ELEVATED_GRANT_ROLES as string[]).includes(r),
      ),
    [policy.data, canGrantElevated],
  );
  const [email, setEmail] = React.useState('');
  const [role, setRole] = React.useState('');

  // Default the select to the first invitable role once the policy arrives.
  React.useEffect(() => {
    if (!role && roles.length > 0) setRole(roles[0]);
  }, [role, roles]);

  function close() {
    setEmail('');
    setRole('');
    onClose();
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !role) return;
    invite.mutate({ email: email.trim(), role }, { onSuccess: close });
  }

  return (
    <Dialog open={open} onClose={close} title="Convidar membro">
      <form onSubmit={submit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Convidar membro</h2>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div>
            <label htmlFor="team-invite-email" className="mb-1 block text-sm font-medium text-foreground">
              E-mail
            </label>
            <Input
              id="team-invite-email"
              type="email"
              placeholder="colaborador@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="team-invite-role" className="mb-1 block text-sm font-medium text-foreground">
              Papel
            </label>
            {policy.showSkeleton ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-busy="true">
                <Loader2 className="h-4 w-4 animate-spin" />
                Carregando papéis...
              </p>
            ) : policy.isError ? (
              <p role="alert" className="text-sm text-destructive">
                Não foi possível carregar os papéis disponíveis.{' '}
                <button type="button" className="underline" onClick={() => void policy.refetch()}>
                  Tentar novamente
                </button>
              </p>
            ) : roles.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Este produto não permite convites.
              </p>
            ) : (
              <select
                id="team-invite-role"
                className={SELECT_CLASS}
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                {roles.map((r) => (
                  <option key={r} value={r}>
                    {policy.data?.labels[r] ?? labelFor(r)}
                  </option>
                ))}
              </select>
            )}
          </div>
        </DialogBody>
        <DialogFooter className="gap-3">
          <Button type="button" variant="outline" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={invite.isPending || !email || !role}>
            {invite.isPending ? (
              <>
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                Enviando...
              </>
            ) : (
              'Enviar convite'
            )}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function PendingInvitations({
  hooks,
  labelFor,
}: {
  hooks: TeamHooks;
  labelFor: (role: string | null | undefined) => string;
}) {
  const invitations = hooks.useTeamInvitations(true);
  const cancel = hooks.useCancelInvitation();
  const rows = invitations.data ?? [];

  return (
    <section aria-label="Convites pendentes">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-foreground">
        <Mail className="h-5 w-5 text-muted-foreground" />
        Convites pendentes
        {rows.length > 0 && <Badge variant="muted">{rows.length}</Badge>}
        {invitations.isRefreshing && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />
        )}
      </h2>
      {invitations.showSkeleton ? (
        <div aria-busy="true">
          <TableSkeleton rows={2} columns={4} />
        </div>
      ) : invitations.isError && !invitations.data ? (
        <ErrorState
          message="Erro ao carregar os convites pendentes."
          onRetry={() => void invitations.refetch()}
        />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum convite pendente.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                <th className="hidden px-4 py-3 font-medium text-muted-foreground sm:table-cell">Expira em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((inv) => (
                <tr key={inv.id} className="bg-card">
                  <td className="px-4 py-3 font-medium text-foreground">{inv.email}</td>
                  <td className="px-4 py-3">
                    <Badge variant="muted">{labelFor(inv.role)}</Badge>
                  </td>
                  <td className="hidden px-4 py-3 text-foreground sm:table-cell">
                    {formatDate(inv.expires_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={cancel.isPending && cancel.variables === inv.id}
                      onClick={() => cancel.mutate(inv.id)}
                    >
                      Cancelar
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function TeamPage({ api, user, canManage, coreUrl, hooks: hooksProp, children }: TeamPageProps) {
  const hooks = React.useMemo(() => hooksProp ?? createTeamHooks(api), [hooksProp, api]);
  const ready = user != null;

  const sso = resolveSSOContext(user?.user_metadata ?? undefined);
  // Two gates, mirroring the backend: invite = MANAGE_TEAM_ROLES; listing /
  // cancelling invitations = ADMIN_ROLES. `isProductAdmin` covers the
  // platform operator (backend `_PLATFORM_ADMIN`).
  const isAdmin = canManage ?? (sso.isProductAdmin || (ADMIN_ROLES as string[]).includes(sso.org.role));
  const canInvite = canManage ?? (isAdmin || (MANAGE_TEAM_ROLES as string[]).includes(sso.org.role));

  const roster = hooks.useTeamRoster(ready);
  // The policy carries the labels for product-extra roles (e.g. `moderador`).
  const policy = hooks.useTeamPolicy(ready);
  const [inviteOpen, setInviteOpen] = React.useState(false);

  const labels = policy.data?.labels;
  const labelFor = React.useCallback(
    (role: string | null | undefined): string => {
      if (!role) return '—';
      return labels?.[role] ?? (ORG_ROLE_LABELS as Record<string, string>)[role] ?? role;
    },
    [labels],
  );

  const members: TeamMember[] = roster.data ?? [];
  const coreTeamUrl = `${(coreUrl ?? env.CORE_URL ?? '').replace(/\/$/, '')}/team`;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
              Equipe
              {roster.isRefreshing && (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />
              )}
            </h1>
            {roster.data && (
              <p className="text-sm text-muted-foreground">
                {members.length} membro{members.length !== 1 ? 's' : ''} na equipe deste produto
              </p>
            )}
          </div>
        </div>
        {canInvite && (
          <Button type="button" variant="primary" onClick={() => setInviteOpen(true)}>
            <UserPlus className="mr-1.5 h-4 w-4" />
            Convidar
          </Button>
        )}
      </div>

      {/* Roster */}
      {!ready || roster.showSkeleton ? (
        <div aria-busy="true" aria-label="Carregando equipe">
          <TableSkeleton rows={4} columns={4} />
        </div>
      ) : roster.isError && !roster.data ? (
        <ErrorState message="Erro ao carregar a equipe." onRetry={() => void roster.refetch()} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="hidden px-4 py-3 font-medium text-muted-foreground sm:table-cell">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                <th className="hidden px-4 py-3 font-medium text-muted-foreground md:table-cell">Entrou em</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {members.map((m) => (
                <tr key={m.id} className="bg-card">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="flex flex-col">
                      <span>
                        {m.nome || '—'}
                        {m.id === user?.id && (
                          <span className="ml-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                            Você
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground sm:hidden">{m.email}</span>
                    </div>
                  </td>
                  <td className="hidden px-4 py-3 text-foreground sm:table-cell">{m.email}</td>
                  <td className="px-4 py-3">
                    <Badge variant="muted">{labelFor(m.org_role ?? m.role)}</Badge>
                  </td>
                  <td className="hidden px-4 py-3 text-foreground md:table-cell">
                    {formatDate(m.created_at)}
                  </td>
                </tr>
              ))}
              {members.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhum membro encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {canInvite && (
        <p className="text-sm text-muted-foreground" data-testid="team-remove-core-note">
          Para remover alguém da organização, use o{' '}
          <a
            href={coreTeamUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
          >
            NoctusAI Core
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          .
        </p>
      )}

      {isAdmin && ready && <PendingInvitations hooks={hooks} labelFor={labelFor} />}

      {canInvite && (
        <InviteDialog
          open={inviteOpen}
          onClose={() => setInviteOpen(false)}
          hooks={hooks}
          labelFor={labelFor}
          canGrantElevated={isAdmin}
        />
      )}

      {children}
    </div>
  );
}
