/**
 * "Acesso a produtos" (owner D5, 2026-10-14) — per member, inside ONE org: a switch per product
 * the org is licensed for. Off = blocked: that org stops being an option for the person in that
 * product (picker, SSO, dashboard). Default (no block) = allowed. The server is the authority
 * (`PUT .../product-access/{slug}` is idempotent); the switch shows the server's answer, never an
 * optimistic guess.
 *
 * Owner decisions 2026-10-14: only the org's OWNER and NoctusAI staff change it (P5) — an org admin
 * sees the same list read-only (`can_edit`); NoctusAI staff are never blockable (P3,
 * `target_is_staff`), so no switch is offered for them.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Button, Dialog, DialogBody, DialogFooter, DialogHeader, EmptyState, ErrorState, Switch, TableSkeleton,
} from '@noctusai/lib/design-system';

import { useMemberProductAccess, useSetMemberProductAccess } from '../../hooks/useTeam';
import type { TeamMember, TeamScopeOrg } from '../../hooks/useTeam';
import { teamErrorMessage } from '../../lib/team-errors';

export interface ProductAccessDialogProps {
  member: TeamMember;
  org: TeamScopeOrg;
  onClose: () => void;
}

export function ProductAccessDialog({ member, org, onClose }: ProductAccessDialogProps) {
  const q = useMemberProductAccess(org.id, member.id);
  const set = useSetMemberProductAccess(org.id, member.id);
  const [busySlug, setBusySlug] = useState<string | null>(null);

  const showSkeleton = q.isPending && !q.data;
  const editable = !!q.data && q.data.can_edit && !q.data.target_is_staff;
  const isRefreshing = q.isFetching && !!q.data;

  async function toggle(slug: string, nome: string, allowed: boolean) {
    setBusySlug(slug);
    try {
      await set.mutateAsync({ slug, blocked: !allowed });
      toast.success(allowed
        ? `${member.nome} voltou a ter acesso a ${nome} em ${org.nome}.`
        : `${member.nome} não tem mais acesso a ${nome} em ${org.nome}.`);
    } catch (err) {
      toast.error(teamErrorMessage(err, 'Não foi possível alterar o acesso ao produto.'));
    } finally {
      setBusySlug(null);
    }
  }

  let body: React.ReactNode;
  if (showSkeleton) {
    body = <div data-testid="product-access-skeleton"><TableSkeleton rows={3} columns={2} showHeader={false} /></div>;
  } else if (q.isError && !q.data) {
    body = (
      <div className="space-y-3 text-center">
        <ErrorState message={teamErrorMessage(q.error, 'Não foi possível carregar os acessos.')} />
        <Button type="button" variant="outline" onClick={() => void q.refetch()}>Tentar novamente</Button>
      </div>
    );
  } else if (!q.data || q.data.products.length === 0) {
    body = <EmptyState message="Esta organização não tem produtos licenciados." />;
  } else {
    body = (
      <ul className="divide-y divide-border rounded-md border border-border" data-testid="product-access-list">
        {q.data.products.map((p) => {
          const allowed = !p.blocked;
          return (
            <li key={p.slug} className="flex items-center justify-between gap-3 px-3 py-3">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{p.nome}</span>
                <span className="block text-xs text-muted-foreground">
                  {allowed ? 'Com acesso' : 'Bloqueado'}
                </span>
              </span>
              <Switch
                checked={allowed}
                disabled={busySlug !== null || !editable}
                aria-label={`Acesso a ${p.nome}`}
                onCheckedChange={(next) => void toggle(p.slug, p.nome, next)}
              />
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <Dialog open onClose={onClose} title="Acesso a produtos">
      <DialogHeader>
        <h2 className="text-base font-semibold text-foreground">Acesso a produtos</h2>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </DialogHeader>
      <DialogBody className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Produtos de <strong className="text-foreground">{org.nome}</strong> que{' '}
          <strong className="text-foreground">{member.nome}</strong> pode usar. Bloquear um produto
          impede a pessoa de entrar nele por esta organização; as outras organizações dela não mudam.
        </p>
        {q.data?.target_is_staff && (
          <p className="text-sm text-muted-foreground" data-testid="product-access-staff">
            Esta pessoa é da equipe NoctusAI e não pode ser bloqueada.
          </p>
        )}
        {q.data && !q.data.target_is_staff && !q.data.can_edit && (
          <p className="text-sm text-muted-foreground" data-testid="product-access-readonly">
            Somente o proprietário da organização pode bloquear ou liberar produtos.
          </p>
        )}
        {body}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>Fechar</Button>
      </DialogFooter>
    </Dialog>
  );
}
