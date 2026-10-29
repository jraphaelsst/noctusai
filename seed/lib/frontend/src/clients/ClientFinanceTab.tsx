/**
 * "Financeiro" tab: open / overdue / received tiles, the client's receivables (newest first) and -- admins only --
 * "Registrar pagamento": amount prefilled with the open total, date, finance account (`GET /api/finance/accounts`),
 * method (config) and an optional pick of which entries it settles. Money flows through the finance organ: the
 * receivables live in Financeiro, so cash flow / DRE include them.
 */
import { Wallet } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { centsToInput, formatCents, parseMoneyToCents } from '../organ-kit/money';
import { EmptyState, ErrorState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select, Textarea } from './controls';
import { formatDay, paymentStatusOf, PAYMENT_STATUS, todayIn, tzOf } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, StatTile, ToneBadge } from './parts';
import type { Client, ClientFinance } from './types';

function PaymentForm({ hooks, client, finance, onClose }: { hooks: ClientsHooks; client: Client; finance: ClientFinance; onClose: () => void }) {
  const { data: config } = hooks.useClientsConfig();
  const accounts = hooks.useFinanceAccounts();
  const pay = hooks.useRegisterPayment();
  const openEntries = finance.entries.filter((e) => e.settled_cents < e.amount_cents && e.status !== 'cancelled');
  const [amount, setAmount] = React.useState(centsToInput(finance.open_cents));
  const [paidOn, setPaidOn] = React.useState(todayIn(tzOf(config)));
  const [accountId, setAccountId] = React.useState('');
  const [method, setMethod] = React.useState('');
  const [notes, setNotes] = React.useState('');
  const [picked, setPicked] = React.useState<string[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const accountList = accounts.data ?? [];
  const chosenAccount = accountId || (accountList.length === 1 ? accountList[0].id : '');

  const togglePick = (id: string) => {
    const next = picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id];
    setPicked(next);
    // The amount follows the selection (the user may still type another value).
    const sum = (next.length ? openEntries.filter((e) => next.includes(e.entry_id)) : openEntries).reduce((acc, e) => acc + e.amount_cents - e.settled_cents, 0);
    setAmount(centsToInput(next.length ? sum : finance.open_cents));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const cents = parseMoneyToCents(amount);
    if (!cents || cents <= 0) return setError(t('payment.amount_invalid'));
    if (!chosenAccount) return setError(t('payment.account_required'));
    if (!method) return setError(t('payment.method_required'));
    setError(null);
    pay.mutate(
      { clientId: client.id, amount_cents: cents, paid_on: paidOn, account_id: chosenAccount, method, notes: notes.trim() || null, ...(picked.length ? { entry_ids: picked } : {}) },
      {
        onSuccess: () => {
          toast.success(t('payment.done'));
          onClose();
        },
        onError: (err) => setError(clientsErrorText(err)),
      },
    );
  };

  return (
    <form onSubmit={submit} noValidate data-testid="payment-form">
      <DialogHeader>
        <h2 className="text-lg font-semibold">{t('payment.title')}</h2>
        <p className="text-sm text-muted-foreground">{client.name}</p>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('payment.amount')} required>
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" />
          </Field>
          <Field label={t('payment.date')} required>
            <Input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
          </Field>
          <Field label={t('payment.account')} required>
            {accounts.isError && !accounts.data ? (
              <ErrorState message={`${t('payment.accounts_error')} ${errorMessage(accounts.error)}`} />
            ) : (
              <Select value={chosenAccount} onChange={(e) => setAccountId(e.target.value)} disabled={accounts.showSkeleton}>
                <option value="">—</option>
                {accountList.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t('payment.method')} required>
            <Select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="">—</option>
              {config?.payment_methods.map((m) => (
                <option key={m.slug} value={m.slug}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {accounts.data && accountList.length === 0 && <p className="text-sm text-destructive">{t('payment.no_accounts')}</p>}
        {openEntries.length > 1 && (
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium">{t('payment.entries')}</legend>
            {openEntries.map((e) => (
              <label key={e.entry_id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={picked.includes(e.entry_id)} onChange={() => togglePick(e.entry_id)} data-testid={`payment-entry-${e.entry_id}`} />
                <span className="min-w-0 flex-1 truncate">{e.description}</span>
                <span className="text-muted-foreground">{formatCents(e.amount_cents - e.settled_cents)}</span>
              </label>
            ))}
          </fieldset>
        )}
        <Field label={t('payment.notes')}>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={2000} />
        </Field>
        <FormError message={error} />
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button type="button" variant="ghost" onClick={onClose} disabled={pay.isPending}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={pay.isPending || (accounts.data !== undefined && accountList.length === 0)} data-testid="payment-submit">
          {pay.isPending ? t('common.saving') : t('payment.submit')}
        </Button>
      </DialogFooter>
    </form>
  );
}

export interface ClientFinanceTabProps {
  hooks: ClientsHooks;
  client: Client;
  /** UX gate only (the server enforces admin on payments). */
  isAdmin?: boolean;
}

export function ClientFinanceTab({ hooks, client, isAdmin = false }: ClientFinanceTabProps) {
  const { data: config } = hooks.useClientsConfig();
  const enabled = config?.finance_enabled !== false;
  const finance = hooks.useClientFinance(client.id, enabled);
  const [paying, setPaying] = React.useState(false);

  if (!enabled) return <EmptyState message={t('finance.disabled')} />;
  const f = finance.data;

  return (
    <div className="space-y-4" data-testid="client-finance">
      <RefreshingBar active={finance.isRefreshing} label={t('common.refreshing')} />
      {finance.showSkeleton ? (
        <ListSkeleton rows={3} />
      ) : finance.isError && !f ? (
        <RetryError message={`${t('finance.error')} ${errorMessage(finance.error)}`} onRetry={() => void finance.refetch()} retryLabel={t('common.retry')} />
      ) : f ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatTile label={t('finance.open')} value={formatCents(f.open_cents)} testId="finance-open" />
            <StatTile label={t('finance.overdue')} value={formatCents(f.overdue_cents)} tone={f.overdue_cents > 0 ? 'destructive' : undefined} testId="finance-overdue" />
            <StatTile label={t('finance.paid')} value={formatCents(f.paid_cents)} tone="success" testId="finance-paid" />
          </div>
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t('finance.entries')}</h3>
            {isAdmin ? (
              <Button onClick={() => setPaying(true)} disabled={f.open_cents <= 0} data-testid="finance-pay">
                <Wallet className="mr-1 h-4 w-4" />
                {t('finance.pay')}
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">{t('finance.pay_admin_only')}</p>
            )}
          </div>
          {f.entries.length === 0 ? (
            <EmptyState message={t('finance.empty')} />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t('finance.col_description')}</th>
                    <th className="px-3 py-2 font-medium">{t('finance.col_due')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('finance.col_amount')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('finance.col_settled')}</th>
                    <th className="px-3 py-2 font-medium">{t('finance.col_status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {f.entries.map((e) => {
                    const st = PAYMENT_STATUS[paymentStatusOf(e)];
                    return (
                      <tr key={e.entry_id} className="border-t" data-testid={`finance-entry-${e.entry_id}`}>
                        <td className="px-3 py-2">{e.description}</td>
                        <td className="px-3 py-2 text-muted-foreground">{formatDay(e.due_date)}</td>
                        <td className="px-3 py-2 text-right">{formatCents(e.amount_cents)}</td>
                        <td className="px-3 py-2 text-right">{formatCents(e.settled_cents)}</td>
                        <td className="px-3 py-2">
                          <ToneBadge color={st.color}>{st.label}</ToneBadge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
      {isAdmin && f && (
        <Dialog open={paying} onClose={() => setPaying(false)} title={t('payment.title')}>
          <PaymentForm hooks={hooks} client={client} finance={f} onClose={() => setPaying(false)} />
        </Dialog>
      )}
    </div>
  );
}
