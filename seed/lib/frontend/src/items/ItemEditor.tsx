/**
 * `<ItemEditor/>` — create (`itemId` empty) or edit one item, in three tabs: Geral · Fiscal · Medidas.
 *
 * Client-side format checks (`validation.ts`) give instant feedback; the server's 422 (with
 * `error.details.field`) is mapped back onto the same field and its tab, so a rule only the server knows
 * (duplicate SKU, foreign category) is never lost. Money is typed in reais and sent as integer cents.
 * No stock fields here — the inventory organ owns stock.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { centsToInput, parseMoneyToCents } from '../organ-kit/money';
import { EmptyState, Field, FormError, Input, ListSkeleton, RetryError, Select, Textarea } from './controls';
import { apiFieldError, errorMessage, type ItemsHooks } from './hooks';
import { itemsT as t } from './messages';
import { flattenCategories } from './ItemCategoryManager';
import { ITEM_TYPES, ORIGENS, UNITS, type Item, type ItemInput } from './types';
import { normalizeCest, normalizeCfop, normalizeGtin, normalizeNcm, normalizeOrigem, normalizeSku } from './validation';

export interface ItemEditorProps {
  hooks: ItemsHooks;
  /** Item to edit; omit/`null` to create. */
  itemId?: string | null;
  onSaved?: (item: Item) => void;
  onCancel?: () => void;
}

type TabKey = 'general' | 'fiscal' | 'logistics';
const TAB_OF_FIELD: Record<string, TabKey> = {
  sku: 'general', name: 'general', description: 'general', item_type: 'general', unit: 'general', category_id: 'general',
  cost_cents: 'general', price_cents: 'general', is_active: 'general',
  ncm: 'fiscal', cest: 'fiscal', cfop_default: 'fiscal', origem: 'fiscal', gtin: 'fiscal',
  weight_g: 'logistics', length_mm: 'logistics', width_mm: 'logistics', height_mm: 'logistics',
};
/** Form field key → the API field (server errors arrive under the API name). */
const FORM_TO_API: Record<string, string> = { cost: 'cost_cents', price: 'price_cents', cfop: 'cfop_default', weight: 'weight_g', length: 'length_mm', width: 'width_mm', height: 'height_mm' };

interface FormState {
  sku: string; name: string; description: string; item_type: string; unit: string; category_id: string;
  cost: string; price: string; is_active: boolean;
  ncm: string; cest: string; cfop: string; origem: string; gtin: string;
  weight: string; length: string; width: string; height: string;
}

const EMPTY: FormState = {
  sku: '', name: '', description: '', item_type: 'goods', unit: 'UN', category_id: '', cost: '0,00', price: '', is_active: true,
  ncm: '', cest: '', cfop: '', origem: '', gtin: '', weight: '', length: '', width: '', height: '',
};

const intOrNull = (v: string): number | null | undefined => {
  if (v.trim() === '') return null;
  return /^\d+$/.test(v.trim()) ? Number(v.trim()) : undefined;
};

function fromItem(it: Item): FormState {
  const s = (v: string | number | null) => (v == null ? '' : String(v));
  return {
    sku: it.sku, name: it.name, description: it.description ?? '', item_type: it.item_type, unit: it.unit,
    category_id: it.category_id ?? '', cost: centsToInput(it.cost_cents), price: it.price_cents == null ? '' : centsToInput(it.price_cents),
    is_active: it.is_active, ncm: s(it.ncm), cest: s(it.cest), cfop: s(it.cfop_default), origem: s(it.origem), gtin: s(it.gtin),
    weight: s(it.weight_g), length: s(it.length_mm), width: s(it.width_mm), height: s(it.height_mm),
  };
}

/** Validate the form; returns the API body or the per-field messages. */
export function buildItemInput(f: FormState): { body: ItemInput | null; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const sku = normalizeSku(f.sku);
  if (sku === undefined) errors.sku = t('editor.invalid_sku');
  if (!f.name.trim()) errors.name = t('common.required');
  const ncm = normalizeNcm(f.ncm);
  if (ncm === undefined) errors.ncm = t('editor.invalid_ncm');
  const cest = normalizeCest(f.cest);
  if (cest === undefined) errors.cest = t('editor.invalid_cest');
  const cfop = normalizeCfop(f.cfop);
  if (cfop === undefined) errors.cfop = t('editor.invalid_cfop');
  const gtin = normalizeGtin(f.gtin);
  if (gtin === undefined) errors.gtin = t('editor.invalid_gtin');
  const origem = normalizeOrigem(f.origem);
  const cost = f.cost.trim() === '' ? 0 : parseMoneyToCents(f.cost);
  if (cost === null) errors.cost = t('editor.invalid_money');
  const price = f.price.trim() === '' ? null : parseMoneyToCents(f.price);
  if (f.price.trim() !== '' && price === null) errors.price = t('editor.invalid_money');
  const ints: Record<string, number | null | undefined> = {
    weight: intOrNull(f.weight), length: intOrNull(f.length), width: intOrNull(f.width), height: intOrNull(f.height),
  };
  for (const [k, v] of Object.entries(ints)) if (v === undefined) errors[k] = t('editor.invalid_int');
  if (Object.keys(errors).length > 0) return { body: null, errors };
  return {
    errors,
    body: {
      sku: sku as string,
      name: f.name.trim(),
      description: f.description.trim() || null,
      item_type: f.item_type,
      unit: f.unit as ItemInput['unit'],
      category_id: f.category_id || null,
      ncm: ncm as string | null,
      cest: cest as string | null,
      cfop_default: cfop as string | null,
      origem: origem as number | null,
      gtin: gtin as string | null,
      cost_cents: cost as number,
      price_cents: price,
      weight_g: ints.weight as number | null,
      length_mm: ints.length as number | null,
      width_mm: ints.width as number | null,
      height_mm: ints.height as number | null,
      is_active: f.is_active,
    },
  };
}

export function ItemEditor({ hooks, itemId, onSaved, onCancel }: ItemEditorProps) {
  const editing = !!itemId;
  const item = hooks.useItem(itemId);
  const categories = hooks.useItemCategories();
  const m = hooks.useItemMutations();
  const [form, setForm] = React.useState<FormState>(EMPTY);
  const [loadedId, setLoadedId] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<TabKey>('general');
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);

  // Seed the form once per loaded item (a background refetch must not clobber what the user is typing).
  React.useEffect(() => {
    if (editing && item.data && loadedId !== item.data.id) {
      setForm(fromItem(item.data));
      setLoadedId(item.data.id);
      setErrors({});
    }
  }, [editing, item.data, loadedId]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      if (!(key in e)) return e;
      const { [key]: _gone, ...rest } = e;
      return rest;
    });
  };

  function tabHasError(k: TabKey): boolean {
    return Object.keys(errors).some((field) => TAB_OF_FIELD[FORM_TO_API[field] ?? field] === k);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setFormError(null);
    const { body, errors: found } = buildItemInput(form);
    if (!body) {
      setErrors(found);
      const first = Object.keys(found)[0];
      setTab(TAB_OF_FIELD[FORM_TO_API[first] ?? first] ?? 'general');
      return;
    }
    try {
      const saved = editing
        ? await m.update.mutateAsync({ id: itemId as string, ...body })
        : await m.create.mutateAsync(body);
      setErrors({});
      onSaved?.(saved);
    } catch (err) {
      const fe = apiFieldError(err);
      if (fe?.field) {
        const formKey = Object.entries(FORM_TO_API).find(([, api]) => api === fe.field)?.[0] ?? fe.field;
        setErrors({ [formKey]: fe.message });
        setTab(TAB_OF_FIELD[fe.field] ?? 'general');
      } else {
        setFormError(errorMessage(err));
      }
    }
  }

  if (editing && item.showSkeleton) return <ListSkeleton rows={5} />;
  if (editing && item.isError && !item.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(item.error)}`} onRetry={() => item.refetch()} retryLabel={t('common.retry')} />;
  }
  if (editing && !item.data) return <EmptyState message={t('editor.not_found')} />;

  const saving = m.create.isPending || m.update.isPending;
  const tabs: Array<[TabKey, string]> = [['general', 'editor.tab_general'], ['fiscal', 'editor.tab_fiscal'], ['logistics', 'editor.tab_logistics']];

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-busy={editing && item.isRefreshing}>
      <h2 className="text-base font-semibold">{editing ? t('editor.title_edit') : t('editor.title_new')}</h2>
      <div role="tablist" aria-label={t('editor.tabs')} className="flex gap-1 border-b">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`item-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`item-panel-${key}`}
            className={`px-3 py-1.5 text-sm ${tab === key ? 'border-b-2 border-primary font-medium' : 'text-muted-foreground'}`}
            onClick={() => setTab(key)}
          >
            {t(label)}
            {tabHasError(key) ? <span aria-label="!" className="ml-1 text-destructive">!</span> : null}
          </button>
        ))}
      </div>

      {tab === 'general' ? (
        <div role="tabpanel" id="item-panel-general" aria-labelledby="item-tab-general" className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.sku')} required error={errors.sku}>
            <Input value={form.sku} onChange={(e) => set('sku', e.target.value)} />
          </Field>
          <Field label={t('editor.name')} required error={errors.name}>
            <Input value={form.name} onChange={(e) => set('name', e.target.value)} />
          </Field>
          <Field label={t('editor.type')} error={errors.item_type}>
            <Select value={form.item_type} onChange={(e) => set('item_type', e.target.value)}>
              {(ITEM_TYPES as readonly string[]).includes(form.item_type) ? null : <option value={form.item_type}>{form.item_type}</option>}
              {ITEM_TYPES.map((x) => (
                <option key={x} value={x}>{t(`type.${x}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('editor.unit')} error={errors.unit}>
            <Select value={form.unit} onChange={(e) => set('unit', e.target.value)}>
              {UNITS.map((u) => (
                <option key={u} value={u}>{t(`unit.${u}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('editor.category')} error={errors.category_id}>
            <Select value={form.category_id} onChange={(e) => set('category_id', e.target.value)}>
              <option value="">{t('editor.no_category')}</option>
              {flattenCategories(categories.data ?? []).map(([c, depth]) => (
                <option key={c.id} value={c.id}>{`${'— '.repeat(depth)}${c.name}`}</option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2 self-end text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} />
            {t('editor.active')}
          </label>
          <Field label={t('editor.cost')} error={errors.cost}>
            <Input inputMode="decimal" value={form.cost} onChange={(e) => set('cost', e.target.value)} />
          </Field>
          <Field label={t('editor.price')} error={errors.price}>
            <Input inputMode="decimal" value={form.price} onChange={(e) => set('price', e.target.value)} />
          </Field>
          <p className="text-xs text-muted-foreground sm:col-span-2">{t('editor.cost_hint')}</p>
          <div className="sm:col-span-2">
            <Field label={t('editor.description')} error={errors.description}>
              <Textarea rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} />
            </Field>
          </div>
        </div>
      ) : null}

      {tab === 'fiscal' ? (
        <div role="tabpanel" id="item-panel-fiscal" aria-labelledby="item-tab-fiscal" className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.ncm')} error={errors.ncm}>
            <Input inputMode="numeric" placeholder={t('editor.ncm_hint')} value={form.ncm} onChange={(e) => set('ncm', e.target.value)} />
          </Field>
          <Field label={t('editor.cest')} error={errors.cest}>
            <Input inputMode="numeric" placeholder={t('editor.cest_hint')} value={form.cest} onChange={(e) => set('cest', e.target.value)} />
          </Field>
          <Field label={t('editor.cfop')} error={errors.cfop}>
            <Input inputMode="numeric" placeholder={t('editor.cfop_hint')} value={form.cfop} onChange={(e) => set('cfop', e.target.value)} />
          </Field>
          <Field label={t('editor.origem')} error={errors.origem}>
            <Select value={form.origem} onChange={(e) => set('origem', e.target.value)}>
              <option value="">{t('editor.no_origem')}</option>
              {ORIGENS.map((o) => (
                <option key={o} value={String(o)}>{t(`origem.${o}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('editor.gtin')} error={errors.gtin}>
            <Input inputMode="numeric" placeholder={t('editor.gtin_hint')} value={form.gtin} onChange={(e) => set('gtin', e.target.value)} />
          </Field>
          <p className="text-xs text-muted-foreground sm:col-span-2">{t('editor.fiscal_note')}</p>
        </div>
      ) : null}

      {tab === 'logistics' ? (
        <div role="tabpanel" id="item-panel-logistics" aria-labelledby="item-tab-logistics" className="grid gap-3 sm:grid-cols-2">
          <Field label={t('editor.weight')} error={errors.weight}>
            <Input inputMode="numeric" value={form.weight} onChange={(e) => set('weight', e.target.value)} />
          </Field>
          <Field label={t('editor.length')} error={errors.length}>
            <Input inputMode="numeric" value={form.length} onChange={(e) => set('length', e.target.value)} />
          </Field>
          <Field label={t('editor.width')} error={errors.width}>
            <Input inputMode="numeric" value={form.width} onChange={(e) => set('width', e.target.value)} />
          </Field>
          <Field label={t('editor.height')} error={errors.height}>
            <Input inputMode="numeric" value={form.height} onChange={(e) => set('height', e.target.value)} />
          </Field>
        </div>
      ) : null}

      <FormError message={formError} />
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</Button>
        {onCancel ? <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button> : null}
      </div>
    </form>
  );
}
