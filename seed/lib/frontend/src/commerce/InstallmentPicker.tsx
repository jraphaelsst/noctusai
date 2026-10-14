/**
 * `<InstallmentPicker/>` — the buyer's card parcelamento choice (CONTRACT P4 §2.4 / D33). Options come from the
 * server quote (`Quote.installment_options`): count, regular parcela and the TOTAL the buyer pays in all —
 * interest included once the count passes the store's interest-free limit. The picker only presents; the server
 * re-validates the chosen count at checkout (422 `parcelamento_invalido`). Renders nothing when the quote
 * offers a single option (no choice to make).
 */
import { useCommerceT } from './i18n';
import { formatCents } from './format';
import type { InstallmentOption } from './types';

export interface InstallmentPickerProps {
  options: readonly InstallmentOption[];
  value: number;
  onChange: (count: number) => void;
  currency?: string;
  locale?: string;
  disabled?: boolean;
}

export function InstallmentPicker({ options, value, onChange, currency = 'BRL', locale, disabled }: InstallmentPickerProps) {
  const { t, locale: loc } = useCommerceT(locale);
  if (options.length <= 1) return null;
  const fmt = (c: number) => formatCents(c, currency, loc);
  const chosen = options.find((o) => o.count === value);
  return (
    <fieldset className="space-y-1" data-testid="installment-picker" disabled={disabled}>
      <legend className="mb-1 text-sm font-semibold">{t('picker.label')}</legend>
      {options.map((o) => (
        <label key={o.count} className="flex items-center gap-2 text-sm">
          <input type="radio" name="installments" value={o.count} checked={value === o.count} onChange={() => onChange(o.count)} />
          {o.count === 1
            ? t('picker.single', { total: fmt(o.total_cents) })
            : o.interest_free
              ? t('picker.free', { count: o.count, value: fmt(o.installment_cents) })
              : t('picker.interest', { count: o.count, value: fmt(o.installment_cents), total: fmt(o.total_cents) })}
        </label>
      ))}
      {chosen && !chosen.interest_free ? (
        <p className="text-xs text-muted-foreground" data-testid="installment-total">{t('picker.total_charged', { total: fmt(chosen.total_cents) })}</p>
      ) : null}
    </fieldset>
  );
}
