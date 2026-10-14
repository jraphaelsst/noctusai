/**
 * `<DominioExport/>` — the accounting entries of a period as a Domínio (Thomson Reuters) import file. Needs the contador's
 * account code on every category and bank account used in the period; when something is missing the server answers 422 with
 * the exact list and this panel shows it (nothing partial is ever produced). The system prepares the file; the contador
 * imports it and keeps the books. `GET /api/finance/exports/dominio.txt` (layout notes: `finance/DOMINIO-LAYOUT.md`).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { dominioMissingOf } from './accountantTypes';
import { Field, FormError, HelpTip, Input, Notice, PageHeader } from './controls';
import { monthStartIso, todayIso } from './format';
import { FINANCE_EXPORT_PATHS, errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface DominioExportProps {
  hooks: FinanceHooks;
  canExport?: boolean;
  /** Takes the user to Cadastros (where the codes are typed). */
  onGoToRegisters?: () => void;
  now?: Date;
}

export function DominioExport({ hooks, canExport = false, onGoToRegisters, now }: DominioExportProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const checklist = hooks.useAccountantChecklist();
  const exp = hooks.useExport();
  const [from, setFrom] = React.useState(monthStartIso(base));
  const [to, setTo] = React.useState(todayIso(base));
  const [cnpj, setCnpj] = React.useState('');
  const [historyCode, setHistoryCode] = React.useState('');
  const [done, setDone] = React.useState(false);
  const [localError, setLocalError] = React.useState<string | null>(null);

  async function run() {
    setDone(false);
    const digits = cnpj.replace(/\D/g, '');
    if (digits.length !== 11 && digits.length !== 14) {
      setLocalError(t('dominio.cnpj_invalid'));
      return;
    }
    setLocalError(null);
    try {
      await exp.mutateAsync({ path: FINANCE_EXPORT_PATHS.dominio, params: { from, to, cnpj: digits, history_code: historyCode.trim() }, filename: 'dominio.txt' });
      setDone(true);
    } catch {
      // Surfaced below (the 422 carries the list of missing codes).
    }
  }

  const missing = dominioMissingOf(exp.error);
  const readiness = checklist.data?.dominio_readiness;
  return (
    <section className="space-y-3">
      <PageHeader title={t('dominio.title')} subtitle={t('dominio.subtitle')} actions={<HelpTip label={t('dominio.help_label')}>{t('dominio.help')}</HelpTip>} />
      {readiness && !readiness.ready ? (
        <Notice tone="warning">{t('dominio.readiness', { categories: readiness.categories_without_code, accounts: readiness.accounts_without_code })}</Notice>
      ) : null}
      <div className="grid max-w-2xl gap-2 sm:grid-cols-2">
        <Field label={t('report.from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('report.to')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label={t('dominio.cnpj')} required><Input inputMode="numeric" value={cnpj} onChange={(e) => setCnpj(e.target.value)} placeholder="00.000.000/0000-00" /></Field>
        <Field label={t('dominio.history_code')}><Input inputMode="numeric" value={historyCode} onChange={(e) => setHistoryCode(e.target.value)} /></Field>
      </div>
      {canExport ? (
        <Button size="sm" disabled={exp.isPending} onClick={() => void run()}>{t('dominio.download')}</Button>
      ) : (
        <p className="text-sm text-muted-foreground">{t('exports.admin_only')}</p>
      )}
      {done ? <p role="status" className="text-sm text-muted-foreground">{t('exports.downloaded')}</p> : null}
      <FormError message={localError ?? (exp.error && !missing ? errorMessage(exp.error) : null)} />
      {missing ? (
        <div role="alert" className="space-y-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm" data-testid="dominio-missing">
          <p className="font-medium">{t('dominio.missing_title')}</p>
          {missing.categories.length > 0 ? (
            <div>
              <p className="text-xs font-medium">{t('dominio.missing_categories')}</p>
              <ul className="list-disc pl-5 text-xs">{missing.categories.map((c) => <li key={c.id}>{c.name}</li>)}</ul>
            </div>
          ) : null}
          {missing.accounts.length > 0 ? (
            <div>
              <p className="text-xs font-medium">{t('dominio.missing_accounts')}</p>
              <ul className="list-disc pl-5 text-xs">{missing.accounts.map((a) => <li key={a.id}>{a.name}</li>)}</ul>
            </div>
          ) : null}
          {missing.issues.length > 0 ? (
            <ul className="list-disc pl-5 text-xs">{missing.issues.map((i) => <li key={i.code}>{t(`dominio.issue_${i.code.split(':')[0]}`)} ({i.count})</li>)}</ul>
          ) : null}
          {onGoToRegisters ? <Button size="sm" variant="outline" onClick={onGoToRegisters}>{t('dominio.go_registers')}</Button> : null}
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">{t('dominio.disclaimer')}</p>
    </section>
  );
}
