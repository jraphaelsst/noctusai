/** `<TransferDialog/>` — move stock between two warehouses (at the origin's average cost). */
import * as React from 'react';
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, FormError, Input, Select, Textarea } from './controls';
import { formatQty, parseQty, shortId } from './format';
import { inventoryErrorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';

export interface TransferDialogProps extends InventoryOrganProps {
  open: boolean;
  onClose: () => void;
  itemId: string;
  fromWarehouseId: string;
  /** Available (on hand − reserved) at the origin, shown as a hint; the server is the authority. */
  available?: number;
  onDone?: () => void;
}

export function TransferDialog({ hooks, t = defaultInventoryT, locale, itemLabel = shortId, open, onClose, itemId, fromWarehouseId, available, onDone }: TransferDialogProps) {
  const { transfer } = hooks.useStockMutations();
  const warehouses = hooks.useWarehouses({ active: true });
  const targets = (warehouses.data ?? []).filter((w) => w.id !== fromWarehouseId);
  const [to, setTo] = React.useState('');
  const [qty, setQty] = React.useState('');
  const [note, setNote] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const fromName = (warehouses.data ?? []).find((w) => w.id === fromWarehouseId)?.name ?? shortId(fromWarehouseId);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const q = parseQty(qty);
    if (q === null || Number(q) <= 0) {
      setErr(t('transfer.invalid'));
      return;
    }
    const dest = to || targets[0]?.id;
    if (!dest || dest === fromWarehouseId) {
      setErr(t('transfer.same'));
      return;
    }
    setErr(null);
    try {
      await transfer.mutateAsync({ item_id: itemId, from_warehouse_id: fromWarehouseId, to_warehouse_id: dest, qty: q, ...(note.trim() ? { note: note.trim() } : {}) });
      onDone?.();
      onClose();
    } catch (e) {
      setErr(inventoryErrorMessage(e, t));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('transfer.title')}>
      <form onSubmit={submit}>
        <DialogHeader>
          <div>
            <h3 className="text-sm font-semibold">{t('transfer.title')}</h3>
            <p className="text-xs text-muted-foreground">{itemLabel(itemId)}</p>
          </div>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <p className="text-sm">
            {t('transfer.from')}: <strong>{fromName}</strong>
            {available != null ? ` · ${t('transfer.available', { qty: formatQty(available, locale) })}` : ''}
          </p>
          <Field label={t('transfer.to')} required>
            <Select value={to || targets[0]?.id || ''} onChange={(e) => setTo(e.target.value)}>
              {targets.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('transfer.qty')} required>
            <Input inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} autoFocus />
          </Field>
          <Field label={t('transfer.note')}>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <FormError message={err} />
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button onClick={onClose} disabled={transfer.isPending}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" disabled={transfer.isPending || targets.length === 0}>
            {transfer.isPending ? t('common.saving') : t('transfer.submit')}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
