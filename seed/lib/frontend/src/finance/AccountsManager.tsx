/**
 * `<AccountsManager/>` — contas (banco, caixa, gateway, cartão...) with the balance of each, create /
 * edit / deactivate on the same page, and the transfer dialog. Balance = opening + ledger up to today.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, FormError, Input, ListSkeleton, PageHeader, RefreshingBar, RetryError, Select } from './controls';
import { centsToInput, formatCents, formatDate, parseMoneyToCents } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import { TransferDialog } from './TransferDialog';
import { ACCOUNT_KINDS, type AccountKind, type FinanceAccount } from './types';

export interface AccountsManagerProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

export function AccountsManager({ hooks, isAdmin = false }: AccountsManagerProps) {
  const accounts = hooks.useAccounts();
  const ids = React.useMemo(() => (accounts.data ?? []).map((a) => a.id), [accounts.data]);
  const balances = hooks.useAccountBalances(ids);
  const m = hooks.useAccountMutations();

  const [editing, setEditing] = React.useState<FinanceAccount | 'new' | null>(null);
  const [transferOpen, setTransferOpen] = React.useState(false);
  const [name, setName] = React.useState('');
  const [kind, setKind] = React.useState<AccountKind>('checking');
  const [bankCode, setBankCode] = React.useState('');
  const [agency, setAgency] = React.useState('');
  const [number, setNumber] = React.useState('');
  const [opening, setOpening] = React.useState('');
  const [openingDate, setOpeningDate] = React.useState('');
  const [gateway, setGateway] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  function open(a: FinanceAccount | null) {
    setEditing(a ?? 'new');
    setName(a?.name ?? '');
    setKind(a?.kind ?? 'checking');
    setBankCode(a?.bank_code ?? '');
    setAgency(a?.agency ?? '');
    setNumber(a?.number ?? '');
    setOpening(a ? centsToInput(a.opening_balance_cents) : '');
    setOpeningDate(a?.opening_date ?? '');
    setGateway(a?.gateway ?? '');
    setErrors({});
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    const cents = opening.trim() ? parseMoneyToCents(opening.replace(/^-/, '')) : 0;
    const negative = opening.trim().startsWith('-');
    if (!name.trim()) next.name = t('common.required');
    if (cents === null) next.opening = t('entry.amount_invalid');
    if (kind === 'gateway' && !gateway.trim()) next.gateway = t('accounts.gateway_required');
    setErrors(next);
    if (Object.keys(next).length) return;
    const openingCents = (negative ? -1 : 1) * (cents ?? 0);
    const common = {
      name: name.trim(),
      bank_code: bankCode.trim() || null,
      agency: agency.trim() || null,
      number: number.trim() || null,
      opening_balance_cents: openingCents,
      opening_date: openingDate || null,
      gateway: kind === 'gateway' ? gateway.trim() : null,
    };
    try {
      if (editing === 'new') await m.create.mutateAsync({ kind, ...common });
      else if (editing) await m.update.mutateAsync({ id: editing.id, ...common });
      setEditing(null);
    } catch {
      // Surfaced below.
    }
  }

  if (accounts.showSkeleton) return <ListSkeleton />;
  if (accounts.isError && !accounts.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(accounts.error)}`} onRetry={() => accounts.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = accounts.data ?? [];
  const mutErr = m.create.error ?? m.update.error;

  return (
    <section className="space-y-3" aria-busy={accounts.isRefreshing || balances.isRefreshing}>
      <PageHeader
        title={t('accounts.title')}
        subtitle={t('accounts.subtitle')}
        actions={
          isAdmin ? (
            <>
              <Button size="sm" variant="outline" onClick={() => setTransferOpen(true)} disabled={list.filter((a) => a.active).length < 2}>
                {t('accounts.transfer')}
              </Button>
              <Button size="sm" onClick={() => open(null)}>{t('accounts.add')}</Button>
            </>
          ) : undefined
        }
      />
      <RefreshingBar active={accounts.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {list.length === 0 && editing === null ? <EmptyState message={t('accounts.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {list.map((a) => {
          const bal = balances.byId[a.id];
          return (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
              <span>
                <span className={a.active ? 'font-medium' : 'font-medium text-muted-foreground line-through'}>{a.name}</span>{' '}
                <span className="text-xs text-muted-foreground">
                  {t(`account_kind.${a.kind}`)}
                  {a.gateway ? ` · ${a.gateway}` : ''}
                  {a.opening_date ? ` · ${t('accounts.opening_on')} ${formatDate(a.opening_date)}` : ''}
                </span>
              </span>
              <span className="flex items-center gap-3">
                <span aria-label={`${t('accounts.balance')}: ${a.name}`}>
                  {bal ? formatCents(bal.balance_cents) : balances.showSkeleton ? '…' : '—'}
                </span>
                {isAdmin ? (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => open(a)}>{t('common.edit')}</Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={m.update.isPending}
                      onClick={() => m.update.mutate({ id: a.id, active: !a.active })}
                    >
                      {a.active ? t('common.deactivate') : t('common.activate')}
                    </Button>
                  </>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
      {isAdmin && editing !== null ? (
        <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" aria-label={t('accounts.form')}>
          <Field label={t('accounts.name')} required error={errors.name}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </Field>
          <Field label={t('accounts.kind')}>
            <Select value={kind} disabled={editing !== 'new'} onChange={(e) => setKind(e.target.value as AccountKind)}>
              {ACCOUNT_KINDS.map((k) => <option key={k} value={k}>{t(`account_kind.${k}`)}</option>)}
            </Select>
          </Field>
          {kind === 'gateway' ? (
            <Field label={t('accounts.gateway')} required error={errors.gateway}>
              <Input value={gateway} onChange={(e) => setGateway(e.target.value)} placeholder="asaas" maxLength={40} />
            </Field>
          ) : null}
          <Field label={t('accounts.bank_code')}><Input value={bankCode} onChange={(e) => setBankCode(e.target.value)} maxLength={10} /></Field>
          <Field label={t('accounts.agency')}><Input value={agency} onChange={(e) => setAgency(e.target.value)} maxLength={20} /></Field>
          <Field label={t('accounts.number')}><Input value={number} onChange={(e) => setNumber(e.target.value)} maxLength={40} /></Field>
          <Field label={t('accounts.opening_balance')} error={errors.opening}>
            <Input inputMode="decimal" placeholder="0,00" value={opening} onChange={(e) => setOpening(e.target.value)} />
          </Field>
          <Field label={t('accounts.opening_date')}>
            <Input type="date" value={openingDate} onChange={(e) => setOpeningDate(e.target.value)} />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
      {isAdmin ? <TransferDialog hooks={hooks} open={transferOpen} onClose={() => setTransferOpen(false)} /> : null}
    </section>
  );
}
