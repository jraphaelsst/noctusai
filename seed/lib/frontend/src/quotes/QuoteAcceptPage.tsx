/**
 * `<QuoteAcceptPage/>` — the customer's page behind the signed accept link. NO login, NO host chrome: storefront-style,
 * one self-contained document (the offer, its lines, totals, terms) and the decision.
 *
 * * Consent is explicit: the customer types their name and ticks "Li e aceito"; the page shows the exact sentence the
 *   server will record (the server authors the template, so what is shown is what is stored).
 * * Every state is honest: skeleton on first load; a bad / expired link says so (no retry loop — it is an answer);
 *   an expired / superseded / already-decided quote shows that, with no decision form (a lying "Aceitar" button
 *   over a quote that refuses is the bug this prevents).
 * * It only ever renders what the server's allow-list returned: no document, e-mail, phone or internal id exists here.
 */
import * as React from 'react';
import { ApiError } from '../api';
import { Button, EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, Textarea } from './controls';
import { formatCents, formatDate, formatDateTime, formatQty } from './format';
import { quotesErrorMessage, type QuotesPublicHooks } from './hooks';
import { defaultQuotesT, type QuotesTranslate } from './i18n';
import { QuoteStatusChip } from './QuoteStatusChip';

export interface QuoteAcceptPageProps {
  hooks: QuotesPublicHooks;
  /** The signed token from the URL. */
  token: string;
  t?: QuotesTranslate;
  locale?: string;
}

export function QuoteAcceptPage({ hooks, token, t = defaultQuotesT, locale }: QuoteAcceptPageProps) {
  const view = hooks.usePublicQuote(token);
  const { accept, reject } = hooks.usePublicDecision(token);
  const [name, setName] = React.useState('');
  const [agree, setAgree] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  if (view.showSkeleton) {
    return (
      <main className="mx-auto max-w-3xl space-y-3 p-4" aria-busy="true" aria-label={t('accept.loading')}>
        <ListSkeleton rows={6} />
      </main>
    );
  }
  if (view.isError && !view.data) {
    const gone = view.error instanceof ApiError && view.error.status === 404;
    return (
      <main className="mx-auto max-w-3xl p-4">
        <EmptyState message={gone ? t('accept.invalid_link') : `${t('common.error_loading')}: ${quotesErrorMessage(view.error, t)}`} />
        {gone ? null : (
          <div className="text-center"><Button variant="outline" onClick={() => view.refetch()}>{t('common.retry')}</Button></div>
        )}
      </main>
    );
  }
  const q = view.data;
  if (!q) return null;

  const sentence = q.consent_template ? q.consent_template.replace('{name}', name.trim() || '…') : null;
  const cur = q.currency;
  const busy = accept.isPending || reject.isPending;

  async function onAccept(ev: React.FormEvent) {
    ev.preventDefault();
    setErr(null);
    try {
      await accept.mutateAsync({ name: name.trim(), agree });
    } catch (e) {
      setErr(quotesErrorMessage(e, t));
    }
  }
  async function onReject(ev: React.FormEvent) {
    ev.preventDefault();
    setErr(null);
    try {
      await reject.mutateAsync({ ...(name.trim().length >= 2 ? { name: name.trim() } : {}), ...(reason.trim() ? { reason: reason.trim() } : {}) });
    } catch (e) {
      setErr(quotesErrorMessage(e, t));
    }
  }

  let banner: React.ReactNode = null;
  if (q.decision?.decision === 'accepted') banner = <p role="status" className="rounded-md border p-3 text-sm font-medium">{t('accept.done_accepted', { date: formatDateTime(q.decision.decided_at, locale) })}</p>;
  else if (q.decision?.decision === 'rejected') banner = <p role="status" className="rounded-md border p-3 text-sm">{t('accept.done_rejected', { date: formatDateTime(q.decision.decided_at, locale) })}</p>;
  else if (q.status === 'expired') banner = <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm">{t('accept.expired')}</p>;
  else if (q.status === 'superseded') banner = <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm">{t('accept.superseded')}</p>;

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4" aria-busy={view.isRefreshing}>
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold">{t('accept.title', { number: q.number })}</h1>
          <QuoteStatusChip status={q.status} t={t} />
        </div>
        <p className="text-xs text-muted-foreground">
          {t('accept.version', { n: q.version })}
          {q.valid_until ? ` · ${t('accept.valid_until', { date: formatDate(q.valid_until) })}` : ''}
        </p>
        {q.title ? <p className="text-sm font-medium">{q.title}</p> : null}
        <p className="text-sm">{t('accept.for', { name: q.party_name })}</p>
        {q.issuer_name ? <p className="text-sm">{t('accept.from', { name: q.issuer_name })}</p> : null}
        <RefreshingBar active={view.isRefreshing} label={t('common.refreshing')} />
      </header>

      {banner}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('accept.col_item')}</th>
              <th className="p-2 text-right">{t('accept.col_qty')}</th>
              <th className="p-2 text-right">{t('accept.col_price')}</th>
              <th className="p-2 text-right">{t('accept.col_total')}</th>
            </tr>
          </thead>
          <tbody>
            {q.lines.map((l) => (
              <tr key={l.position} data-testid="public-line" className="border-b">
                <td className="p-2">{l.description}</td>
                <td className="p-2 text-right tabular-nums">{formatQty(l.qty, locale)} {l.unit}</td>
                <td className="p-2 text-right tabular-nums">{formatCents(l.unit_price_cents, cur, locale)}</td>
                <td className="p-2 text-right tabular-nums">{formatCents(l.total_cents, cur, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="ml-auto max-w-xs space-y-1 text-sm">
        <div className="flex justify-between"><dt>{t('accept.subtotal')}</dt><dd className="tabular-nums">{formatCents(q.subtotal_cents, cur, locale)}</dd></div>
        {q.discount_cents > 0 ? <div className="flex justify-between"><dt>{t('accept.discount')}</dt><dd className="tabular-nums">- {formatCents(q.discount_cents, cur, locale)}</dd></div> : null}
        <div className="flex justify-between text-base font-semibold"><dt>{t('accept.total')}</dt><dd className="tabular-nums" data-testid="public-total">{formatCents(q.total_cents, cur, locale)}</dd></div>
      </dl>
      {q.notes ? <section><h2 className="text-sm font-medium">{t('accept.notes')}</h2><p className="whitespace-pre-line text-sm">{q.notes}</p></section> : null}
      {q.terms ? <section><h2 className="text-sm font-medium">{t('accept.terms')}</h2><p className="whitespace-pre-line text-sm">{q.terms}</p></section> : null}
      <a className="text-sm underline" href={hooks.pdfUrl(token)} target="_blank" rel="noreferrer">{t('accept.pdf')}</a>

      {q.can_decide ? (
        <section className="space-y-3 rounded-md border p-4">
          <form onSubmit={onAccept} className="space-y-3" aria-label={t('accept.submit')}>
            <Field label={t('accept.name')} required>
              <Input value={name} maxLength={120} autoComplete="name" onChange={(e) => setName(e.target.value)} />
            </Field>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
              <span>{t('accept.agree')}</span>
            </label>
            {sentence ? <p className="text-xs text-muted-foreground">{t('accept.consent', { sentence })}</p> : null}
            <Button type="submit" variant="primary" disabled={busy || name.trim().length < 2 || !agree}>
              {accept.isPending ? t('accept.submitting') : t('accept.submit')}
            </Button>
          </form>
          {rejecting ? (
            <form onSubmit={onReject} className="space-y-2" aria-label={t('accept.reject_submit')}>
              <Field label={t('accept.reject_reason')}><Textarea rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
              <Button type="submit" variant="outline" disabled={busy}>{reject.isPending ? t('accept.submitting') : t('accept.reject_submit')}</Button>
            </form>
          ) : (
            <Button type="button" variant="ghost" size="sm" onClick={() => setRejecting(true)}>{t('accept.reject_toggle')}</Button>
          )}
          <FormError message={err} />
        </section>
      ) : null}
    </main>
  );
}
