/**
 * `<ProductEditor/>` — create/edit a product (CONTRACT §3 products API).
 *
 * Core fields + a per-`ProductType` attribute "slot" set (`PRODUCT_TYPE_SLOTS`)
 * stored in `attributes`; the allowed `FulfillmentType`s follow the type
 * (`FULFILLMENT_BY_TYPE`). For an existing product it also hosts the status
 * control (publishing needs ≥1 active offer — the server's 422/409 is shown
 * verbatim), the media uploader and the embedded `<OffersEditor/>`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, Field, FormError, Input, ListSkeleton, RetryError, Select, Textarea } from './controls';
import { useCommerceT } from './i18n';
import { slugify } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { OffersEditor } from './OffersEditor';
import {
  FULFILLMENT_TYPES,
  PRODUCT_STATUSES,
  PRODUCT_TYPES,
  TAX_TREATMENTS,
  type FulfillmentType,
  type Product,
  type ProductInput,
  type ProductStatus,
  type ProductType,
  type TaxTreatment,
} from './types';

export interface SlotDef {
  key: string;
  kind: 'text' | 'number' | 'textarea';
}

/** Attribute slots per product type — labels are i18n keys `slot.<key>`. */
export const PRODUCT_TYPE_SLOTS: Readonly<Record<ProductType, readonly SlotDef[]>> = {
  digital: [
    { key: 'delivery_notes', kind: 'textarea' },
    { key: 'file_format', kind: 'text' },
    { key: 'license_terms', kind: 'textarea' },
  ],
  physical: [
    { key: 'sku', kind: 'text' },
    { key: 'weight_grams', kind: 'number' },
    { key: 'length_cm', kind: 'number' },
    { key: 'width_cm', kind: 'number' },
    { key: 'height_cm', kind: 'number' },
    { key: 'stock', kind: 'number' },
  ],
  service: [
    { key: 'duration_minutes', kind: 'number' },
    { key: 'service_location', kind: 'text' },
    { key: 'service_notes', kind: 'textarea' },
  ],
  print_on_demand: [
    { key: 'provider', kind: 'text' },
    { key: 'template_ref', kind: 'text' },
    { key: 'print_area', kind: 'text' },
  ],
};

/** Fulfillment types allowed per product type (first = default). Server remains the authority. */
export const FULFILLMENT_BY_TYPE: Readonly<Record<ProductType, readonly FulfillmentType[]>> = {
  digital: ['digital_delivery', 'none'],
  physical: ['shipping', 'pickup', 'local_delivery'],
  service: ['none', 'pickup', 'local_delivery'],
  print_on_demand: ['shipping'],
};

export interface ProductEditorProps {
  hooks: CommerceHooks;
  /** Existing product id; omit/null to create a new product. */
  productId?: string | null;
  locale?: string;
  /** Called after create (new id) or update. */
  onSaved?: (product: Product) => void;
  /** Called after delete. */
  onDeleted?: () => void;
}

interface FormState {
  title: string;
  slug: string;
  slugTouched: boolean;
  description: string;
  product_type: ProductType;
  fulfillment_type: FulfillmentType;
  category_id: string;
  tax_treatment_override: TaxTreatment | '';
  attributes: Record<string, string>;
}

function toState(p?: Product | null): FormState {
  const type = p?.product_type ?? 'digital';
  return {
    title: p?.title ?? '',
    slug: p?.slug ?? '',
    slugTouched: !!p,
    description: p?.description ?? '',
    product_type: type,
    fulfillment_type: p?.fulfillment_type ?? FULFILLMENT_BY_TYPE[type][0],
    category_id: p?.category_id ?? '',
    tax_treatment_override: p?.tax_treatment_override ?? '',
    attributes: Object.fromEntries(Object.entries(p?.attributes ?? {}).map(([k, v]) => [k, String(v ?? '')])),
  };
}

export function ProductEditor({ hooks, productId, locale, onSaved, onDeleted }: ProductEditorProps) {
  const { t } = useCommerceT(locale);
  const product = hooks.useProduct(productId);
  const categories = hooks.useCategories();
  const m = hooks.useProductMutations();
  const media = hooks.useMediaMutations(productId ?? '');

  const [form, setForm] = React.useState<FormState>(() => toState(product.data));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const loaded = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!productId) {
      if (loaded.current !== 'new') {
        loaded.current = 'new';
        setForm(toState(null));
      }
      return;
    }
    if (product.data) {
      const stamp = `${product.data.id}:${product.data.updated_at ?? ''}`;
      if (loaded.current !== stamp) {
        loaded.current = stamp;
        setForm(toState(product.data));
      }
    }
  }, [productId, product.data]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  if (productId && product.showSkeleton) return <ListSkeleton rows={5} />;
  if (productId && product.isError && !product.data) {
    return (
      <RetryError
        message={`${t('common.error_loading')}: ${errorMessage(product.error)}`}
        onRetry={() => product.refetch()}
        retryLabel={t('common.retry')}
      />
    );
  }

  const slots = PRODUCT_TYPE_SLOTS[form.product_type];

  function onType(type: ProductType) {
    setForm((f) => ({
      ...f,
      product_type: type,
      fulfillment_type: FULFILLMENT_BY_TYPE[type].includes(f.fulfillment_type) ? f.fulfillment_type : FULFILLMENT_BY_TYPE[type][0],
    }));
  }

  function buildInput(): ProductInput {
    const attributes: Record<string, unknown> = {};
    for (const s of slots) {
      const raw = form.attributes[s.key];
      if (raw === undefined || raw === '') continue;
      attributes[s.key] = s.kind === 'number' ? Number(raw) : raw;
    }
    return {
      slug: form.slug.trim(),
      title: form.title.trim(),
      description: form.description,
      product_type: form.product_type,
      fulfillment_type: form.fulfillment_type,
      category_id: form.category_id || null,
      attributes,
      tax_treatment_override: form.tax_treatment_override || null,
    };
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (!form.title.trim()) e.title = t('common.required');
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.slug.trim())) e.slug = t('product.slug_invalid');
    for (const s of slots) {
      const raw = form.attributes[s.key];
      if (s.kind === 'number' && raw && (!Number.isFinite(Number(raw)) || Number(raw) < 0)) e[`attr.${s.key}`] = t('common.invalid');
    }
    setErrors(e);
    if (Object.keys(e).length) return;
    try {
      const saved = productId
        ? await m.update.mutateAsync({ id: productId, ...buildInput() })
        : await m.create.mutateAsync(buildInput());
      onSaved?.(saved);
    } catch {
      // Surfaced via `m.create.error` / `m.update.error` below.
    }
  }

  const saveError = (productId ? m.update.error : m.create.error) as unknown;
  const current = product.data;

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="space-y-4" noValidate aria-busy={product.isRefreshing}>
        {product.isRefreshing ? <p role="status" className="text-xs text-muted-foreground">{t('common.refreshing')}</p> : null}
        <FormError message={saveError ? errorMessage(saveError) : null} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('product.title')} required error={errors.title}>
            <Input
              value={form.title}
              onChange={(e) => {
                const title = e.target.value;
                setForm((f) => ({ ...f, title, slug: f.slugTouched ? f.slug : slugify(title) }));
              }}
            />
          </Field>
          <Field label={t('product.slug')} required error={errors.slug}>
            <Input
              value={form.slug}
              onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value, slugTouched: true }))}
            />
          </Field>
          <Field label={t('product.type')}>
            <Select value={form.product_type} onChange={(e) => onType(e.target.value as ProductType)}>
              {PRODUCT_TYPES.map((x) => (
                <option key={x} value={x}>{t(`product_type.${x}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('product.fulfillment')}>
            <Select value={form.fulfillment_type} onChange={(e) => set('fulfillment_type', e.target.value as FulfillmentType)}>
              {FULFILLMENT_BY_TYPE[form.product_type].map((x) => (
                <option key={x} value={x}>{t(`fulfillment.${x}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('product.category')}>
            <Select value={form.category_id} onChange={(e) => set('category_id', e.target.value)}>
              <option value="">{t('product.no_category')}</option>
              {(categories.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
          <Field label={t('product.tax_override')}>
            <Select value={form.tax_treatment_override} onChange={(e) => set('tax_treatment_override', e.target.value as TaxTreatment | '')}>
              <option value="">{t('product.tax_default')}</option>
              {TAX_TREATMENTS.map((x) => (
                <option key={x} value={x}>{t(`tax_treatment.${x}`)}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label={t('product.description')}>
          <Textarea rows={4} value={form.description} onChange={(e) => set('description', e.target.value)} />
        </Field>

        <fieldset className="grid gap-3 sm:grid-cols-2" data-testid="product-slots">
          <legend className="mb-2 text-sm font-semibold">{t('product.attributes')} — {t(`product_type.${form.product_type}`)}</legend>
          {slots.map((s) => (
            <Field key={s.key} label={t(`slot.${s.key}`)} error={errors[`attr.${s.key}`]}>
              {s.kind === 'textarea' ? (
                <Textarea rows={2} value={form.attributes[s.key] ?? ''} onChange={(e) => set('attributes', { ...form.attributes, [s.key]: e.target.value })} />
              ) : (
                <Input
                  inputMode={s.kind === 'number' ? 'decimal' : undefined}
                  value={form.attributes[s.key] ?? ''}
                  onChange={(e) => set('attributes', { ...form.attributes, [s.key]: e.target.value })}
                />
              )}
            </Field>
          ))}
        </fieldset>

        <div className="flex items-center gap-2">
          <Button type="submit" disabled={m.create.isPending || m.update.isPending}>
            {m.create.isPending || m.update.isPending ? t('common.saving') : t('common.save')}
          </Button>
          {productId ? (
            confirmDelete ? (
              <>
                <span className="text-sm">{t('product.delete_confirm')}</span>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={m.remove.isPending}
                  onClick={async () => {
                    try {
                      await m.remove.mutateAsync(productId);
                      onDeleted?.();
                    } catch {
                      // Surfaced via `m.remove.error` below.
                    }
                  }}
                >
                  {t('common.delete')}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setConfirmDelete(false)}>{t('common.cancel')}</Button>
              </>
            ) : (
              <Button type="button" variant="outline" onClick={() => setConfirmDelete(true)}>{t('common.delete')}</Button>
            )
          ) : null}
        </div>
        <FormError message={m.remove.error ? errorMessage(m.remove.error) : null} />
      </form>

      {productId && current ? (
        <>
          <section className="space-y-2" aria-label={t('product.status')}>
            <h3 className="text-sm font-semibold">{t('product.status')}</h3>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={current.status === 'published' ? 'default' : 'muted'}>{t(`product_status.${current.status}`)}</Badge>
              {PRODUCT_STATUSES.filter((s) => s !== current.status).map((s) => (
                <Button
                  key={s}
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={m.setStatus.isPending}
                  onClick={() => m.setStatus.mutate({ id: productId, status: s as ProductStatus })}
                >
                  {t(`product_status.${s}`)}
                </Button>
              ))}
            </div>
            <FormError message={m.setStatus.error ? errorMessage(m.setStatus.error) : null} />
          </section>

          <section className="space-y-2" aria-label={t('product.media')}>
            <h3 className="text-sm font-semibold">{t('product.media')}</h3>
            {(current.media ?? []).length === 0 ? <EmptyState message={t('product.media_empty')} /> : null}
            <ul className="flex flex-wrap gap-3">
              {(current.media ?? []).map((md) => (
                <li key={md.id} className="space-y-1">
                  {md.kind === 'image' && md.url ? (
                    <img src={md.url} alt={md.alt} className="h-24 w-24 rounded object-cover" />
                  ) : (
                    <span className="block h-24 w-24 rounded bg-muted text-xs">{md.kind}</span>
                  )}
                  <Button size="sm" variant="ghost" disabled={media.remove.isPending} onClick={() => media.remove.mutate(md.id)}>
                    {t('common.remove')}
                  </Button>
                </li>
              ))}
            </ul>
            <input
              type="file"
              accept="image/*,video/*"
              aria-label={t('product.media_upload')}
              disabled={media.upload.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) media.upload.mutate({ file, alt: current.title });
                e.target.value = '';
              }}
            />
            {media.upload.isPending ? <p role="status" className="text-xs">{t('common.saving')}</p> : null}
            <FormError message={media.upload.error ? errorMessage(media.upload.error) : media.remove.error ? errorMessage(media.remove.error) : null} />
          </section>

          <OffersEditor hooks={hooks} productId={productId} locale={locale} />
        </>
      ) : null}
    </div>
  );
}
