/**
 * `<AccountantChecklist/>` — "Para o contador": every provisional choice and open question the store should take
 * to its contador, with sources, plus the exports he/she needs (DRE CSV, lançamentos CSV; the ledger OFX needs an
 * account, so it lives in the Exportações tab; the Livro Caixa and the Domínio file have their own tabs, linked below). The
 * software prepares and exports; it never signs, files or decides
 * a regime. `GET /api/finance/accountant-checklist` (CONTRACT §10.4).
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { EmptyState, FormError, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError } from './controls';
import type { AccountantChoiceItem } from './dreTypes';
import { formatDateTime } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface AccountantChecklistProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
  /** UX only: downloads offered (default: `isAdmin`; pass true for the accountant read grant). */
  canExport?: boolean;
  /** Jump to another Contador tab (`livro_caixa` · `dominio` · `mei`). */
  onOpenTab?: (tab: 'livro_caixa' | 'dominio' | 'mei') => void;
}

const EXPORT_FILENAME: Record<string, string> = {
  dre_csv: 'dre.csv',
  entries_csv: 'lancamentos.csv',
  livro_caixa_csv: 'livro-caixa.csv',
  livro_caixa_pdf: 'livro-caixa.pdf',
};

function ChoiceCard({ item }: { item: AccountantChoiceItem }) {
  const current = item.options[item.current_value] ?? item.current_value;
  return (
    <li className="space-y-1 rounded-md border p-3 text-sm" data-item={item.choice}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong>{item.question}</strong>
        <Badge variant={item.provisional ? 'outline' : 'default'}>
          {item.provisional ? t('accountant.status_provisional') : t('accountant.status_confirmed')}
        </Badge>
      </div>
      <p>{t('accountant.current_choice')}: {current}</p>
      <p className="text-xs text-muted-foreground">{t('accountant.why_open')}: {item.why_open}</p>
      <p className="text-xs text-muted-foreground">
        {t('accountant.options')}: {Object.values(item.options).join(' · ')}
      </p>
      {!item.provisional && item.confirmed_at ? (
        <p className="text-xs text-muted-foreground">
          {t('accountant.confirmed_on', { date: formatDateTime(item.confirmed_at) })}
          {item.note ? ` — ${item.note}` : ''}
        </p>
      ) : null}
      {item.sources.length > 0 ? <p className="text-xs text-muted-foreground">{t('dre.source')}: {item.sources.join('; ')}</p> : null}
    </li>
  );
}

export function AccountantChecklist({ hooks, isAdmin = false, canExport, onOpenTab }: AccountantChecklistProps) {
  const allowed = canExport ?? isAdmin;
  const list = hooks.useAccountantChecklist();
  const exp = hooks.useExport();

  if (list.showSkeleton) return <ListSkeleton rows={5} />;
  if (list.isError && !list.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  }
  const data = list.data;
  const provisional = data?.provisional_choices ?? [];
  const confirmed = data?.confirmed_choices ?? [];
  const questions = data?.open_questions ?? [];
  const downloadable = (data?.exports ?? []).filter((x) => x.name in EXPORT_FILENAME);
  const empty = provisional.length + confirmed.length + questions.length === 0;
  const pending = provisional.length + questions.length;

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing}>
      <PageHeader
        title={t('accountant.title')}
        subtitle={t('accountant.subtitle')}
        actions={<Button size="sm" variant="outline" onClick={() => window.print()}>{t('accountant.print')}</Button>}
      />
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      {data?.disclaimer ? <Notice>{data.disclaimer}</Notice> : null}
      {data && !data.tax_regime_informed ? <Notice tone="warning">{t('dre_settings.regime_unknown')}</Notice> : null}
      {empty ? (
        <EmptyState message={t('accountant.empty')} />
      ) : (
        <>
          <p className="text-sm" role="status">{pending > 0 ? t('accountant.pending', { n: pending }) : t('accountant.all_confirmed')}</p>
          {provisional.length > 0 ? (
            <section className="space-y-2" aria-label={t('accountant.provisional_title')}>
              <h3 className="text-sm font-semibold">{t('accountant.provisional_title')}</h3>
              <ol className="space-y-2">{provisional.map((i) => <ChoiceCard key={i.choice} item={i} />)}</ol>
            </section>
          ) : null}
          {questions.length > 0 ? (
            <section className="space-y-2" aria-label={t('accountant.questions_title')}>
              <h3 className="text-sm font-semibold">{t('accountant.questions_title')}</h3>
              <ol className="space-y-2">
                {questions.map((q) => (
                  <li key={q.id} className="space-y-1 rounded-md border p-3 text-sm" data-question={q.id}>
                    <strong>{q.question}</strong>
                    <p className="text-xs text-muted-foreground">{q.context}</p>
                    {q.sources.length > 0 ? <p className="text-xs text-muted-foreground">{t('dre.source')}: {q.sources.join('; ')}</p> : null}
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          {confirmed.length > 0 ? (
            <section className="space-y-2" aria-label={t('accountant.confirmed_title')}>
              <h3 className="text-sm font-semibold">{t('accountant.confirmed_title')}</h3>
              <ol className="space-y-2">{confirmed.map((i) => <ChoiceCard key={i.choice} item={i} />)}</ol>
            </section>
          ) : null}
        </>
      )}
      {data?.dominio_readiness || onOpenTab ? (
        <div className="space-y-2" data-section="books">
          <h3 className="text-sm font-semibold">{t('accountant.books_title')}</h3>
          {data?.dominio_readiness ? (
            <p className="text-xs text-muted-foreground" role="status">
              {data.dominio_readiness.ready
                ? t('accountant.dominio_ready')
                : t('accountant.dominio_not_ready', { categories: data.dominio_readiness.categories_without_code, accounts: data.dominio_readiness.accounts_without_code })}
            </p>
          ) : null}
          {onOpenTab ? (
            <ul className="flex flex-wrap gap-2">
              <li><Button size="sm" variant="outline" onClick={() => onOpenTab('livro_caixa')}>{t('accountant.open_livro_caixa')}</Button></li>
              <li><Button size="sm" variant="outline" onClick={() => onOpenTab('dominio')}>{t('accountant.open_dominio')}</Button></li>
              {data?.tax_regime === 'mei' ? <li><Button size="sm" variant="outline" onClick={() => onOpenTab('mei')}>{t('accountant.open_mei')}</Button></li> : null}
            </ul>
          ) : null}
        </div>
      ) : null}
      {downloadable.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t('accountant.exports')}</h3>
          <FormError message={exp.error ? errorMessage(exp.error) : null} />
          <ul className="flex flex-wrap gap-2">
            {downloadable.map((x) => (
              <li key={x.name}>
                <Button size="sm" variant="outline" disabled={!allowed || exp.isPending} onClick={() => exp.mutate({ path: x.path, filename: EXPORT_FILENAME[x.name] })}>
                  {t(`accountant.export_${x.name}`)}
                </Button>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">{allowed ? t('accountant.ledger_hint') : t('exports.admin_only')}</p>
        </div>
      ) : null}
    </section>
  );
}
