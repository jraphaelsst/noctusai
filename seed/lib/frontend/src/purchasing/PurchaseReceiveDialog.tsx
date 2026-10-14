/**
 * `<PurchaseReceiveDialog/>` — receive (part of) an order. One quantity per open line, defaulting to the whole open balance;
 * the server re-checks against the locked balance (`recebimento_excede_pedido`). One idempotency key per open dialog, so a
 * retried submit is a replay and never a second receipt. When the receipt was committed but stock / payables did not finish,
 * the warning is shown with a repost button instead of pretending success.
 */
import * as React from 'react';
import { Field, FormError, Input, Textarea } from '../organ-kit';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { formatQty, newIdempotencyKey, parseQty, qtyToWire } from './format';
import { purchasingErrorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';
import type { PurchaseOrder, PurchaseOrderLine, PurchaseReceiveResult } from './types';

export interface PurchaseReceiveDialogProps extends PurchasingOrganProps {
  open: boolean;
  onClose: () => void;
  /** The order DETAIL (with `lines`). */
  order: Pick<PurchaseOrder, 'id' | 'number' | 'lines'>;
  onDone?: (receipt: PurchaseReceiveResult) => void;
}

const openQty = (l: PurchaseOrderLine) => Math.max(0, Number(l.qty) - Number(l.received_qty));
const today = () => new Date().toISOString().slice(0, 10);

export function PurchaseReceiveDialog({ hooks, t = defaultPurchasingT, locale, open, onClose, order, onDone }: PurchaseReceiveDialogProps) {
  const { receive, repost } = hooks.useReceiptMutations();
  const lines = React.useMemo(() => (order.lines ?? []).filter((l) => openQty(l) > 0), [order.lines]);
  const [qtys, setQtys] = React.useState<Record<string, string>>({});
  const [date, setDate] = React.useState(today);
  const [note, setNote] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<PurchaseReceiveResult | null>(null);
  const key = React.useRef<string>('');
  if (!key.current) key.current = newIdempotencyKey();

  const valueFor = (l: PurchaseOrderLine) => qtys[l.id] ?? qtyToWire(openQty(l));

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const picked: { order_line_id: string; qty: string }[] = [];
    for (const l of lines) {
      const raw = valueFor(l).trim();
      if (!raw || Number(raw) === 0) continue;
      const parsed = parseQty(raw);
      if (parsed === null || Number(parsed) <= 0) {
        setErr(t('receive.invalid'));
        return;
      }
      if (Number(parsed) > openQty(l) + 1e-9) {
        setErr(t('receive.exceeds'));
        return;
      }
      picked.push({ order_line_id: l.id, qty: parsed });
    }
    if (!picked.length) {
      setErr(t('receive.invalid'));
      return;
    }
    setErr(null);
    try {
      const out = await receive.mutateAsync({ orderId: order.id, received_on: date, note: note.trim() || undefined, idempotency_key: key.current, lines: picked });
      setResult(out);
      onDone?.(out);
      if (!out.posting_error) onClose();
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  async function retryPosting() {
    if (!result) return;
    setErr(null);
    try {
      const out = await repost.mutateAsync(result.id);
      setResult({ ...result, ...out });
      if (!out.posting_error) onClose();
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('receive.title', { number: order.number })}>
      <form onSubmit={submit}>
        <DialogHeader>
          <h3 className="text-sm font-semibold">{t('receive.title', { number: order.number })}</h3>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {lines.length === 0 ? (
            <p className="text-sm">{t('receive.nothing_open')}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1">{t('receive.line')}</th>
                  <th className="text-right">{t('receive.ordered')}</th>
                  <th className="text-right">{t('receive.received')}</th>
                  <th className="text-right">{t('receive.open')}</th>
                  <th className="w-28">{t('receive.qty')}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id} className="border-b" data-testid="receive-line">
                    <td className="py-1">{l.description}</td>
                    <td className="text-right">{formatQty(l.qty, locale)}</td>
                    <td className="text-right">{formatQty(l.received_qty, locale)}</td>
                    <td className="text-right">{formatQty(openQty(l), locale)}</td>
                    <td>
                      <Input aria-label={`${t('receive.qty')} ${l.description}`} inputMode="decimal" value={valueFor(l)} onChange={(e) => setQtys((q) => ({ ...q, [l.id]: e.target.value }))} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Field label={t('receive.date')}>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label={t('receive.note')}>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          {result?.posting_error ? (
            <div role="alert" className="space-y-2 text-sm" data-testid="posting-warning">
              <p>{t('receive.posting_warning', { error: result.posting_error })}</p>
              <Button type="button" variant="outline" disabled={repost.isPending} onClick={retryPosting}>{t('receipts.repost')}</Button>
            </div>
          ) : null}
          <FormError message={err} />
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" onClick={onClose} disabled={receive.isPending}>{result ? t('common.close') : t('common.cancel')}</Button>
          {!result ? (
            <Button type="submit" variant="primary" disabled={receive.isPending || lines.length === 0}>
              {receive.isPending ? t('common.saving') : t('receive.submit')}
            </Button>
          ) : null}
        </DialogFooter>
      </form>
    </Dialog>
  );
}
