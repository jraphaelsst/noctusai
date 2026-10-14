/**
 * `<PurchaseOrderEditor/>` — create / edit a DRAFT purchase order: supplier (parties organ picker, or free text), item lines
 * (items organ picker), payment terms (installments + first due + interval -> the payables a receipt generates), freight /
 * other / discount, with the totals the server will compute (`round(qty × cost)` per line, half away from zero).
 *
 * The cross-organ pickers are OPTIONAL props and rendered as sub-components, so a host without the parties / items /
 * inventory organs gets free-text supplier, manual lines and no warehouse field — no conditional hooks. A non-draft order opens
 * read-only (the server refuses edits with `pedido_nao_editavel` anyway).
 */
import * as React from 'react';
import type { InventoryHooks } from '../inventory/hooks';
import type { ItemsHooks } from '../items/hooks';
import type { PartiesHooks } from '../parties/hooks';
import { Card, EmptyState, Field, FormError, Input, ListSkeleton, RetryError, Select, Textarea } from '../organ-kit';
import { Button } from '../design-system/ui/Button';
import { formatCents, lineTotalCents, parseMoneyToCents, parseQty } from './format';
import { errorMessage } from '../organ-kit';
import { purchasingErrorMessage } from './hooks';
import { defaultPurchasingT } from './i18n';
import type { PurchasingOrganProps } from './shared';
import type { PurchaseOrder, PurchaseOrderInput } from './types';

export interface PurchaseOrderEditorProps extends PurchasingOrganProps {
  /** Edit this draft; omit / null for a new order. */
  orderId?: string | null;
  partiesHooks?: PartiesHooks;
  itemsHooks?: ItemsHooks;
  inventoryHooks?: InventoryHooks;
  onSaved?: (order: PurchaseOrder) => void;
  onCancel?: () => void;
}

interface LineDraft {
  key: string;
  itemId: string | null;
  description: string;
  unit: string | null;
  qty: string;
  cost: string;
}

let seq = 0;
const nextKey = () => `l${++seq}`;
const centsToInput = (cents: number) => (cents / 100).toFixed(2).replace('.', ',');

function SupplierPicker({ partiesHooks, onPick, t }: { partiesHooks: PartiesHooks; onPick: (id: string, name: string) => void; t: PurchasingOrganProps['t'] & object }) {
  const [q, setQ] = React.useState('');
  const found = partiesHooks.useParties({ q: q.trim() || undefined, role: 'supplier', active: 'active', page_size: 8 });
  const rows = found.data?.data ?? [];
  return (
    <div className="space-y-1">
      <Input aria-label={t('editor.supplier')} placeholder={t('editor.supplier_search')} value={q} onChange={(e) => setQ(e.target.value)} />
      {found.showSkeleton ? <ListSkeleton rows={2} /> : null}
      <ul className="max-h-40 overflow-auto text-sm">
        {rows.map((p) => (
          <li key={p.id}>
            <button type="button" className="w-full px-2 py-1 text-left hover:bg-muted" onClick={() => onPick(p.id, p.trade_name || p.legal_name)}>
              {p.trade_name || p.legal_name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemSearch({ itemsHooks, onPick, t }: { itemsHooks: ItemsHooks; onPick: (line: Omit<LineDraft, 'key'>) => void; t: PurchasingOrganProps['t'] & object }) {
  const [q, setQ] = React.useState('');
  const found = itemsHooks.useItems({ q: q.trim() || undefined, active: 'true' });
  const rows = found.data?.data ?? [];
  return (
    <div className="space-y-1">
      <Input aria-label={t('editor.add_item')} placeholder={t('editor.item_search')} value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="max-h-40 overflow-auto text-sm">
        {(q.trim() ? rows : rows.slice(0, 5)).map((it) => (
          <li key={it.id}>
            <button
              type="button"
              className="w-full px-2 py-1 text-left hover:bg-muted"
              onClick={() => onPick({ itemId: it.id, description: it.name, unit: it.unit, qty: '1', cost: centsToInput(it.cost_cents) })}
            >
              {it.sku} — {it.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function WarehouseSelect({ inventoryHooks, value, onChange, t }: { inventoryHooks: InventoryHooks; value: string; onChange: (v: string) => void; t: PurchasingOrganProps['t'] & object }) {
  const warehouses = inventoryHooks.useWarehouses({ active: true });
  const list = warehouses.data ?? [];
  React.useEffect(() => {
    if (!value && list.length) onChange((list.find((w) => w.is_default) ?? list[0]).id);
  }, [value, list, onChange]);
  return (
    <Field label={t('editor.warehouse')} required>
      <Select aria-label={t('editor.warehouse')} value={value} onChange={(e) => onChange(e.target.value)}>
        {list.map((w) => (
          <option key={w.id} value={w.id}>{w.name}</option>
        ))}
      </Select>
    </Field>
  );
}

export function PurchaseOrderEditor({ hooks, t = defaultPurchasingT, locale, orderId, partiesHooks, itemsHooks, inventoryHooks, onSaved, onCancel }: PurchaseOrderEditorProps) {
  const existing = hooks.usePurchaseOrder(orderId);
  const { save } = hooks.usePurchaseOrderMutations();
  const [partyId, setPartyId] = React.useState<string | null>(null);
  const [supplier, setSupplier] = React.useState('');
  const [warehouseId, setWarehouseId] = React.useState('');
  const [expected, setExpected] = React.useState('');
  const [lines, setLines] = React.useState<LineDraft[]>([]);
  const [freight, setFreight] = React.useState('');
  const [other, setOther] = React.useState('');
  const [discount, setDiscount] = React.useState('');
  const [installments, setInstallments] = React.useState('1');
  const [firstDue, setFirstDue] = React.useState('30');
  const [interval, setIntervalDays] = React.useState('30');
  const [notes, setNotes] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const loadedFor = React.useRef<string | null>(null);

  const loaded = existing.data;
  React.useEffect(() => {
    if (!loaded || loadedFor.current === `${loaded.id}:${loaded.updated_at}`) return;
    loadedFor.current = `${loaded.id}:${loaded.updated_at}`;
    setPartyId(loaded.party_id);
    setSupplier(loaded.supplier_name);
    setWarehouseId(loaded.warehouse_id ?? '');
    setExpected(loaded.expected_date ?? '');
    setLines((loaded.lines ?? []).map((l) => ({ key: nextKey(), itemId: l.item_id, description: l.description, unit: l.unit, qty: String(Number(l.qty)), cost: centsToInput(l.unit_cost_cents) })));
    setFreight(loaded.freight_cents ? centsToInput(loaded.freight_cents) : '');
    setOther(loaded.other_cents ? centsToInput(loaded.other_cents) : '');
    setDiscount(loaded.discount_cents ? centsToInput(loaded.discount_cents) : '');
    setInstallments(String(loaded.installments_count));
    setFirstDue(String(loaded.first_due_days));
    setIntervalDays(String(loaded.interval_days));
    setNotes(loaded.notes ?? '');
  }, [loaded]);

  const money = (raw: string): number | null => (raw.trim() ? parseMoneyToCents(raw) : 0);
  const freightC = money(freight);
  const otherC = money(other);
  const discountC = money(discount);
  const goods = lines.reduce((sum, l) => {
    const q = parseQty(l.qty);
    const c = parseMoneyToCents(l.cost);
    return sum + (q !== null && c !== null ? lineTotalCents(q, c) : 0);
  }, 0);
  const total = goods + (freightC ?? 0) + (otherC ?? 0) - (discountC ?? 0);

  const setLine = (key: string, patch: Partial<LineDraft>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const addLine = (line: Omit<LineDraft, 'key'>) => setLines((ls) => [...ls, { key: nextKey(), ...line }]);

  if (orderId && existing.showSkeleton) return <ListSkeleton rows={6} />;
  if (orderId && existing.isError && !existing.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(existing.error)}`} onRetry={() => existing.refetch()} retryLabel={t('common.retry')} />;
  }
  const readOnly = !!loaded && loaded.status !== 'draft';

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!partyId && !supplier.trim()) return setErr(t('editor.invalid.supplier'));
    if (inventoryHooks && !warehouseId) return setErr(t('editor.invalid.warehouse'));
    if (freightC === null || otherC === null || discountC === null) return setErr(t('editor.invalid.money'));
    const n = Number(installments);
    const first = Number(firstDue);
    const gap = Number(interval);
    if (![n, first, gap].every(Number.isInteger) || n < 1 || n > 120 || first < 0 || gap < 0 || (n > 1 && gap < 1)) return setErr(t('editor.invalid.terms'));
    const payloadLines: PurchaseOrderInput['lines'] = [];
    for (const l of lines) {
      const q = parseQty(l.qty);
      const c = parseMoneyToCents(l.cost);
      if (q === null || Number(q) <= 0 || c === null || !l.description.trim()) return setErr(t('editor.invalid.lines'));
      payloadLines.push({ item_id: l.itemId, description: l.description.trim(), unit: l.unit, qty: q, unit_cost_cents: c });
    }
    if (!payloadLines.length) return setErr(t('editor.invalid.lines'));
    setErr(null);
    try {
      const saved = await save.mutateAsync({
        id: orderId ?? undefined,
        party_id: partyId,
        supplier_name: partyId ? undefined : supplier.trim(),
        warehouse_id: warehouseId || null,
        expected_date: expected || null,
        installments_count: n,
        first_due_days: first,
        interval_days: gap,
        freight_cents: freightC,
        other_cents: otherC,
        discount_cents: discountC,
        notes: notes.trim() || null,
        lines: payloadLines,
      });
      onSaved?.(saved);
    } catch (e) {
      setErr(purchasingErrorMessage(e, t));
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label={loaded ? t('editor.title_edit', { number: loaded.number }) : t('editor.title_new')}>
      <h3 className="text-sm font-semibold">{loaded ? t('editor.title_edit', { number: loaded.number }) : t('editor.title_new')}</h3>
      {readOnly ? <p role="status" className="text-sm text-muted-foreground" data-testid="editor-readonly">{t('editor.readonly')}</p> : null}
      <fieldset disabled={readOnly} className="space-y-4">
        <Card className="space-y-3 p-4">
          <Field label={t('editor.supplier')} required>
            {partyId ? (
              <div className="flex items-center gap-2 text-sm">
                <span data-testid="supplier-chosen">{supplier}</span>
                <Button type="button" size="sm" variant="ghost" onClick={() => { setPartyId(null); setSupplier(''); }}>{t('editor.supplier_change')}</Button>
              </div>
            ) : partiesHooks ? (
              <SupplierPicker partiesHooks={partiesHooks} t={t} onPick={(id, name) => { setPartyId(id); setSupplier(name); }} />
            ) : (
              <Input aria-label={t('editor.supplier_free')} placeholder={t('editor.supplier_free')} value={supplier} onChange={(e) => setSupplier(e.target.value)} />
            )}
          </Field>
          {inventoryHooks ? <WarehouseSelect inventoryHooks={inventoryHooks} value={warehouseId} onChange={setWarehouseId} t={t} /> : null}
          <Field label={t('editor.expected')}>
            <Input type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
          </Field>
        </Card>

        <Card className="space-y-3 p-4">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">{t('editor.lines')}</h4>
          {itemsHooks ? <ItemSearch itemsHooks={itemsHooks} t={t} onPick={addLine} /> : <Button type="button" size="sm" onClick={() => addLine({ itemId: null, description: '', unit: null, qty: '1', cost: '' })}>{t('editor.add_item')}</Button>}
          {lines.length === 0 ? (
            <EmptyState message={t('editor.no_items')} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1">{t('editor.line.description')}</th>
                  <th className="w-24">{t('editor.line.qty')}</th>
                  <th className="w-32">{t('editor.line.unit_cost')}</th>
                  <th className="w-28 text-right">{t('editor.line.total')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => {
                  const q = parseQty(l.qty);
                  const c = parseMoneyToCents(l.cost);
                  return (
                    <tr key={l.key} className="border-b" data-testid="editor-line">
                      <td className="py-1"><Input aria-label={t('editor.line.description')} value={l.description} onChange={(e) => setLine(l.key, { description: e.target.value })} /></td>
                      <td><Input aria-label={t('editor.line.qty')} inputMode="decimal" value={l.qty} onChange={(e) => setLine(l.key, { qty: e.target.value })} /></td>
                      <td><Input aria-label={t('editor.line.unit_cost')} inputMode="decimal" value={l.cost} onChange={(e) => setLine(l.key, { cost: e.target.value })} /></td>
                      <td className="text-right">{q !== null && c !== null ? formatCents(lineTotalCents(q, c), 'BRL', locale) : '—'}</td>
                      <td><Button type="button" size="sm" variant="ghost" onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}>{t('editor.line.remove')}</Button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="grid gap-3 p-4 md:grid-cols-3">
          <Field label={t('editor.freight')}><Input inputMode="decimal" value={freight} onChange={(e) => setFreight(e.target.value)} /></Field>
          <Field label={t('editor.other')}><Input inputMode="decimal" value={other} onChange={(e) => setOther(e.target.value)} /></Field>
          <Field label={t('editor.discount')}><Input inputMode="decimal" value={discount} onChange={(e) => setDiscount(e.target.value)} /></Field>
        </Card>

        <Card className="grid gap-3 p-4 md:grid-cols-3">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground md:col-span-3">{t('editor.terms')}</h4>
          <Field label={t('editor.installments')}><Input inputMode="numeric" value={installments} onChange={(e) => setInstallments(e.target.value)} /></Field>
          <Field label={t('editor.first_due')}><Input inputMode="numeric" value={firstDue} onChange={(e) => setFirstDue(e.target.value)} /></Field>
          <Field label={t('editor.interval')}><Input inputMode="numeric" value={interval} onChange={(e) => setIntervalDays(e.target.value)} /></Field>
        </Card>

        <Field label={t('editor.notes')}><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      </fieldset>

      <dl className="space-y-1 text-sm" data-testid="editor-totals">
        <div className="flex justify-between"><dt>{t('editor.goods')}</dt><dd>{formatCents(goods, 'BRL', locale)}</dd></div>
        <div className="flex justify-between font-semibold"><dt>{t('editor.total')}</dt><dd>{formatCents(total, 'BRL', locale)}</dd></div>
      </dl>
      <FormError message={err} />
      <div className="flex gap-2">
        {onCancel ? <Button type="button" onClick={onCancel} disabled={save.isPending}>{t('common.cancel')}</Button> : null}
        {!readOnly ? <Button type="submit" variant="primary" disabled={save.isPending}>{save.isPending ? t('common.saving') : t('editor.save')}</Button> : null}
      </div>
    </form>
  );
}
