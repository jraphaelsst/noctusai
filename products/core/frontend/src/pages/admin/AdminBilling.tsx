/**
 * Admin > Faturamento — platform billing for the edicao-fotos R2 release.
 *
 * Tabs are sub-routes (`/admin/billing/<tab>`, the seed `SectionTabsPage`): summary (MRR/ARR from what subscriptions actually pay), plans and
 * prices, subscriptions (incl. manual onboarding), payments with fees, and
 * gateway settings (keys, mode, automations, webhook URLs).
 */
import { SectionTabsPage, type SectionTab } from '@noctusai/lib/components';
import { Badge, Skeleton } from '@noctusai/lib/design-system';
import { STATUS_LABEL, type SubscriptionStatus, formatMoney, useBillingSummary } from '../../lib/billing';
import { GatewaysSection } from './billing/GatewaysSection';
import { PaymentsSection } from './billing/PaymentsSection';
import { PlansSection } from './billing/PlansSection';
import { SubscriptionsSection } from './billing/SubscriptionsSection';

function SummarySection() {
  const { data, isPending, isFetching, error } = useBillingSummary();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}
      </div>
    );
  }
  if (error && !data) return <p role="alert" className="text-sm text-destructive">{error.message}</p>;
  if (!data) return null;

  const cards = [
    { label: 'MRR (receita mensal recorrente)', value: formatMoney(data.mrr) },
    { label: 'ARR (projeção anual)', value: formatMoney(data.arr) },
    { label: 'Assinaturas que pagam', value: String(data.counted_subscriptions) },
  ];
  return (
    <div className="space-y-4" aria-busy={isRefreshing}>
      <div className="flex flex-wrap gap-2">
        <Badge variant={data.mode === 'live' ? 'destructive' : 'outline'}>
          modo {data.mode === 'live' ? 'produção' : 'teste'}
        </Badge>
        <Badge variant={data.automations_enabled ? 'default' : 'muted'}>
          automações {data.automations_enabled ? 'ligadas' : 'desligadas'}
        </Badge>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-lg border border-border bg-card p-5">
            <div className="text-2xl font-bold text-foreground">{c.value}</div>
            <div className="mt-1 text-sm text-muted-foreground">{c.label}</div>
          </div>
        ))}
      </div>
      {Object.keys(data.non_brl_mrr).length > 0 && (
        <p className="text-xs text-muted-foreground">
          Fora do MRR em BRL: {Object.entries(data.non_brl_mrr).map(([cur, v]) => formatMoney(v, cur)).join(', ')}
        </p>
      )}
      <div className="flex flex-wrap gap-3 text-sm">
        {(Object.entries(data.counts) as Array<[SubscriptionStatus, number]>).map(([status, count]) => (
          <span key={status} className="rounded-md border border-border px-2 py-1">
            {STATUS_LABEL[status] ?? status}: <strong>{count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

export function AdminBilling() {
  const sections: SectionTab[] = [
    { key: 'summary', label: 'Resumo', render: () => <SummarySection /> },
    { key: 'plans', label: 'Planos', render: () => <PlansSection /> },
    { key: 'subscriptions', label: 'Assinaturas', render: () => <SubscriptionsSection /> },
    { key: 'payments', label: 'Pagamentos', render: () => <PaymentsSection /> },
    { key: 'gateways', label: 'Gateways', render: () => <GatewaysSection /> },
  ];
  return (
    <SectionTabsPage
      basePath="/admin/billing"
      title="Faturamento"
      description="Planos, assinaturas, pagamentos e gateways da plataforma"
      sections={sections}
    />
  );
}
