/**
 * Plans + prices CRUD. A price is immutable once created: changing an
 * amount creates a new price and retires the old one (subscriptions keep
 * the price they were sold at). Stripe Price ids are editable per mode.
 */
import { useState } from 'react';
import { Badge, Button, Input, TableSkeleton } from '@noctusai/lib/design-system';
import {
  type BillingCycle,
  type BillingPlan,
  type PlanPrice,
  formatCents,
  parseMoneyToCents,
  useBillingMutation,
  useBillingPlans,
} from '../../../lib/billing';

const AUDIENCE_LABEL = { individual: 'Corretor individual', company: 'Imobiliária', any: 'Todos' } as const;
const CYCLE_LABEL: Record<BillingCycle, string> = { monthly: 'Mensal', yearly: 'Anual' };

interface PlanDraft {
  nome: string;
  slug: string;
  audience: BillingPlan['audience'];
  trial_days: string;
  grace_days: string;
  product_id: string;
}

const EMPTY_DRAFT: PlanDraft = { nome: '', slug: '', audience: 'any', trial_days: '0', grace_days: '0', product_id: '' };

function toInt(value: string): number | null {
  return /^\d+$/.test(value) ? Number(value) : null;
}

function NewPlanForm({ onDone }: { onDone: () => void }) {
  const [draft, setDraft] = useState<PlanDraft>(EMPTY_DRAFT);
  const create = useBillingMutation((b, body: Partial<BillingPlan>) => b.createPlan(body));
  const trial = toInt(draft.trial_days);
  const grace = toInt(draft.grace_days);
  const valid = draft.nome.trim() && /^[a-z0-9][a-z0-9-_]*$/.test(draft.slug) && trial !== null && grace !== null;

  return (
    <form
      className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        create.mutate(
          {
            nome: draft.nome.trim(),
            slug: draft.slug,
            audience: draft.audience,
            trial_days: trial!,
            grace_days: grace!,
            ...(draft.product_id.trim() ? { product_id: draft.product_id.trim() } : {}),
          },
          { onSuccess: () => { setDraft(EMPTY_DRAFT); onDone(); } },
        );
      }}
    >
      <label className="text-sm">Nome
        <Input value={draft.nome} onChange={(e) => setDraft({ ...draft, nome: e.target.value })} />
      </label>
      <label className="text-sm">Slug
        <Input value={draft.slug} onChange={(e) => setDraft({ ...draft, slug: e.target.value.toLowerCase() })} />
      </label>
      <label className="text-sm">Público
        <select
          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1"
          value={draft.audience}
          onChange={(e) => setDraft({ ...draft, audience: e.target.value as BillingPlan['audience'] })}
        >
          {Object.entries(AUDIENCE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="text-sm">Dias de trial
        <Input inputMode="numeric" value={draft.trial_days} onChange={(e) => setDraft({ ...draft, trial_days: e.target.value })} />
      </label>
      <label className="text-sm">Dias de carência
        <Input inputMode="numeric" value={draft.grace_days} onChange={(e) => setDraft({ ...draft, grace_days: e.target.value })} />
      </label>
      <label className="text-sm">Produto (id) licenciado
        <Input value={draft.product_id} onChange={(e) => setDraft({ ...draft, product_id: e.target.value })} />
      </label>
      {create.error && <p role="alert" className="text-sm text-destructive md:col-span-3">{create.error.message}</p>}
      <div className="md:col-span-3 flex gap-2">
        <Button type="submit" disabled={!valid || create.isPending}>{create.isPending ? 'Criando…' : 'Criar plano'}</Button>
        <Button type="button" variant="outline" onClick={onDone}>Cancelar</Button>
      </div>
    </form>
  );
}

function PlanSettings({ plan }: { plan: BillingPlan }) {
  const [trial, setTrial] = useState(String(plan.trial_days));
  const [grace, setGrace] = useState(String(plan.grace_days ?? 0));
  const update = useBillingMutation((b, body: Partial<BillingPlan>) => b.updatePlan(plan.id, body));
  const t = toInt(trial);
  const g = toInt(grace);
  const dirty = t !== plan.trial_days || g !== (plan.grace_days ?? 0);
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-xs">Trial (dias)
        <Input aria-label={`Trial ${plan.nome}`} className="w-20" value={trial} onChange={(e) => setTrial(e.target.value)} />
      </label>
      <label className="text-xs">Carência (dias)
        <Input aria-label={`Carência ${plan.nome}`} className="w-20" value={grace} onChange={(e) => setGrace(e.target.value)} />
      </label>
      <Button
        size="sm"
        variant="outline"
        disabled={!dirty || t === null || g === null || update.isPending}
        onClick={() => update.mutate({ trial_days: t!, grace_days: g! })}
      >
        Salvar
      </Button>
      <Button
        size="sm"
        variant={plan.ativo ? 'destructive' : 'outline'}
        disabled={update.isPending}
        onClick={() => update.mutate({ ativo: !plan.ativo })}
      >
        {plan.ativo ? 'Desativar' : 'Reativar'}
      </Button>
      {update.error && <span role="alert" className="text-xs text-destructive">{update.error.message}</span>}
    </div>
  );
}

function PriceRow({ price }: { price: PlanPrice }) {
  const [test, setTest] = useState(price.stripe_price_id_test ?? '');
  const [live, setLive] = useState(price.stripe_price_id_live ?? '');
  const update = useBillingMutation((b, body: Partial<PlanPrice>) => b.updatePrice(price.id, body));
  const validId = (v: string) => v === '' || /^price_[A-Za-z0-9]+$/.test(v);
  const dirty = test !== (price.stripe_price_id_test ?? '') || live !== (price.stripe_price_id_live ?? '');
  return (
    <tr className="border-t border-border">
      <td className="py-2">{CYCLE_LABEL[price.billing_cycle]}</td>
      <td>{formatCents(price.amount_cents, price.currency)}</td>
      <td><Input aria-label="Stripe price (teste)" className="w-44" value={test} onChange={(e) => setTest(e.target.value.trim())} /></td>
      <td><Input aria-label="Stripe price (produção)" className="w-44" value={live} onChange={(e) => setLive(e.target.value.trim())} /></td>
      <td className="space-x-2 whitespace-nowrap">
        <Button
          size="sm"
          variant="outline"
          disabled={!dirty || !validId(test) || !validId(live) || update.isPending}
          onClick={() => update.mutate({ stripe_price_id_test: test, stripe_price_id_live: live })}
        >
          Salvar
        </Button>
        <Button size="sm" variant="ghost" disabled={update.isPending} onClick={() => update.mutate({ ativo: false })}>
          Retirar
        </Button>
        {update.error && <span role="alert" className="text-xs text-destructive">{update.error.message}</span>}
      </td>
    </tr>
  );
}

function NewPrice({ planId }: { planId: string }) {
  const [cycle, setCycle] = useState<BillingCycle>('monthly');
  const [amount, setAmount] = useState('');
  const create = useBillingMutation((b, body: { billing_cycle: BillingCycle; amount_cents: number }) =>
    b.createPrice(planId, body));
  const cents = parseMoneyToCents(amount);
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs">Ciclo
        <select
          className="ml-1 rounded-md border border-border bg-background px-2 py-1"
          value={cycle}
          onChange={(e) => setCycle(e.target.value as BillingCycle)}
        >
          <option value="monthly">Mensal</option>
          <option value="yearly">Anual</option>
        </select>
      </label>
      <label className="text-xs">Valor (R$)
        <Input aria-label="Novo valor" className="w-28" placeholder="99,90" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </label>
      <Button
        size="sm"
        disabled={cents === null || create.isPending}
        onClick={() => create.mutate({ billing_cycle: cycle, amount_cents: cents! }, { onSuccess: () => setAmount('') })}
      >
        Definir preço
      </Button>
      {create.error && <span role="alert" className="text-xs text-destructive">{create.error.message}</span>}
    </div>
  );
}

export function PlansSection() {
  const { data, isPending, isFetching, error } = useBillingPlans();
  const [creating, setCreating] = useState(false);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) return <TableSkeleton rows={4} columns={4} />;
  if (error && !data) return <p role="alert" className="text-sm text-destructive">{error.message}</p>;

  return (
    <div className="space-y-4" aria-busy={isRefreshing}>
      {creating
        ? <NewPlanForm onDone={() => setCreating(false)} />
        : <Button onClick={() => setCreating(true)}>Novo plano</Button>}
      {data?.length === 0 && <p className="text-sm text-muted-foreground">Nenhum plano cadastrado.</p>}
      {data?.map((plan) => {
        const active = plan.prices.filter((p) => p.ativo !== false);
        return (
          <section key={plan.id} className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold text-foreground">{plan.nome}</h2>
              <code className="text-xs text-muted-foreground">{plan.slug}</code>
              <Badge variant="outline">{AUDIENCE_LABEL[plan.audience] ?? plan.audience}</Badge>
              {!plan.ativo && <Badge variant="muted">inativo</Badge>}
              {!plan.product_id && <Badge variant="destructive">sem produto — não concede licença</Badge>}
            </div>
            <PlanSettings plan={plan} />
            {active.length > 0 ? (
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th>Ciclo</th><th>Valor</th><th>Stripe (teste)</th><th>Stripe (produção)</th><th /></tr>
                </thead>
                <tbody>{active.map((price) => <PriceRow key={price.id} price={price} />)}</tbody>
              </table>
            ) : (
              <p className="text-sm text-muted-foreground">Sem preço ativo — o plano não aparece para venda.</p>
            )}
            <NewPrice planId={plan.id} />
          </section>
        );
      })}
    </div>
  );
}
