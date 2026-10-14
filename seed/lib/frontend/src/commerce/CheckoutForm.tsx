/**
 * `<CheckoutForm/>` — buyer data, payment method and the LGPD/CDC consents
 * (CONTRACT §4 `POST /api/storefront/checkout`).
 *
 * Consent rules (enforced here for UX; the server re-enforces and answers
 * 422 `aceite_obrigatorio`, shown inline):
 *   - terms + privacy checkboxes REQUIRED (each carries its version);
 *   - marketing opt-in is OPTIONAL and UNCHECKED by default (never pre-ticked);
 *   - the immediate-delivery waiver (CDC art. 49) is shown and REQUIRED only when
 *     the quote says `requires_immediate_delivery_waiver`.
 * Totals shown come from the server quote; the server recomputes at checkout.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input, ListSkeleton, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, maskCpfOrCnpj, onlyDigits } from './format';
import { isValidCpfOrCnpj, isValidEmail } from './validation';
import { apiErrorCode, errorMessage, type CommerceHooks } from './hooks';
import { useQuoteFor } from './useQuoteFor';
import { useOptionalStorefront } from './storefrontContext';
import { InstallmentPicker } from './InstallmentPicker';
import {
  COMMERCE_ERROR_CODES,
  PAYMENT_METHODS,
  type Address,
  type CheckoutRequest,
  type CheckoutResult,
  type PaymentMethod,
  type Quote,
  type QuoteRequest,
  type StorefrontLegal,
} from './types';

export interface CheckoutFormProps {
  hooks: CommerceHooks;
  /** Items + coupon (the cart's request). */
  request: QuoteRequest;
  /** Already-fetched quote; if omitted the form fetches its own. */
  quote?: Quote | null;
  /** Legal versions; defaults to the surrounding `<StorefrontShell/>`'s. */
  legal?: StorefrontLegal;
  locale?: string;
  onSuccess: (result: CheckoutResult) => void;
}

const ADDRESS_FIELDS = ['street', 'number', 'complement', 'district', 'city', 'state', 'zip'] as const;
const ADDRESS_REQUIRED: ReadonlyArray<(typeof ADDRESS_FIELDS)[number]> = ['street', 'number', 'city', 'state', 'zip'];

export function CheckoutForm({ hooks, request, quote: quoteProp, legal: legalProp, locale, onSuccess }: CheckoutFormProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const storefront = useOptionalStorefront();
  const legal = legalProp ?? storefront?.legal;
  const q = useQuoteFor(hooks, request, quoteProp);
  const checkout = hooks.useCheckout();

  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [doc, setDoc] = React.useState('');
  const [phone, setPhone] = React.useState('');
  const [method, setMethod] = React.useState<PaymentMethod>('pix');
  const [installments, setInstallments] = React.useState(1);
  const [address, setAddress] = React.useState<Address>({});
  const [terms, setTerms] = React.useState(false);
  const [privacy, setPrivacy] = React.useState(false);
  const [marketing, setMarketing] = React.useState(false);
  const [waiver, setWaiver] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  if (q.showSkeleton) return <ListSkeleton rows={5} />;
  const quote = q.quote;
  if (!quote) {
    return q.error ? (
      <RetryError message={`${t('cart.quote_error')}: ${errorMessage(q.error)}`} onRetry={q.retry} retryLabel={t('common.retry')} />
    ) : (
      <p role="status" className="text-sm">{t('cart.empty')}</p>
    );
  }
  if (!legal) {
    return <FormError message={t('checkout.no_legal')} />;
  }

  // Card parcelamento (D33): offered only for the card and only when the quote carries a choice.
  const cardOptions = method === 'credit_card' ? (quote.installment_options ?? []) : [];
  const chosenCount = cardOptions.some((o) => o.count === installments) ? installments : 1;
  const chargedTotal = cardOptions.find((o) => o.count === chosenCount)?.total_cents ?? quote.total_cents;
  const needsWaiver = quote.requires_immediate_delivery_waiver;
  const needsAddress = quote.lines.some((l) => l.fulfillment_type === 'shipping' || l.fulfillment_type === 'local_delivery');
  const aceiteServerError = apiErrorCode(checkout.error) === COMMERCE_ERROR_CODES.aceiteObrigatorio;

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    if (name.trim().length < 3) e.name = t('common.required');
    if (!isValidEmail(email)) e.email = t('common.invalid_email');
    if (!isValidCpfOrCnpj(doc)) e.doc = t('checkout.doc_invalid');
    if (onlyDigits(phone).length < 10) e.phone = t('checkout.phone_invalid');
    if (needsAddress) for (const k of ADDRESS_REQUIRED) if (!address[k]?.trim()) e[`address.${k}`] = t('common.required');
    if (!terms) e.terms = t('checkout.terms_required');
    if (!privacy) e.privacy = t('checkout.privacy_required');
    if (needsWaiver && !waiver) e.waiver = t('checkout.waiver_required');
    return e;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;
    const body: CheckoutRequest = {
      ...request,
      buyer: { name: name.trim(), email: email.trim().toLowerCase(), doc: onlyDigits(doc), phone: onlyDigits(phone) },
      ...(needsAddress ? { address } : {}),
      payment_method: method,
      ...(method === 'credit_card' ? { installments: chosenCount } : {}),
      consents: {
        terms_version: legal!.terms_version,
        privacy_version: legal!.privacy_version,
        marketing,
        immediate_delivery_waiver: needsWaiver ? waiver : false,
      },
    };
    try {
      onSuccess(await checkout.mutateAsync(body));
    } catch {
      // Surfaced below via `checkout.error` (aceite_obrigatorio inline / FormError) — not swallowed.
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <section aria-label={t('checkout.summary')} className="rounded-md border p-3 text-sm">
        <ul className="space-y-1">
          {quote.lines.map((l) => (
            <li key={l.offer_id} className="flex justify-between">
              <span>{l.qty}× {l.title}</span>
              <span>{formatCents(l.total_cents, quote.currency, loc)}</span>
            </li>
          ))}
        </ul>
        {quote.discount_cents > 0 ? (
          <p className="mt-1 flex justify-between"><span>{t('cart.discount')}</span><span>-{formatCents(quote.discount_cents, quote.currency, loc)}</span></p>
        ) : null}
        <p className="mt-2 flex justify-between font-semibold"><span>{t('cart.total')}</span><span>{formatCents(quote.total_cents, quote.currency, loc)}</span></p>
      </section>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold">{t('checkout.buyer')}</legend>
        <Field label={t('checkout.name')} required error={errors.name}>
          <Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t('checkout.email')} required error={errors.email}>
          <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t('checkout.doc')} required error={errors.doc}>
          <Input inputMode="numeric" value={doc} onChange={(e) => setDoc(maskCpfOrCnpj(e.target.value))} />
        </Field>
        <Field label={t('checkout.phone')} required error={errors.phone}>
          <Input type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
      </fieldset>

      {needsAddress ? (
        <fieldset className="grid gap-3 sm:grid-cols-3">
          <legend className="mb-2 text-sm font-semibold">{t('checkout.address')}</legend>
          {ADDRESS_FIELDS.map((k) => (
            <Field key={k} label={t(`address.${k}`)} required={ADDRESS_REQUIRED.includes(k)} error={errors[`address.${k}`]}>
              <Input value={address[k] ?? ''} onChange={(e) => setAddress((a) => ({ ...a, [k]: e.target.value }))} />
            </Field>
          ))}
        </fieldset>
      ) : null}

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-semibold">{t('checkout.payment')}</legend>
        {PAYMENT_METHODS.map((m) => (
          <label key={m} className="flex items-center gap-2 text-sm">
            <input type="radio" name="payment_method" value={m} checked={method === m} onChange={() => setMethod(m)} />
            {t(`payment.${m}`)}
          </label>
        ))}
        <InstallmentPicker options={cardOptions} value={chosenCount} onChange={setInstallments} currency={quote.currency} locale={locale} disabled={checkout.isPending} />
      </fieldset>

      <fieldset className="space-y-2" data-testid="consents">
        <legend className="mb-1 text-sm font-semibold">{t('checkout.consents')}</legend>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} aria-invalid={!!errors.terms} />
          <span>{t('checkout.accept_terms', { version: legal.terms_version })} <span className="text-destructive">*</span></span>
        </label>
        {errors.terms ? <p role="alert" className="text-xs text-destructive">{errors.terms}</p> : null}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} aria-invalid={!!errors.privacy} />
          <span>{t('checkout.accept_privacy', { version: legal.privacy_version })} <span className="text-destructive">*</span></span>
        </label>
        {errors.privacy ? <p role="alert" className="text-xs text-destructive">{errors.privacy}</p> : null}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
          <span>{t('checkout.accept_marketing')}</span>
        </label>
        {needsWaiver ? (
          <>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={waiver} onChange={(e) => setWaiver(e.target.checked)} aria-invalid={!!errors.waiver} />
              <span>{t('checkout.accept_waiver')} <span className="text-destructive">*</span></span>
            </label>
            {errors.waiver ? <p role="alert" className="text-xs text-destructive">{errors.waiver}</p> : null}
          </>
        ) : null}
        {aceiteServerError ? <p role="alert" className="text-sm text-destructive">{t('checkout.aceite_obrigatorio')}</p> : null}
        {legal.withdrawal_text ? <p className="text-xs text-muted-foreground">{legal.withdrawal_text}</p> : null}
      </fieldset>

      {checkout.isError && !aceiteServerError ? <FormError message={errorMessage(checkout.error)} /> : null}

      <Button type="submit" disabled={checkout.isPending}>
        {checkout.isPending ? t('checkout.processing') : t('checkout.pay', { total: formatCents(chargedTotal, quote.currency, loc) })}
      </Button>
    </form>
  );
}
