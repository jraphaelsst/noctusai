/** Status chip for an `OrderStatus` (one color mapping, one i18n label). */
import { Badge, type BadgeVariant } from '../design-system/ui/Badge';
import { useCommerceT } from './i18n';
import type { OrderStatus } from './types';

const VARIANT: Record<OrderStatus, BadgeVariant> = {
  created: 'muted',
  pending_payment: 'outline',
  paid: 'default',
  expired: 'muted',
  failed: 'destructive',
  cancelled: 'muted',
  refunded: 'outline',
  chargeback: 'destructive',
  partially_refunded: 'outline',
  disputed: 'destructive',
};

export function OrderStatusChip({ status, locale }: { status: OrderStatus; locale?: string }) {
  const { t } = useCommerceT(locale);
  return (
    <Badge variant={VARIANT[status]} data-status={status}>
      {t(`order_status.${status}`)}
    </Badge>
  );
}
