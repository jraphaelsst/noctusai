/**
 * `<QuoteEditor/>` — create / edit a quote in a dialog: customer + priced lines (item or free text), general
 * discount, validity, terms, versions, and — once the quote left draft — the lifecycle actions.
 *
 * * A DRAFT is editable; anything else is read-only (the database freezes it) and offers "Nova versão".
 * * Live totals use the server's rounding (`previewTotals`), and say so: the server's numbers win on save.
 * * Money is typed in R$ and sent as integer cents; quantities are sent as decimal STRINGS.
 * * `canWrite` is UX only — the server enforces admin-only writes.
 */
import * as React from 'react';
import {
  Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, ErrorState, Field, FormError, Input, ListSkeleton, Select, Textarea,
} from './controls';
import { centsToInput, formatCents, formatDate, formatDateTime, formatQty, parseMoneyToCents, parseQty, previewTotals } from './format';
import { quotesErrorMessage, type QuotesHooks } from './hooks';
import { defaultQuotesT, type QuotesTranslate } from './i18n';
import { QuoteConversionChip, QuoteStatusChip } from './QuoteStatusChip';
import { QuoteSendDialog } from './QuoteSendDialog';
import {
  QUOTE_CONVERT_TO,
  type QuoteConvertTo,
  type QuoteInput,
  type QuoteItemOption,
  type QuoteLineInput,
  type QuoteLineKind,
  type QuotePartyOption,
  type QuoteRecord,
} from './types';

interface LineState {
  key: number;
  item_id: string;
  description: string;
  unit: string;
  kind: QuoteLineKind;
  qty: string;
  price: string;
  discount: string;
}

export interface QuoteEditorProps {
  hooks: QuotesHooks;
  t?: QuotesTranslate;
  locale?: string;
  open: boolean;
  /** `null` = a new quote. */
  quoteId: string | null;
  onClose: () => void;
  /** Called with the id of a quote the editor created / revised, so the host can follow it. */
  onOpenQuote?: (id: string) => void;
  canWrite?: boolean;
  parties?: QuotePartyOption[];
  items?: QuoteItemOption[];
  /** Where "Baixar PDF" points (default: the staff PDF route via the hooks). */
  pdfHref?: (id: string) => string;
}

let nextKey = 1;
const blankLine = (): LineState => ({ key: nextKey++, item_id: '', description: '', unit: 'UN', kind: 'goods', qty: '1', price: '', discount: '' });

function fromRecord(q: QuoteRecord): LineState[] {
  return (q.lines ?? []).map((l) => ({
    key: nextKey++,
    item_id: l.item_id ?? '',
    description: l.description,
    unit: l.unit,
    kind: l.kind,
    qty: formatQty(l.qty).replace(/\./g, ''),
    price: centsToInput(l.unit_price_cents),
    discount: l.discount_cents ? centsToInput(l.discount_cents) : '',
  }));
}

export function QuoteEditor({ hooks, t = defaultQuotesT, locale, open, quoteId, onClose, onOpenQuote, canWrite = false, parties = [], items = [], pdfHref }: QuoteEditorProps) {
  const detail = hooks.useQuote(quoteId);
  const m = hooks.useQuoteMutations();
  const quote = detail.data;

  const [partyId, setPartyId] = React.useState('');
  const [title, setTitle] = React.useState('');
  const [validUntil, setValidUntil] = React.useState('');
  const [notes, setNotes] = React.useState('');
  const [terms, setTerms] = React.useState('');
  const [discount, setDiscount] = React.useState('');
  const [convertTo, setConvertTo] = React.useState<QuoteConvertTo | ''>('');
  const [lines, setLines] = React.useState<LineState[]>(() => [blankLine()]);
  const [err, setErr] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [decisionName, setDecisionName] = React.useState('');
  const [rejectReason, setRejectReason] = React.useState('');

  // Hydrate the form from the server record ONCE per (quote, version of the row).
  const hydrated = React.useRef<string>('');
  React.useEffect(() => {
    if (!quote) return;
    const stamp = `${quote.id}:${quote.updated_at}`;
    if (hydrated.current === stamp) return;
    hydrated.current = stamp;
    setPartyId(quote.party_id);
    setTitle(quote.title ?? '');
    setValidUntil(quote.valid_until ?? '');
    setNotes(quote.notes ?? '');
    setTerms(quote.terms ?? '');
    setDiscount(quote.discount_cents ? centsToInput(quote.discount_cents) : '');
    setConvertTo(quote.convert_to ?? '');
    setLines(quote.lines?.length ? fromRecord(quote) : [blankLine()]);
  }, [quote]);

  const isNew = quoteId === null;
  const frozen = !!quote && quote.status !== 'draft';
  const readOnly = !canWrite || frozen;

  const parsedLines = lines.map((l) => ({
    qty: l.qty,
    unitPriceCents: parseMoneyToCents(l.price) ?? NaN,
    discountCents: l.discount.trim() ? parseMoneyToCents(l.discount) ?? NaN : 0,
  }));
  const totals = previewTotals(parsedLines, discount.trim() ? parseMoneyToCents(discount) ?? -1 : 0);
  const cur = quote?.currency ?? 'BRL';

  const setLine = (key: number, patch: Partial<LineState>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  function pickItem(key: number, itemId: string) {
    const it = items.find((i) => i.id === itemId);
    setLine(key, {
      item_id: itemId,
      ...(it ? { description: it.name, unit: it.unit ?? 'UN', kind: it.kind ?? 'goods', price: it.price_cents != null ? centsToInput(it.price_cents) : '' } : {}),
    });
  }

  function buildBody(): QuoteInput | null {
    if (!partyId) {
      setErr(t('editor.party_pick'));
      return null;
    }
    const out: QuoteLineInput[] = [];
    for (const l of lines) {
      const qty = parseQty(l.qty);
      const price = parseMoneyToCents(l.price);
      const disc = l.discount.trim() ? parseMoneyToCents(l.discount) : 0;
      if (qty === null || Number(qty) <= 0 || price === null || disc === null || (!l.item_id && !l.description.trim())) {
        setErr(t('error.linha_invalida'));
        return null;
      }
      out.push({
        ...(l.item_id ? { item_id: l.item_id } : {}),
        description: l.description.trim() || undefined,
        unit: l.unit.trim() || undefined,
        kind: l.kind,
        qty,
        unit_price_cents: price,
        discount_cents: disc,
      });
    }
    const general = discount.trim() ? parseMoneyToCents(discount) : 0;
    if (general === null) {
      setErr(t('error.desconto_invalido'));
      return null;
    }
    return {
      party_id: partyId,
      title: title.trim() || null,
      valid_until: validUntil || null,
      notes: notes.trim() || null,
      terms: terms.trim() || null,
      discount_cents: general,
      convert_to: convertTo || null,
      lines: out,
    };
  }

  async function run<T>(p: Promise<T>): Promise<T | undefined> {
    setErr(null);
    try {
      return await p;
    } catch (e) {
      setErr(quotesErrorMessage(e, t));
      return undefined;
    }
  }

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    const body = buildBody();
    if (!body) return;
    setErr(null);
    if (isNew) {
      const created = await run(m.create.mutateAsync(body));
      if (created) {
        onOpenQuote?.(created.id);
        if (!onOpenQuote) onClose();
      }
    } else if (quoteId) {
      const saved = await run(m.update.mutateAsync({ id: quoteId, ...body }));
      if (saved) onClose();
    }
  }

  async function revise() {
    if (!quoteId) return;
    const v = await run(m.newVersion.mutateAsync({ id: quoteId }));
    if (v) onOpenQuote?.(v.id);
  }

  async function remove() {
    if (!quoteId) return;
    const ok = await run(m.remove.mutateAsync(quoteId).then(() => true));
    if (ok) onClose();
  }

  const party = parties.find((p) => p.id === partyId);
  const headerTitle = quote ? t('editor.title_edit', { number: quote.number, version: quote.version }) : t('editor.title_new');
  const busy = m.create.isPending || m.update.isPending;

  let body: React.ReactNode;
  if (!isNew && detail.showSkeleton) {
    body = <ListSkeleton rows={5} />;
  } else if (!isNew && detail.isError && !quote) {
    body = (
      <div className="space-y-2 text-center">
        <ErrorState message={`${t('common.error_loading')}: ${quotesErrorMessage(detail.error, t)}`} />
        <Button variant="outline" onClick={() => detail.refetch()}>{t('common.retry')}</Button>
      </div>
    );
  } else {
    body = (
      <div className="space-y-4">
        {quote ? (
          <div className="flex flex-wrap items-center gap-2">
            <QuoteStatusChip status={quote.status} t={t} />
            <QuoteConversionChip status={quote.conversion_status} t={t} />
            {quote.status === 'accepted' && quote.accepted_at ? <span className="text-xs">{t('editor.accepted_by', { name: quote.party?.legal_name ?? '', date: formatDateTime(quote.accepted_at, locale) })}</span> : null}
            {quote.status === 'rejected' && quote.rejection_reason ? <span className="text-xs">{t('editor.rejected_reason', { reason: quote.rejection_reason })}</span> : null}
          </div>
        ) : null}
        {frozen ? <p role="note" className="rounded-md border p-2 text-xs">{t('editor.frozen')}</p> : null}
        {!canWrite ? <p role="note" className="text-xs text-muted-foreground">{t('editor.read_only')}</p> : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.party')} required>
            {parties.length ? (
              <Select value={partyId} disabled={readOnly} onChange={(e) => setPartyId(e.target.value)}>
                <option value="">{t('editor.party_pick')}</option>
                {parties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            ) : (
              <Input value={quote?.party?.legal_name ?? partyId} disabled={readOnly} onChange={(e) => setPartyId(e.target.value)} />
            )}
          </Field>
          <Field label={t('editor.title')}><Input value={title} disabled={readOnly} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label={t('editor.valid_until')}><Input type="date" value={validUntil} disabled={readOnly} onChange={(e) => setValidUntil(e.target.value)} /></Field>
          <Field label={t('editor.convert_to')}>
            <Select value={convertTo} disabled={readOnly} onChange={(e) => setConvertTo(e.target.value as QuoteConvertTo | '')}>
              <option value="">{t('convert_to.auto')}</option>
              {QUOTE_CONVERT_TO.map((c) => <option key={c} value={c}>{t(`convert_to.${c}`)}</option>)}
            </Select>
          </Field>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t('editor.lines')}</legend>
          {lines.map((l, i) => (
            <div key={l.key} data-testid="quote-line" className="grid items-end gap-2 rounded-md border p-2 sm:grid-cols-12">
              {items.length ? (
                <div className="sm:col-span-3">
                  <Field label={t('editor.line_item')}>
                    <Select value={l.item_id} disabled={readOnly} onChange={(e) => pickItem(l.key, e.target.value)}>
                      <option value="">{t('editor.line_free')}</option>
                      {items.map((it) => <option key={it.id} value={it.id}>{it.name}</option>)}
                    </Select>
                  </Field>
                </div>
              ) : null}
              <div className={items.length ? 'sm:col-span-4' : 'sm:col-span-6'}>
                <Field label={t('editor.line_description')}><Input value={l.description} disabled={readOnly} onChange={(e) => setLine(l.key, { description: e.target.value })} /></Field>
              </div>
              <div className="sm:col-span-2">
                <Field label={t('editor.line_kind')}>
                  <Select value={l.kind} disabled={readOnly} onChange={(e) => setLine(l.key, { kind: e.target.value as QuoteLineKind })}>
                    <option value="goods">{t('editor.line_goods')}</option>
                    <option value="service">{t('editor.line_service')}</option>
                  </Select>
                </Field>
              </div>
              <div className="sm:col-span-1"><Field label={t('editor.line_qty')}><Input inputMode="decimal" value={l.qty} disabled={readOnly} onChange={(e) => setLine(l.key, { qty: e.target.value })} /></Field></div>
              <div className="sm:col-span-1"><Field label={t('editor.line_price')}><Input inputMode="decimal" value={l.price} disabled={readOnly} onChange={(e) => setLine(l.key, { price: e.target.value })} /></Field></div>
              <div className="sm:col-span-1"><Field label={t('editor.line_discount')}><Input inputMode="decimal" value={l.discount} disabled={readOnly} onChange={(e) => setLine(l.key, { discount: e.target.value })} /></Field></div>
              <div className="flex items-center justify-between gap-2 sm:col-span-12">
                <span className="text-xs text-muted-foreground">
                  {t('editor.line_total')}: <b className="tabular-nums">{totals.lineTotals[i] == null ? '—' : formatCents(totals.lineTotals[i], cur, locale)}</b>
                </span>
                {!readOnly && lines.length > 1 ? (
                  <Button type="button" size="sm" variant="ghost" aria-label={`${t('editor.remove_line')} ${i + 1}`} onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}>
                    {t('editor.remove_line')}
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
          {!readOnly ? <Button type="button" size="sm" variant="outline" onClick={() => setLines((ls) => [...ls, blankLine()])}>{t('editor.add_line')}</Button> : null}
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.discount')}><Input inputMode="decimal" value={discount} disabled={readOnly} onChange={(e) => setDiscount(e.target.value)} /></Field>
          <dl className="space-y-1 text-sm" aria-label={t('editor.total')}>
            <div className="flex justify-between"><dt>{t('editor.subtotal')}</dt><dd className="tabular-nums" data-testid="quote-subtotal">{formatCents(totals.subtotal, cur, locale)}</dd></div>
            <div className="flex justify-between"><dt>{t('editor.discount_label')}</dt><dd className="tabular-nums">{formatCents(Math.max(0, totals.discount), cur, locale)}</dd></div>
            <div className="flex justify-between font-semibold"><dt>{t('editor.total')}</dt><dd className="tabular-nums" data-testid="quote-total">{totals.invalid ? '—' : formatCents(totals.total, cur, locale)}</dd></div>
            <p className="text-xs text-muted-foreground">{t('editor.totals_note')}</p>
          </dl>
        </div>
        <Field label={t('editor.notes')}><Textarea rows={2} value={notes} disabled={readOnly} onChange={(e) => setNotes(e.target.value)} /></Field>
        <Field label={t('editor.terms')}><Textarea rows={3} value={terms} disabled={readOnly} onChange={(e) => setTerms(e.target.value)} /></Field>

        {quote ? <Versions hooks={hooks} quote={quote} t={t} onOpenQuote={onOpenQuote} /> : null}

        {quote && canWrite && (quote.status === 'sent' || quote.status === 'viewed') ? (
          <fieldset className="space-y-2 rounded-md border p-3">
            <legend className="px-1 text-xs font-medium">{t('editor.decision')}</legend>
            <Field label={t('editor.decision_name')}><Input value={decisionName} onChange={(e) => setDecisionName(e.target.value)} /></Field>
            <Field label={t('editor.reject_reason')}><Input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} /></Field>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="primary" disabled={m.accept.isPending || decisionName.trim().length < 2}
                onClick={() => run(m.accept.mutateAsync({ id: quote.id, signer_name: decisionName.trim() }))}>{t('editor.accept_staff')}</Button>
              <Button type="button" size="sm" variant="outline" disabled={m.reject.isPending || !rejectReason.trim()}
                onClick={() => run(m.reject.mutateAsync({ id: quote.id, reason: rejectReason.trim(), signer_name: decisionName.trim() || undefined }))}>{t('editor.reject_staff')}</Button>
            </div>
          </fieldset>
        ) : null}

        {quote && canWrite && quote.status === 'accepted' && (quote.conversion_status === 'failed' || quote.conversion_status === 'skipped' || quote.conversion_status === 'pending') ? (
          <div className="space-y-1">
            {quote.conversion_error ? <p role="alert" className="text-xs text-destructive">{quote.conversion_error}</p> : null}
            <Button type="button" size="sm" variant="outline" disabled={m.convert.isPending} onClick={() => run(m.convert.mutateAsync(quote.id))}>{t('editor.convert_retry')}</Button>
          </div>
        ) : null}

        <FormError message={err} />
      </div>
    );
  }

  return (
    <>
      <Dialog open={open} onClose={onClose} title={headerTitle} className="max-w-4xl">
        <form onSubmit={save} aria-label={headerTitle}>
          <DialogHeader>
            <div>
              <h3 className="text-sm font-semibold">{headerTitle}</h3>
              {quote?.valid_until ? <p className="text-xs text-muted-foreground">{t('accept.valid_until', { date: formatDate(quote.valid_until) })}</p> : null}
              {party && isNew ? <p className="text-xs text-muted-foreground">{party.name}</p> : null}
            </div>
          </DialogHeader>
          <DialogBody>{body}</DialogBody>
          <DialogFooter className="items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              {quote ? <a className="text-sm underline" href={(pdfHref ?? hooks.pdfUrl)(quote.id)} target="_blank" rel="noreferrer">{t('editor.pdf')}</a> : null}
              {quote && canWrite && frozen && quote.is_current && quote.status !== 'accepted' ? (
                <Button type="button" size="sm" variant="outline" disabled={m.newVersion.isPending} onClick={revise}>{t('editor.new_version')}</Button>
              ) : null}
              {quote && canWrite && quote.status === 'draft' ? (
                confirmDelete ? (
                  <Button type="button" size="sm" variant="destructive" onClick={remove}>{t('editor.delete_confirm_yes')}</Button>
                ) : (
                  <Button type="button" size="sm" variant="ghost" onClick={() => setConfirmDelete(true)}>{t('editor.delete')}</Button>
                )
              ) : null}
              {quote && canWrite && (quote.status === 'draft' || quote.status === 'sent' || quote.status === 'viewed') ? (
                <Button type="button" size="sm" variant="outline" onClick={() => setSending(true)}>{t('editor.send')}</Button>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>{t('common.close')}</Button>
              {!readOnly ? <Button type="submit" variant="primary" disabled={busy}>{busy ? t('common.saving') : t('common.save')}</Button> : null}
            </div>
          </DialogFooter>
        </form>
      </Dialog>
      {quote && sending ? (
        <QuoteSendDialog hooks={hooks} t={t} open quoteId={quote.id} defaultTo={quote.party?.email} onClose={() => setSending(false)} />
      ) : null}
    </>
  );
}

function Versions({ hooks, quote, t, onOpenQuote }: { hooks: QuotesHooks; quote: QuoteRecord; t: QuotesTranslate; onOpenQuote?: (id: string) => void }) {
  const list = hooks.useQuotes({ q: quote.number, include_versions: true, page_size: 50 });
  const versions = (list.data?.data ?? []).filter((v) => v.root_id === quote.root_id).sort((a, b) => b.version - a.version);
  if (versions.length < 2) return null;
  return (
    <section aria-label={t('editor.versions')} className="space-y-1">
      <h4 className="text-xs font-medium">{t('editor.versions')}</h4>
      <ul className="space-y-1 text-sm">
        {versions.map((v) => (
          <li key={v.id} className="flex items-center gap-2">
            <button type="button" className="underline disabled:no-underline" disabled={v.id === quote.id || !onOpenQuote} onClick={() => onOpenQuote?.(v.id)}>
              {t('table.version', { n: v.version })}
            </button>
            <QuoteStatusChip status={v.status} t={t} />
            {v.is_current ? <Badge variant="outline">{t('editor.version_current')}</Badge> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
