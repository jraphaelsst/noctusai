/**
 * `<PurchaseApproversManager/>` — the org's approver list (org admin). Approval authority in purchasing is membership in
 * THIS list (org-scoped on the server: an approver of org A is nothing in org B) -- there is no global permission to grant.
 * The server enforces admin-only and records every grant / revocation in the append-only audit log; the host's `canManage`
 * only hides the controls. Pass `members` (id + label) to pick from the org's users; without it the admin types the user id.
 */
import * as React from 'react';
import { EmptyState, ErrorState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from '../organ-kit';
import { Button } from '../design-system/ui/Button';
import { errorMessage } from '../organ-kit';
import { formatDate } from './format';
import { purchasingErrorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';

export interface PurchaseApproverMember {
  id: string;
  label: string;
}

export interface PurchaseApproversManagerProps extends PurchasingOrganProps {
  /** The org's users, to pick from (and to name the rows). Optional: without it the user id is typed / shown raw. */
  members?: PurchaseApproverMember[];
  /** The current user's id, to tag their own row. */
  currentUserId?: string;
  /** Host hint (org admin); the API is the authority. Default true. */
  canManage?: boolean;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function PurchaseApproversManager({ hooks, t = defaultPurchasingT, members, currentUserId, canManage = true }: PurchaseApproversManagerProps) {
  const approvers = hooks.usePurchaseApprovers(canManage);
  const { add, remove } = hooks.usePurchaseApproverMutations();
  const [pick, setPick] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const names = React.useMemo(() => new Map((members ?? []).map((m) => [m.id, m.label])), [members]);

  if (!canManage) return <ErrorState message={t('error.sem_permissao_aprovar')} />;
  if (approvers.showSkeleton) return <ListSkeleton rows={3} />;
  if (approvers.isError && !approvers.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(approvers.error)}`} onRetry={() => approvers.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = approvers.data ?? [];
  const taken = new Set(rows.map((r) => r.user_id));
  const options = (members ?? []).filter((m) => !taken.has(m.id));
  const busy = add.isPending || remove.isPending;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const id = pick.trim();
    if (!UUID.test(id)) {
      setErr(t('approvers.invalid_id'));
      return;
    }
    setErr(null);
    try {
      await add.mutateAsync(id);
      setPick('');
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  async function doRemove(id: string) {
    setErr(null);
    try {
      await remove.mutateAsync(id);
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  return (
    <section className="space-y-3" aria-busy={approvers.isRefreshing} aria-label={t('approvers.title')}>
      <RefreshingBar active={approvers.isRefreshing} label={t('common.refreshing')} />
      <h3 className="text-sm font-semibold">{t('approvers.title')}</h3>
      <p className="text-xs text-muted-foreground">{t('approvers.hint')}</p>
      {rows.length === 0 ? (
        <EmptyState message={t('approvers.empty')} />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-2">{t('approvers.user')}</th>
              <th>{t('approvers.since')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.user_id} className="border-b" data-testid="approver-row">
                <td className="py-2">
                  {names.get(r.user_id) ?? r.user_id}
                  {r.user_id === currentUserId ? <span className="ml-2 text-xs text-muted-foreground">({t('approvers.you')})</span> : null}
                </td>
                <td>{formatDate(r.granted_at)}</td>
                <td className="text-right">
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => doRemove(r.user_id)}>{t('approvers.remove')}</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        {members ? (
          <Field label={t('approvers.user')}>
            <Select value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">{t('approvers.pick')}</option>
              {options.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </Select>
          </Field>
        ) : (
          <Field label={t('approvers.user_id')}>
            <Input value={pick} onChange={(e) => setPick(e.target.value)} placeholder="00000000-0000-0000-0000-000000000000" />
          </Field>
        )}
        <Button type="submit" variant="primary" disabled={busy || !pick}>{add.isPending ? t('approvers.add_working') : t('approvers.add')}</Button>
      </form>
      <FormError message={err} />
    </section>
  );
}
