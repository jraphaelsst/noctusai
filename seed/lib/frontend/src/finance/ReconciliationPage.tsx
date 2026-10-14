/**
 * `<ReconciliationPage/>` — conciliação bancária: import an OFX/CSV statement, see its lines with the
 * system's suggested matches, match (or ignore) each line, and sync gateway accounts (Asaas/Stripe).
 * Matching a line to an open entry settles it; matching to an already-paid one just links the ledger row.
 * Reads are for staff; import / match / ignore / sync are admin (server enforced).
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import {
  Card, EmptyState, Field, FormError, Input, ListSkeleton, Notice, PageHeader, Pager, RefreshingBar, RetryError, Select, totalPagesOf,
} from './controls';
import { FormDialog } from './FormDialog';
import { formatCents, formatDate } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import {
  MATCH_STATUSES, type CsvColumnMap, type FinanceEntry, type GatewaySyncResult, type MatchStatus, type StatementImportResult, type StatementLine,
} from './types';

export interface ReconciliationPageProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

/** A column is a header name or a 0-based index (a numeric-looking string is an index). */
export function parseColumn(raw: string): string | number | undefined {
  const s = raw.trim();
  if (!s) return undefined;
  return /^\d+$/.test(s) ? Number(s) : s;
}

function StatusBadge({ status }: { status: MatchStatus }) {
  const variant = status === 'matched' ? 'default' : status === 'ignored' ? 'muted' : 'outline';
  return <Badge variant={variant}>{t(`match_status.${status}`)}</Badge>;
}

function SuggestedEntry({ hooks, entryId }: { hooks: FinanceHooks; entryId: string }) {
  const detail = hooks.useEntry(entryId);
  if (detail.showSkeleton) return <span className="text-xs text-muted-foreground">…</span>;
  if (!detail.data) return <span className="text-xs text-muted-foreground">{t('reconcile.suggestion_unavailable')}</span>;
  return (
    <span className="text-xs">
      {t('reconcile.suggestion')}: <strong>{detail.data.description}</strong> · {formatCents(detail.data.amount_cents)} · {formatDate(detail.data.due_date)}
    </span>
  );
}

function MatchPicker({
  hooks, line, onPick, onClose, pending,
}: {
  hooks: FinanceHooks; line: StatementLine; onPick: (e: FinanceEntry) => void; onClose: () => void; pending: boolean;
}) {
  const [q, setQ] = React.useState('');
  const direction = line.amount_cents > 0 ? 'receivable' : 'payable';
  const entries = hooks.useEntries({ direction, status: '', q, page: 1, page_size: 20 });
  const open = (entries.data?.data ?? []).filter((e) => e.status === 'open' || e.status === 'partial' || e.status === 'paid');
  return (
    <FormDialog open onClose={onClose} title={t('reconcile.pick_title')} wide>
      <p className="mb-2 text-sm">
        {formatDate(line.posted_on)} · {line.description} · <strong>{formatCents(line.amount_cents)}</strong>
      </p>
      <Input type="search" aria-label={t('entries.search')} placeholder={t('entries.search')} value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-2">
        {entries.showSkeleton ? (
          <ListSkeleton rows={3} />
        ) : entries.isError && !entries.data ? (
          <RetryError message={`${t('common.error_loading')}: ${errorMessage(entries.error)}`} onRetry={() => entries.refetch()} retryLabel={t('common.retry')} />
        ) : open.length === 0 ? (
          <EmptyState message={t('entries.empty')} />
        ) : (
          <ul className="divide-y rounded-md border text-sm">
            {open.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 p-2">
                <span>{e.description} · {formatCents(e.amount_cents)} · {formatDate(e.due_date)}</span>
                <Button size="sm" disabled={pending} onClick={() => onPick(e)}>{t('reconcile.match')}</Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </FormDialog>
  );
}

function ImportForm({ hooks, accountId, onImported }: { hooks: FinanceHooks; accountId: string; onImported: (r: StatementImportResult) => void }) {
  const m = hooks.useReconciliationMutations();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [colDate, setColDate] = React.useState('');
  const [colDesc, setColDesc] = React.useState('');
  const [colAmount, setColAmount] = React.useState('');
  const [colDebit, setColDebit] = React.useState('');
  const [colCredit, setColCredit] = React.useState('');
  const [delimiter, setDelimiter] = React.useState<NonNullable<CsvColumnMap['delimiter']>>(';');
  const [dateFormat, setDateFormat] = React.useState<NonNullable<CsvColumnMap['date_format']>>('dmy');
  const [decimal, setDecimal] = React.useState<NonNullable<CsvColumnMap['decimal']>>('comma');
  const [hasHeader, setHasHeader] = React.useState(true);
  const [skipRows, setSkipRows] = React.useState('0');
  const [error, setError] = React.useState<string | null>(null);

  const isCsv = !!file && /\.(csv|txt)$/i.test(file.name);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setError(null);
    if (!accountId) return setError(t('reconcile.choose_account_first'));
    if (!file) return setError(t('reconcile.file_required'));
    let column_map: CsvColumnMap | undefined;
    if (isCsv) {
      const date = parseColumn(colDate);
      const description = parseColumn(colDesc);
      const amount = parseColumn(colAmount);
      const debit = parseColumn(colDebit);
      const credit = parseColumn(colCredit);
      if (date === undefined || description === undefined) return setError(t('reconcile.csv_need_columns'));
      if (amount === undefined && (debit === undefined || credit === undefined)) return setError(t('reconcile.csv_need_amount'));
      if (amount !== undefined && (debit !== undefined || credit !== undefined)) return setError(t('reconcile.csv_amount_xor'));
      column_map = {
        date, description, ...(amount !== undefined ? { amount } : { debit, credit }),
        delimiter, date_format: dateFormat, decimal, has_header: hasHeader, skip_rows: Number(skipRows) || 0,
      };
    }
    try {
      const result = await m.importStatement.mutateAsync({ account_id: accountId, file, format: isCsv ? 'csv' : undefined, column_map });
      onImported(result);
      setFile(null);
    } catch {
      // Surfaced below.
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-md border p-3" aria-label={t('reconcile.import_title')}>
      <h3 className="text-sm font-semibold">{t('reconcile.import_title')}</h3>
      <p className="text-xs text-muted-foreground">{t('reconcile.import_help')}</p>
      <input
        ref={fileRef}
        type="file"
        accept=".ofx,.qfx,.csv,.txt"
        aria-label={t('reconcile.choose_file')}
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block text-sm"
      />
      {isCsv ? (
        <div className="grid gap-2 sm:grid-cols-3" aria-label={t('reconcile.csv_map')}>
          <p className="text-xs text-muted-foreground sm:col-span-3">{t('reconcile.csv_help')}</p>
          <Field label={t('reconcile.col_date')} required><Input value={colDate} onChange={(e) => setColDate(e.target.value)} placeholder="Data" /></Field>
          <Field label={t('reconcile.col_description')} required><Input value={colDesc} onChange={(e) => setColDesc(e.target.value)} placeholder="Histórico" /></Field>
          <Field label={t('reconcile.col_amount')}><Input value={colAmount} onChange={(e) => setColAmount(e.target.value)} placeholder="Valor" /></Field>
          <Field label={t('reconcile.col_debit')}><Input value={colDebit} onChange={(e) => setColDebit(e.target.value)} /></Field>
          <Field label={t('reconcile.col_credit')}><Input value={colCredit} onChange={(e) => setColCredit(e.target.value)} /></Field>
          <Field label={t('reconcile.delimiter')}>
            <Select value={delimiter} onChange={(e) => setDelimiter(e.target.value as typeof delimiter)}>
              <option value=";">;</option><option value=",">,</option><option value="tab">Tab</option>
            </Select>
          </Field>
          <Field label={t('reconcile.date_format')}>
            <Select value={dateFormat} onChange={(e) => setDateFormat(e.target.value as typeof dateFormat)}>
              <option value="dmy">31/12/2026</option><option value="ymd">2026-12-31</option>
              <option value="dmy-dash">31-12-2026</option><option value="dmy2">31/12/26</option>
            </Select>
          </Field>
          <Field label={t('reconcile.decimal')}>
            <Select value={decimal} onChange={(e) => setDecimal(e.target.value as typeof decimal)}>
              <option value="comma">1.234,56</option><option value="dot">1234.56</option>
            </Select>
          </Field>
          <Field label={t('reconcile.skip_rows')}><Input type="number" min={0} max={100} value={skipRows} onChange={(e) => setSkipRows(e.target.value)} /></Field>
          <label className="flex items-center gap-2 self-end text-sm">
            <input type="checkbox" checked={hasHeader} onChange={(e) => setHasHeader(e.target.checked)} /> {t('reconcile.has_header')}
          </label>
        </div>
      ) : null}
      <FormError message={error ?? (m.importStatement.error ? errorMessage(m.importStatement.error) : null)} />
      <Button type="submit" disabled={m.importStatement.isPending}>
        {m.importStatement.isPending ? t('reconcile.importing') : t('reconcile.import')}
      </Button>
    </form>
  );
}

function GatewaySync({ hooks }: { hooks: FinanceHooks }) {
  const accounts = hooks.useAccounts({ active: true });
  const m = hooks.useReconciliationMutations();
  const [results, setResults] = React.useState<Record<string, GatewaySyncResult>>({});
  const gateways = (accounts.data ?? []).filter((a) => a.kind === 'gateway');
  if (gateways.length === 0) return null;
  return (
    <Card className="space-y-2 p-4">
      <h3 className="text-sm font-semibold">{t('reconcile.gateway_title')}</h3>
      <p className="text-xs text-muted-foreground">{t('reconcile.gateway_help')}</p>
      <FormError message={m.gatewaySync.error ? errorMessage(m.gatewaySync.error) : null} />
      {gateways.map((a) => {
        const r = results[a.id];
        return (
          <div key={a.id} className="space-y-1 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span>{a.name} <span className="text-xs text-muted-foreground">({a.gateway})</span></span>
              <Button
                size="sm"
                variant="outline"
                disabled={m.gatewaySync.isPending}
                onClick={async () => {
                  try {
                    const res = await m.gatewaySync.mutateAsync({ accountId: a.id });
                    setResults((prev) => ({ ...prev, [a.id]: res }));
                  } catch {
                    // Surfaced above.
                  }
                }}
              >
                {m.gatewaySync.isPending && m.gatewaySync.variables?.accountId === a.id ? t('reconcile.gateway_syncing') : t('reconcile.gateway_sync')}
              </Button>
            </div>
            {r ? (
              <div role="status" className="rounded-md bg-muted p-2 text-xs">
                {t('reconcile.gateway_result', { fetched: r.fetched, fees: r.booked_fees, transfers: r.booked_transfers, already: r.already_booked })}
                {r.status === 'partial' ? <div>{t('reconcile.gateway_partial')}</div> : null}
                {r.review_total > 0 ? (
                  <div className="mt-1">
                    <strong>{t('reconcile.gateway_review', { n: r.review_total })}</strong>
                    <ul className="list-disc pl-4">
                      {r.review.map((it) => (
                        <li key={it.id}>{formatDate(it.occurred_on)} · {it.description || it.kind} · {formatCents(it.amount_cents)} — {it.reason}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </Card>
  );
}

export function ReconciliationPage({ hooks, isAdmin = false }: ReconciliationPageProps) {
  const accounts = hooks.useAccounts({ active: true });
  const [accountId, setAccountId] = React.useState('');
  const [importId, setImportId] = React.useState('');
  const [matchStatus, setMatchStatus] = React.useState<MatchStatus | ''>('');
  const [page, setPage] = React.useState(1);
  const [lastImport, setLastImport] = React.useState<StatementImportResult | null>(null);
  const [picking, setPicking] = React.useState<StatementLine | null>(null);

  const statements = hooks.useStatements({ account_id: accountId || undefined });
  const lines = hooks.useStatementLines(importId || undefined, { match_status: matchStatus, page, page_size: 50 });
  const m = hooks.useReconciliationMutations();

  const bankAccounts = accounts.data ?? [];
  const mutErr = m.match.error ?? m.ignore.error;

  async function doMatch(line: StatementLine, entryId: string) {
    try {
      await m.match.mutateAsync({ lineId: line.id, entryId });
      setPicking(null);
    } catch {
      // Surfaced via `m.match.error`.
    }
  }

  let linesBody: React.ReactNode = null;
  if (importId) {
    if (lines.showSkeleton) linesBody = <ListSkeleton rows={5} />;
    else if (lines.isError && !lines.data) {
      linesBody = <RetryError message={`${t('common.error_loading')}: ${errorMessage(lines.error)}`} onRetry={() => lines.refetch()} retryLabel={t('common.retry')} />;
    } else {
      const rows = lines.data?.data ?? [];
      linesBody = rows.length === 0 ? (
        <EmptyState message={t('reconcile.lines_empty')} />
      ) : (
        <ul className="divide-y rounded-md border text-sm">
          {rows.map((l) => {
            const pending = l.match_status === 'unmatched' || l.match_status === 'suggested';
            return (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <span className="min-w-0 space-y-0.5">
                  <span className="block">{formatDate(l.posted_on)} · {l.description || '—'}</span>
                  {l.suggested_entry_id && pending ? <SuggestedEntry hooks={hooks} entryId={l.suggested_entry_id} /> : null}
                </span>
                <span className="flex items-center gap-2">
                  <span className={l.amount_cents < 0 ? 'font-medium text-destructive' : 'font-medium'}>{formatCents(l.amount_cents)}</span>
                  <StatusBadge status={l.match_status} />
                  {isAdmin && pending ? (
                    <>
                      {l.suggested_entry_id ? (
                        <Button size="sm" disabled={m.match.isPending} onClick={() => doMatch(l, l.suggested_entry_id as string)}>{t('reconcile.accept_suggestion')}</Button>
                      ) : null}
                      <Button size="sm" variant="outline" onClick={() => setPicking(l)}>{t('reconcile.choose_entry')}</Button>
                      <Button size="sm" variant="ghost" disabled={m.ignore.isPending} onClick={() => m.ignore.mutate(l.id)}>{t('reconcile.ignore')}</Button>
                    </>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      );
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t('reconcile.title')} subtitle={t('reconcile.subtitle')} />
      <div className="max-w-sm">
        <Field label={t('report.account')}>
          <Select value={accountId} onChange={(e) => { setAccountId(e.target.value); setImportId(''); setPage(1); }}>
            <option value="">{t('reconcile.all_accounts')}</option>
            {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </Field>
      </div>
      {isAdmin ? (
        <ImportForm hooks={hooks} accountId={accountId} onImported={(r) => { setLastImport(r); setImportId(r.import.id); setPage(1); }} />
      ) : null}
      {lastImport ? (
        <Notice>
          {t('reconcile.import_result', { lines: lastImport.lines, dup: lastImport.duplicates_skipped, sug: lastImport.suggested })}
        </Notice>
      ) : null}

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t('reconcile.imports_title')}</h3>
        {statements.showSkeleton ? <ListSkeleton rows={2} /> : statements.isError && !statements.data ? (
          <RetryError message={`${t('common.error_loading')}: ${errorMessage(statements.error)}`} onRetry={() => statements.refetch()} retryLabel={t('common.retry')} />
        ) : (statements.data?.data ?? []).length === 0 ? (
          <EmptyState message={t('reconcile.imports_empty')} />
        ) : (
          <ul className="divide-y rounded-md border text-sm">
            {(statements.data?.data ?? []).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 p-2">
                <span>
                  {s.filename} <span className="text-xs text-muted-foreground">
                    {s.format.toUpperCase()}{s.period_start ? ` · ${formatDate(s.period_start)} – ${formatDate(s.period_end)}` : ''}
                  </span>
                </span>
                <Button size="sm" variant={importId === s.id ? 'primary' : 'outline'} aria-pressed={importId === s.id} onClick={() => { setImportId(s.id); setPage(1); }}>
                  {t('reconcile.see_lines')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {importId ? (
        <div className="space-y-2" aria-busy={lines.isRefreshing}>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{t('reconcile.lines_title')}</h3>
            <Select aria-label={t('reconcile.filter_status')} className="w-48" value={matchStatus} onChange={(e) => { setMatchStatus(e.target.value as MatchStatus | ''); setPage(1); }}>
              <option value="">{t('common.all')}</option>
              {MATCH_STATUSES.map((s) => <option key={s} value={s}>{t(`match_status.${s}`)}</option>)}
            </Select>
          </div>
          <RefreshingBar active={lines.isRefreshing} label={t('common.refreshing')} />
          <FormError message={mutErr ? errorMessage(mutErr) : null} />
          {linesBody}
          <Pager page={page} totalPages={totalPagesOf(lines.data?.pagination)} onPage={setPage} />
        </div>
      ) : null}

      {isAdmin ? <GatewaySync hooks={hooks} /> : null}
      {picking ? (
        <MatchPicker hooks={hooks} line={picking} pending={m.match.isPending} onClose={() => setPicking(null)} onPick={(e) => doMatch(picking, e.id)} />
      ) : null}
    </section>
  );
}
