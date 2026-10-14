/** `<StockAdjustDialog/>` — inventory count: type what was COUNTED; the server books the signed difference. */
import * as React from 'react';
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, FormError, Input, Textarea } from './controls';
import { formatQty, parseQty, shortId } from './format';
import { parseMoneyToCents } from '../commerce/format';
import { inventoryErrorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';

export interface StockAdjustDialogProps extends InventoryOrganProps {
  open: boolean;
  onClose: () => void;
  itemId: string;
  warehouseId: string;
  currentOnHand: number;
  onDone?: () => void;
}

export function StockAdjustDialog({ hooks, t = defaultInventoryT, locale, itemLabel = shortId, open, onClose, itemId, warehouseId, currentOnHand, onDone }: StockAdjustDialogProps) {
  const { adjust } = hooks.useStockMutations();
  const [counted, setCounted] = React.useState('');
  const [cost, setCost] = React.useState('');
  const [note, setNote] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  const parsed = parseQty(counted);
  const delta = parsed === null ? null : Number(parsed) - currentOnHand;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (parsed === null) {
      setErr(t('adjust.invalid'));
      return;
    }
    const body: Parameters<typeof adjust.mutateAsync>[0] = { item_id: itemId, warehouse_id: warehouseId, counted_qty: parsed };
    if (delta !== null && delta > 0 && cost.trim()) {
      const cents = parseMoneyToCents(cost);
      if (cents === null) {
        setErr(t('error.quantidade_invalida'));
        return;
      }
      body.unit_cost_cents = cents;
    }
    if (note.trim()) body.note = note.trim();
    setErr(null);
    try {
      await adjust.mutateAsync(body);
      onDone?.();
      onClose();
    } catch (e) {
      setErr(inventoryErrorMessage(e, t));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('adjust.title')}>
      <form onSubmit={submit}>
        <DialogHeader>
          <div>
            <h3 className="text-sm font-semibold">{t('adjust.title')}</h3>
            <p className="text-xs text-muted-foreground">{itemLabel(itemId)}</p>
          </div>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <p className="text-sm">{t('adjust.current', { qty: formatQty(currentOnHand, locale) })}</p>
          <Field label={t('adjust.counted')} required>
            <Input inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} autoFocus />
          </Field>
          {delta !== null && delta !== 0 ? <p className="text-sm" data-testid="adjust-delta">{t('adjust.delta', { delta: `${delta > 0 ? '+' : ''}${formatQty(delta, locale)}` })}</p> : null}
          {delta !== null && delta > 0 ? (
            <Field label={t('adjust.cost')}>
              <Input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
            </Field>
          ) : null}
          <Field label={t('adjust.note')}>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <FormError message={err} />
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button onClick={onClose} disabled={adjust.isPending}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" disabled={adjust.isPending}>
            {adjust.isPending ? t('common.saving') : t('adjust.submit')}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
