/**
 * `<InstallmentsSettings/>` — card installments of the store (CONTRACT P4 §7 / owner decisions D33 + D41):
 * the most parcelas offered (default 12), how many are interest-free (default 3) and the monthly buyer
 * interest — own rate in % a.m., or `null` to follow the platform default (1,99 % a.m.).
 *
 * Saves through the store-profile endpoint (`PUT /api/commerce/profile` takes the whole profile plus the three
 * installment fields; it is optimistic-locked with `expected_version`). It changes NEW quotes only — a charge
 * already created keeps the total it was quoted. Admin-only (UX hint; the server enforces).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Skeleton } from '../design-system/ui/Skeleton';
import { ErrorState, Field, FormError, Input, Select } from './controls';
import { useCommerceT } from './i18n';
import { apiErrorCode, errorMessage, type CommerceHooks } from './hooks';
import { COMMERCE_ERROR_CODES, type StoreProfile, type StoreProfileInput } from './types';

export interface InstallmentsSettingsProps {
  hooks: CommerceHooks;
  locale?: string;
  /** Org admin (UX only). Default `false`: read-only with a hint. */
  isAdmin?: boolean;
  onSaved?: (profile: StoreProfile) => void;
}

export const DEFAULT_INSTALLMENTS_MAX = 12;
export const DEFAULT_INSTALLMENTS_INTEREST_FREE = 3;
export const MAX_INTEREST_BPS = 2000;

/** "1,99" / "1.99" -> 199 bps; `null` when not a number in 0..20 %. */
export function percentToBps(input: string): number | null {
  const n = Number(input.trim().replace(',', '.'));
  if (!input.trim() || !Number.isFinite(n) || n < 0) return null;
  const bps = Math.round(n * 100);
  return bps <= MAX_INTEREST_BPS ? bps : null;
}
export function bpsToPercent(bps: number): string {
  return (bps / 100).toFixed(2).replace('.', ',');
}

/** The full `PUT /profile` body from the stored profile + the installment fields (the route needs the whole profile). */
export function profileWithInstallments(
  p: StoreProfile,
  next: { installments_max: number; installments_interest_free: number; installment_interest_monthly_bps: number | null },
): StoreProfileInput {
  return {
    legal_name: p.legal_name,
    trade_name: p.trade_name,
    cnpj: p.cnpj,
    tax_regime: p.tax_regime,
    tax_treatment: p.tax_treatment ?? {},
    locale: p.locale,
    currency: p.currency,
    brand_tokens: p.brand_tokens ?? {},
    address: p.address ?? {},
    contact_email: p.contact_email,
    contact_phone: p.contact_phone,
    ...next,
    expected_version: p.version,
  };
}

const COUNTS = Array.from({ length: 12 }, (_, i) => i + 1);

export function InstallmentsSettings({ hooks, locale, isAdmin = false, onSaved }: InstallmentsSettingsProps) {
  const { t } = useCommerceT(locale);
  const profile = hooks.useProfile();
  const save = hooks.useSaveProfile();
  const [max, setMax] = React.useState(DEFAULT_INSTALLMENTS_MAX);
  const [free, setFree] = React.useState(DEFAULT_INSTALLMENTS_INTEREST_FREE);
  const [custom, setCustom] = React.useState(false);
  const [pct, setPct] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);
  const loadedVersion = React.useRef<number | null | undefined>(undefined);

  React.useEffect(() => {
    if (profile.data === undefined) return;
    const v = profile.data?.version ?? 0;
    if (loadedVersion.current === v) return;
    loadedVersion.current = v;
    const p = profile.data;
    setMax(p?.installments_max ?? DEFAULT_INSTALLMENTS_MAX);
    setFree(p?.installments_interest_free ?? DEFAULT_INSTALLMENTS_INTEREST_FREE);
    const bps = p?.installment_interest_monthly_bps;
    setCustom(bps !== null && bps !== undefined);
    setPct(bps !== null && bps !== undefined ? bpsToPercent(bps) : '');
  }, [profile.data]);

  if (profile.showSkeleton) {
    return (
      <div className="space-y-3" data-testid="installments-loading">
        <Skeleton height={32} width="100%" />
        <Skeleton height={32} width="100%" announce={false} />
      </div>
    );
  }
  if (profile.isError && !profile.data) {
    return (
      <div className="space-y-2">
        <ErrorState message={`${t('common.error_loading')}: ${errorMessage(profile.error)}`} />
        <Button variant="outline" onClick={() => profile.refetch()}>{t('common.retry')}</Button>
      </div>
    );
  }
  const p = profile.data;
  if (!p) return <p role="status" className="text-sm text-muted-foreground">{t('installments.no_profile')}</p>;

  const readOnly = !isAdmin;

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    let bps: number | null = null;
    if (free > max) e.free = t('installments.free_over_max');
    if (custom) {
      bps = percentToBps(pct);
      if (bps === null) e.rate = t('installments.rate_invalid');
    }
    setErrors(e);
    if (Object.keys(e).length) return;
    try {
      const out = await save.mutateAsync(
        profileWithInstallments(p!, { installments_max: max, installments_interest_free: free, installment_interest_monthly_bps: bps }),
      );
      setSaved(true);
      onSaved?.(out);
    } catch {
      // Surfaced below via `save.error` (409 versao_conflitante included) — not swallowed.
    }
  }

  const conflict = apiErrorCode(save.error) === COMMERCE_ERROR_CODES.versaoConflitante;
  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate aria-busy={profile.isRefreshing} aria-label={t('installments.title')}>
      <div>
        <h2 className="text-base font-semibold">{t('installments.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('installments.intro')}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('installments.max')}>
          <Select value={max} disabled={readOnly} onChange={(e) => { setSaved(false); setMax(Number(e.target.value)); }}>
            {COUNTS.map((n) => <option key={n} value={n}>{n}x</option>)}
          </Select>
        </Field>
        <Field label={t('installments.free')} error={errors.free}>
          <Select value={free} disabled={readOnly} onChange={(e) => { setSaved(false); setFree(Number(e.target.value)); }}>
            {COUNTS.map((n) => <option key={n} value={n}>{n}x</option>)}
          </Select>
        </Field>
      </div>
      <fieldset className="space-y-2" disabled={readOnly}>
        <legend className="text-xs font-medium">{t('installments.rate')}</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="installments_rate" checked={!custom} onChange={() => { setSaved(false); setCustom(false); }} />
          {t('installments.rate_platform')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="installments_rate" checked={custom} onChange={() => { setSaved(false); setCustom(true); }} />
          {t('installments.rate_custom')}
        </label>
        {custom ? (
          <Field label={t('installments.rate_pct')} error={errors.rate}>
            <Input inputMode="decimal" value={pct} onChange={(e) => { setSaved(false); setPct(e.target.value); }} />
          </Field>
        ) : null}
      </fieldset>
      {readOnly ? <p className="text-xs text-muted-foreground">{t('installments.admin_only')}</p> : null}
      {conflict ? <FormError message={t('profile.conflict')} /> : save.isError ? <FormError message={errorMessage(save.error)} /> : null}
      {saved ? <p role="status" className="text-sm text-green-600">{t('common.saved')}</p> : null}
      {readOnly ? null : (
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? t('common.saving') : t('installments.save')}
        </Button>
      )}
    </form>
  );
}
