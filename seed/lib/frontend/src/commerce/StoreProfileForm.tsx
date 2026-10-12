/**
 * `<StoreProfileForm/>` — staff form for the org's store profile
 * (CONTRACT §3 `GET/PUT /api/commerce/profile`, `POST .../cnpj-lookup`).
 *
 * CNPJ is masked and check-digit validated with the canonical
 * `identificador.ts` algorithm; the lookup button prefills from the registry.
 * Saves are optimistic-locked: `expected_version` is sent and a 409
 * (`versao_conflitante`) shows a "someone else saved" banner with a reload.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Skeleton } from '../design-system/ui/Skeleton';
import { ErrorState, Field, FormError, Input, Select } from './controls';
import { useCommerceT } from './i18n';
import { maskCnpj, onlyDigits } from './format';
import { isValidCnpj, isValidEmail } from './validation';
import { apiErrorCode, apiErrorStatus, errorMessage, type CommerceHooks } from './hooks';
import {
  COMMERCE_ERROR_CODES,
  PRODUCT_TYPES,
  TAX_REGIMES,
  TAX_TREATMENTS,
  type Address,
  type BrandTokens,
  type StoreProfile,
  type StoreProfileInput,
  type TaxRegime,
  type TaxTreatment,
  type ProductType,
} from './types';

export const BRAND_TOKEN_KEYS = ['primary', 'secondary', 'accent', 'background', 'foreground'] as const;
export const BRAND_TOKEN_DEFAULTS: Record<(typeof BRAND_TOKEN_KEYS)[number], string> = {
  primary: '#4f46e5',
  secondary: '#64748b',
  accent: '#f59e0b',
  background: '#ffffff',
  foreground: '#0f172a',
};
const CURRENCIES = ['BRL', 'USD'] as const;
const LOCALES = ['pt-BR', 'en'] as const;

export interface StoreProfileFormProps {
  hooks: CommerceHooks;
  locale?: string;
  /** Shows the platform-admin-only `platform_fee_bps` field. UX only — the server ignores it otherwise. */
  isPlatformAdmin?: boolean;
  onSaved?: (profile: StoreProfile) => void;
}

interface FormState {
  legal_name: string;
  trade_name: string;
  cnpj: string;
  tax_regime: TaxRegime;
  tax_treatment: Partial<Record<ProductType, TaxTreatment>>;
  locale: string;
  currency: string;
  brand_tokens: BrandTokens;
  address: Address;
  contact_email: string;
  contact_phone: string;
  platform_fee_bps: string;
}

function toState(p: StoreProfile | null | undefined): FormState {
  return {
    legal_name: p?.legal_name ?? '',
    trade_name: p?.trade_name ?? '',
    cnpj: maskCnpj(p?.cnpj ?? ''),
    tax_regime: p?.tax_regime ?? 'simples',
    tax_treatment: p?.tax_treatment ?? {},
    locale: p?.locale ?? 'pt-BR',
    currency: p?.currency ?? 'BRL',
    brand_tokens: { ...BRAND_TOKEN_DEFAULTS, ...(p?.brand_tokens ?? {}) },
    address: p?.address ?? {},
    contact_email: p?.contact_email ?? '',
    contact_phone: p?.contact_phone ?? '',
    platform_fee_bps: String(p?.platform_fee_bps ?? 0),
  };
}

export function StoreProfileForm({ hooks, locale, isPlatformAdmin = false, onSaved }: StoreProfileFormProps) {
  const { t } = useCommerceT(locale);
  const profile = hooks.useProfile();
  const save = hooks.useSaveProfile();
  const lookup = hooks.useCnpjLookup();

  const [form, setForm] = React.useState<FormState>(() => toState(profile.data));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);
  const loadedVersion = React.useRef<number | null | undefined>(undefined);

  // (Re)initialise the form when a different server version arrives.
  React.useEffect(() => {
    if (profile.data === undefined) return;
    const v = profile.data?.version ?? 0;
    if (loadedVersion.current !== v) {
      loadedVersion.current = v;
      setForm(toState(profile.data));
    }
  }, [profile.data]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setSaved(false);
    setForm((f) => ({ ...f, [key]: value }));
  };

  if (profile.showSkeleton) {
    return (
      <div className="space-y-3" data-testid="store-profile-loading">
        <Skeleton height={32} width="100%" />
        <Skeleton height={32} width="100%" announce={false} />
        <Skeleton height={32} width="100%" announce={false} />
      </div>
    );
  }
  if (profile.isError && !profile.data) {
    return (
      <div className="space-y-2">
        <ErrorState message={`${t('common.error_loading')}: ${errorMessage(profile.error)}`} />
        <Button variant="outline" onClick={() => profile.refetch()}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  const conflict =
    apiErrorStatus(save.error) === 409 || apiErrorCode(save.error) === COMMERCE_ERROR_CODES.versaoConflitante;
  const serverCnpjError = apiErrorCode(save.error) === COMMERCE_ERROR_CODES.cnpjInvalido;

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    if (!form.legal_name.trim()) e.legal_name = t('common.required');
    if (!form.trade_name.trim()) e.trade_name = t('common.required');
    if (!isValidCnpj(form.cnpj)) e.cnpj = t('profile.cnpj_invalid');
    if (form.contact_email && !isValidEmail(form.contact_email)) e.contact_email = t('common.invalid_email');
    const bps = Number(form.platform_fee_bps);
    if (isPlatformAdmin && (!Number.isInteger(bps) || bps < 0 || bps > 10000)) e.platform_fee_bps = t('common.invalid');
    return e;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;
    const body: StoreProfileInput = {
      legal_name: form.legal_name.trim(),
      trade_name: form.trade_name.trim(),
      cnpj: onlyDigits(form.cnpj),
      tax_regime: form.tax_regime,
      tax_treatment: form.tax_treatment,
      locale: form.locale,
      currency: form.currency,
      brand_tokens: form.brand_tokens,
      address: form.address,
      contact_email: form.contact_email.trim(),
      contact_phone: form.contact_phone.trim(),
      expected_version: profile.data?.version ?? 0,
      ...(isPlatformAdmin ? { platform_fee_bps: Number(form.platform_fee_bps) } : {}),
    };
    try {
      const saved = await save.mutateAsync(body);
      setSaved(true);
      loadedVersion.current = saved.version;
      onSaved?.(saved);
    } catch {
      // Surfaced below through `save.error` (409 banner / field error / FormError) — not swallowed.
    }
  }

  async function onLookup() {
    if (!isValidCnpj(form.cnpj)) {
      setErrors((x) => ({ ...x, cnpj: t('profile.cnpj_invalid') }));
      return;
    }
    try {
      const r = await lookup.mutateAsync(onlyDigits(form.cnpj));
      setForm((f) => ({
        ...f,
        legal_name: r.legal_name ?? f.legal_name,
        trade_name: r.trade_name ?? f.trade_name,
        address: { ...f.address, ...(r.address ?? {}) },
        contact_email: r.contact_email ?? f.contact_email,
        contact_phone: r.contact_phone ?? f.contact_phone,
      }));
    } catch {
      // Surfaced below through `lookup.error`.
    }
  }

  const setAddr = (k: keyof Address, v: string) => set('address', { ...form.address, [k]: v });
  const tok = form.brand_tokens;

  return (
    <form onSubmit={onSubmit} className="space-y-6" noValidate aria-busy={profile.isRefreshing}>
      {profile.isRefreshing ? <p className="text-xs text-muted-foreground">{t('common.refreshing')}</p> : null}

      {conflict ? (
        <div role="alert" className="space-y-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <p>{t('profile.conflict')}</p>
          <Button
            type="button"
            variant="outline"
            onClick={async () => {
              save.reset();
              loadedVersion.current = undefined;
              await profile.refetch();
            }}
          >
            {t('profile.reload')}
          </Button>
        </div>
      ) : save.isError ? (
        <FormError message={serverCnpjError ? t('profile.cnpj_invalid') : errorMessage(save.error)} />
      ) : null}

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold">{t('profile.section_identity')}</legend>
        <Field label={t('profile.legal_name')} required error={errors.legal_name}>
          <Input value={form.legal_name} onChange={(e) => set('legal_name', e.target.value)} />
        </Field>
        <Field label={t('profile.trade_name')} required error={errors.trade_name}>
          <Input value={form.trade_name} onChange={(e) => set('trade_name', e.target.value)} />
        </Field>
        <div className="space-y-1">
          <Field label={t('profile.cnpj')} required error={errors.cnpj ?? (serverCnpjError ? t('profile.cnpj_invalid') : null)}>
            <Input
              inputMode="numeric"
              value={form.cnpj}
              onChange={(e) => set('cnpj', maskCnpj(e.target.value))}
              placeholder="00.000.000/0000-00"
            />
          </Field>
          <Button type="button" variant="outline" size="sm" onClick={onLookup} disabled={lookup.isPending}>
            {lookup.isPending ? t('common.loading') : t('profile.lookup')}
          </Button>
          {lookup.isError ? <p role="alert" className="text-xs text-destructive">{errorMessage(lookup.error)}</p> : null}
        </div>
        <Field label={t('profile.contact_email')} error={errors.contact_email}>
          <Input type="email" value={form.contact_email} onChange={(e) => set('contact_email', e.target.value)} />
        </Field>
        <Field label={t('profile.contact_phone')}>
          <Input value={form.contact_phone} onChange={(e) => set('contact_phone', e.target.value)} />
        </Field>
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="mb-2 text-sm font-semibold">{t('profile.section_address')}</legend>
        {(['street', 'number', 'complement', 'district', 'city', 'state', 'zip'] as const).map((k) => (
          <Field key={k} label={t(`address.${k}`)}>
            <Input value={form.address[k] ?? ''} onChange={(e) => setAddr(k, e.target.value)} />
          </Field>
        ))}
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold">{t('profile.section_tax')}</legend>
        <Field label={t('profile.tax_regime')}>
          <Select value={form.tax_regime} onChange={(e) => set('tax_regime', e.target.value as TaxRegime)}>
            {TAX_REGIMES.map((r) => (
              <option key={r} value={r}>{t(`tax_regime.${r}`)}</option>
            ))}
          </Select>
        </Field>
        <div className="sm:col-span-2 grid gap-3 sm:grid-cols-2">
          {PRODUCT_TYPES.map((pt) => (
            <Field key={pt} label={`${t('profile.tax_treatment_for')} ${t(`product_type.${pt}`)}`}>
              <Select
                value={form.tax_treatment[pt] ?? 'none'}
                onChange={(e) => set('tax_treatment', { ...form.tax_treatment, [pt]: e.target.value as TaxTreatment })}
              >
                {TAX_TREATMENTS.map((x) => (
                  <option key={x} value={x}>{t(`tax_treatment.${x}`)}</option>
                ))}
              </Select>
            </Field>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold">{t('profile.section_locale')}</legend>
        <Field label={t('profile.locale')}>
          <Select value={form.locale} onChange={(e) => set('locale', e.target.value)}>
            {LOCALES.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </Select>
        </Field>
        <Field label={t('profile.currency')}>
          <Select value={form.currency} onChange={(e) => set('currency', e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </Select>
        </Field>
        {isPlatformAdmin ? (
          <Field label={t('profile.platform_fee_bps')} error={errors.platform_fee_bps}>
            <Input
              inputMode="numeric"
              value={form.platform_fee_bps}
              onChange={(e) => set('platform_fee_bps', e.target.value.replace(/\D/g, ''))}
            />
          </Field>
        ) : null}
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm font-semibold">{t('profile.section_brand')}</legend>
        <div className="flex flex-wrap gap-4">
          {BRAND_TOKEN_KEYS.map((k) => (
            <label key={k} className="flex items-center gap-2 text-xs">
              <input
                type="color"
                aria-label={t(`brand.${k}`)}
                value={tok[k] ?? BRAND_TOKEN_DEFAULTS[k]}
                onChange={(e) => set('brand_tokens', { ...form.brand_tokens, [k]: e.target.value })}
              />
              {t(`brand.${k}`)}
            </label>
          ))}
        </div>
        <div
          data-testid="brand-preview"
          className="rounded-md border p-4"
          style={{ background: tok.background, color: tok.foreground, borderColor: tok.secondary }}
        >
          <p className="text-sm font-semibold">{form.trade_name || t('profile.preview_name')}</p>
          <button
            type="button"
            className="mt-2 rounded px-3 py-1 text-sm"
            style={{ background: tok.primary, color: tok.background }}
          >
            {t('profile.preview_button')}
          </button>
          <span className="ml-2 text-xs" style={{ color: tok.accent }}>{t('profile.preview_accent')}</span>
        </div>
      </fieldset>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {saved ? <span role="status" className="text-sm text-green-600">{t('common.saved')}</span> : null}
      </div>
    </form>
  );
}
