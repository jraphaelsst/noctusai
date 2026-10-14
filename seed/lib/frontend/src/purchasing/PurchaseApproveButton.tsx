/**
 * `<PurchaseApproveButton/>` — the order lifecycle action for the CURRENT status: draft -> Aprovar, approved -> Marcar como
 * enviado, and Cancelar while nothing was received. Who may approve is decided by the SERVER (admin or the
 * `purchasing.approve` permission; above the org threshold only the permission): the host passes `canApprove` only to hide
 * a button the user can never use, and a refusal is rendered with its stable code's pt-BR copy.
 */
import * as React from 'react';
import { FormError } from '../organ-kit';
import { Button } from '../design-system/ui/Button';
import { formatCents } from './format';
import { purchasingErrorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';
import type { PurchaseOrder } from './types';

export interface PurchaseApproveButtonProps extends PurchasingOrganProps {
  order: Pick<PurchaseOrder, 'id' | 'status' | 'total_cents'>;
  /** Host hint (the user's permission); the API is the authority. Default true. */
  canApprove?: boolean;
  /** Show send / cancel too (admins). Default true. */
  canManage?: boolean;
  /** The org's `approval_threshold_cents`, to warn up front that this order needs the permission. */
  thresholdCents?: number | null;
  onDone?: (order: PurchaseOrder) => void;
}

export function PurchaseApproveButton({ hooks, t = defaultPurchasingT, locale, order, canApprove = true, canManage = true, thresholdCents = null, onDone }: PurchaseApproveButtonProps) {
  const { approve, send, cancel } = hooks.usePurchaseOrderMutations();
  const [err, setErr] = React.useState<string | null>(null);
  const busy = approve.isPending || send.isPending || cancel.isPending;
  const above = thresholdCents != null && order.total_cents > thresholdCents;

  async function run(fn: () => Promise<PurchaseOrder>) {
    setErr(null);
    try {
      onDone?.(await fn());
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  const canCancel = canManage && ['draft', 'approved', 'sent'].includes(order.status);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {order.status === 'draft' && canApprove ? (
          <Button variant="primary" disabled={busy} onClick={() => run(() => approve.mutateAsync(order.id))}>
            {approve.isPending ? t('approve.working') : t('approve.button')}
          </Button>
        ) : null}
        {order.status === 'approved' && canManage ? (
          <Button variant="primary" disabled={busy} onClick={() => run(() => send.mutateAsync(order.id))}>{t('approve.send')}</Button>
        ) : null}
        {canCancel ? (
          <Button variant="outline" disabled={busy} onClick={() => run(() => cancel.mutateAsync({ id: order.id }))}>{t('approve.cancel')}</Button>
        ) : null}
      </div>
      {order.status === 'draft' && above ? <p className="text-xs text-muted-foreground" data-testid="approve-above">{t('approve.above', { limit: formatCents(thresholdCents, 'BRL', locale) })}</p> : null}
      <FormError message={err} />
    </div>
  );
}
