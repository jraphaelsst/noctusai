/**
 * All subscriptions (paged) with manual onboarding, manual renewal and
 * cancel. Subscriptions that predate automated billing are listed but
 * cannot be changed here (the backend refuses them too).
 */
import { useState } from 'react';
import { Badge, Button, Input, TableSkeleton } from '@noctusai/lib/design-system';
import {
  type AdminSubscription,
  type SubscriptionStatus,
  STATUS_LABEL,
  STATUS_VARIANT,
  formatCents,
  formatDate,
  useAdminSubscriptions,
  useBillingMutation,
  useBillingPlans,
} from '../../../lib/billing';

const FILTERS: Array<SubscriptionStatus | ''> = ['', 'trial', 'active', 'past_due', 'grace', 'incomplete', 'canceled', 'expired'];

function ManualOnboarding({ onDone }: { onDone: () => void }) {
  const plans = useBillingPlans();
  const [orgId, setOrgId] = useState('');
  const [priceId, setPriceId] = useState('');
  const [trialDays, setTrialDays] = useState('0');
  const [note, setNote] = useState('');
  const onboard = useBillingMutation((b, body: Parameters<typeof b.onboard>[0]) => b.onboard(body));
  const prices = (plans.data ?? []).flatMap((plan) =>
    plan.prices.filter((p) => p.ativo !== false).map((p) => ({ plan, price: p })));
  const valid = /^[0-9a-f-]{36}$/i.test(orgId.trim()) && priceId && /^\d+$/.test(trialDays);

  return (
    <form
      className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        onboard.mutate(
          { org_id: orgId.trim(), plan_price_id: priceId, trial_days: Number(trialDays), note: note || undefined },
          { onSuccess: onDone },
        );
      }}
    >
      <label className="text-sm">ID da organização
        <Input value={orgId} onChange={(e) => setOrgId(e.target.value)} />
      </label>
      <label className="text-sm">Plano e preço
        <select
          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1"
          value={priceId}
          onChange={(e) => setPriceId(e.target.value)}
        >
          <option value="">Selecione…</option>
          {prices.map(({ plan, price }) => (
            <option key={price.id} value={price.id}>
              {plan.nome} — {price.billing_cycle === 'yearly' ? 'anual' : 'mensal'} — {formatCents(price.amount_cents, price.currency)}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">Dias de trial
        <Input inputMode="numeric" value={trialDays} onChange={(e) => setTrialDays(e.target.value)} />
      </label>
      <label className="text-sm">Observação
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {onboard.error && <p role="alert" className="text-sm text-destructive md:col-span-2">{onboard.error.message}</p>}
      <div className="flex gap-2 md:col-span-2">
        <Button type="submit" disabled={!valid || onboard.isPending}>
          {onboard.isPending ? 'Salvando…' : 'Criar assinatura manual'}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>Cancelar</Button>
      </div>
    </form>
  );
}

function RowActions({ sub }: { sub: AdminSubscription }) {
  const [renewUntil, setRenewUntil] = useState('');
  const cancel = useBillingMutation((b, atPeriodEnd: boolean) => b.cancel(sub.id, atPeriodEnd));
  const renew = useBillingMutation((b, until: string) => b.renew(sub.id, until));
  if (!sub.automation_managed) return <span className="text-xs text-muted-foreground">legado</span>;
  const open = !['canceled', 'expired'].includes(sub.status);
  const busy = cancel.isPending || renew.isPending;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {sub.gateway === 'manual' && open && (
        <>
          <input
            type="date"
            aria-label="Renovar até"
            className="rounded-md border border-border bg-background px-1 text-xs"
            value={renewUntil}
            onChange={(e) => setRenewUntil(e.target.value)}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!renewUntil || busy}
            onClick={() => renew.mutate(new Date(`${renewUntil}T23:59:59`).toISOString())}
          >
            Registrar pagamento
          </Button>
        </>
      )}
      {open && !sub.cancel_at_period_end && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => { if (window.confirm('Cancelar ao fim do período pago?')) cancel.mutate(true); }}
        >
          Cancelar no fim
        </Button>
      )}
      {open && (
        <Button
          size="sm"
          variant="destructive"
          disabled={busy}
          onClick={() => { if (window.confirm('Cancelar agora e revogar a licença?')) cancel.mutate(false); }}
        >
          Cancelar agora
        </Button>
      )}
      {(cancel.error || renew.error) && (
        <span role="alert" className="text-xs text-destructive">{(cancel.error ?? renew.error)!.message}</span>
      )}
    </div>
  );
}

export function SubscriptionsSection() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<SubscriptionStatus | ''>('');
  const [onboarding, setOnboarding] = useState(false);
  const { data, isPending, isFetching, error } = useAdminSubscriptions(page, status || undefined);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / 50));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          aria-label="Filtrar por status"
          className="rounded-md border border-border bg-background px-2 py-1 text-sm"
          value={status}
          onChange={(e) => { setStatus(e.target.value as SubscriptionStatus | ''); setPage(1); }}
        >
          {FILTERS.map((f) => <option key={f} value={f}>{f ? STATUS_LABEL[f] : 'Todos os status'}</option>)}
        </select>
        {!onboarding && <Button onClick={() => setOnboarding(true)}>Onboarding manual</Button>}
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {onboarding && <ManualOnboarding onDone={() => setOnboarding(false)} />}
      {showSkeleton ? (
        <TableSkeleton rows={6} columns={7} />
      ) : error && !data ? (
        <p role="alert" className="text-sm text-destructive">{error.message}</p>
      ) : data && data.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma assinatura.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2">Organização</th><th>Plano</th><th>Status</th><th>Gateway</th>
                <th>Valor</th><th>Vence / fim</th><th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {data?.data.map((sub) => (
                <tr key={sub.id} className="border-t border-border align-top">
                  <td className="p-2">{sub.organizations?.nome ?? sub.org_id}</td>
                  <td>{sub.plans?.nome ?? '—'}</td>
                  <td>
                    <Badge variant={STATUS_VARIANT[sub.status]}>{STATUS_LABEL[sub.status] ?? sub.status}</Badge>
                    {sub.cancel_at_period_end && <div className="text-xs text-muted-foreground">cancela no fim</div>}
                  </td>
                  <td>{sub.gateway ?? '—'}{sub.gateway_mode === 'test' ? ' (teste)' : ''}</td>
                  <td>
                    {formatCents(sub.amount_cents, sub.currency ?? 'BRL')}
                    {sub.billing_cycle ? ` / ${sub.billing_cycle === 'yearly' ? 'ano' : 'mês'}` : ''}
                  </td>
                  <td>
                    {sub.status === 'trial' ? `trial até ${formatDate(sub.trial_ends_at)}`
                      : sub.status === 'grace' ? `carência até ${formatDate(sub.grace_ends_at)}`
                      : formatDate(sub.current_period_end)}
                  </td>
                  <td className="py-2"><RowActions sub={sub} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex items-center gap-2 text-sm">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
        <span>Página {page} de {lastPage}</span>
        <Button size="sm" variant="outline" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Próxima</Button>
      </div>
    </div>
  );
}
