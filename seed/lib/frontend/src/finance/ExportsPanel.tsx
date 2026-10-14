/** `<ExportsPanel/>` — downloads for the contador: lançamentos (CSV), razão (OFX) and DRE (CSV). Admin-only on the server. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Card, Field, FormError, Input, PageHeader, Select } from './controls';
import { monthStartIso, todayIso } from './format';
import { FINANCE_EXPORT_PATHS, errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import { ENTRY_DIRECTIONS, ENTRY_STATUSES } from './types';

export interface ExportsPanelProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
  now?: Date;
}

export function ExportsPanel({ hooks, isAdmin = false, now }: ExportsPanelProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const accounts = hooks.useAccounts();
  const exp = hooks.useExport();

  const [from, setFrom] = React.useState(monthStartIso(base));
  const [to, setTo] = React.useState(todayIso(base));
  const [direction, setDirection] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [accountId, setAccountId] = React.useState('');
  const [done, setDone] = React.useState<string | null>(null);
  const [localError, setLocalError] = React.useState<string | null>(null);

  async function run(key: string, path: string, params: Record<string, unknown>, filename: string) {
    setDone(null);
    setLocalError(null);
    try {
      await exp.mutateAsync({ path, params, filename });
      setDone(key);
    } catch {
      // Surfaced through `exp.error`.
    }
  }

  if (!isAdmin) {
    return (
      <section className="space-y-3">
        <PageHeader title={t('exports.title')} />
        <p className="text-sm text-muted-foreground">{t('exports.admin_only')}</p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t('exports.title')} subtitle={t('exports.subtitle')} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      <FormError message={localError ?? (exp.error ? errorMessage(exp.error) : null)} />
      {done ? <p role="status" className="text-sm text-muted-foreground">{t('exports.downloaded')}</p> : null}
      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="space-y-2 p-4">
          <h3 className="font-semibold">{t('exports.entries_title')}</h3>
          <p className="text-xs text-muted-foreground">{t('exports.entries_help')}</p>
          <Select aria-label={t('entries.filter_direction')} value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="">{t('entries.all_directions')}</option>
            {ENTRY_DIRECTIONS.map((d) => <option key={d} value={d}>{t(`entry.direction_${d}`)}</option>)}
          </Select>
          <Select aria-label={t('entries.filter_status')} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t('common.all')}</option>
            {ENTRY_STATUSES.map((s) => <option key={s} value={s}>{t(`entry_status.${s}`)}</option>)}
          </Select>
          <Button size="sm" disabled={exp.isPending} onClick={() => run('entries', FINANCE_EXPORT_PATHS.entries, { from, to, direction, status }, 'lancamentos.csv')}>
            {t('exports.download_csv')}
          </Button>
        </Card>
        <Card className="space-y-2 p-4">
          <h3 className="font-semibold">{t('exports.ledger_title')}</h3>
          <p className="text-xs text-muted-foreground">{t('exports.ledger_help')}</p>
          <Select aria-label={t('report.account')} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t('exports.choose_account')}</option>
            {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
          <Button
            size="sm"
            disabled={exp.isPending}
            onClick={() => {
              if (!accountId) {
                setLocalError(t('exports.account_required'));
                return;
              }
              void run('ledger', FINANCE_EXPORT_PATHS.ledger, { account_id: accountId, from, to }, 'razao.ofx');
            }}
          >
            {t('exports.download_ofx')}
          </Button>
        </Card>
        <Card className="space-y-2 p-4">
          <h3 className="font-semibold">{t('exports.dre_title')}</h3>
          <p className="text-xs text-muted-foreground">{t('exports.dre_help')}</p>
          <Button size="sm" disabled={exp.isPending} onClick={() => run('dre', FINANCE_EXPORT_PATHS.dre, { from, to }, 'dre.csv')}>
            {t('exports.download_csv')}
          </Button>
        </Card>
      </div>
    </section>
  );
}
