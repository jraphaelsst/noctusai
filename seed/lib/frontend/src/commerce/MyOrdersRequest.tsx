/**
 * `<MyOrdersRequest/>` — "find my orders" by e-mail (CONTRACT §4
 * `POST /api/storefront/orders/access-link`). The server always answers 202 and
 * the UI always shows the SAME neutral message ("if there are orders for this
 * address, we sent a link") so the form cannot be used to enumerate customers.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, Input } from './controls';
import { useCommerceT } from './i18n';
import { errorMessage, type CommerceHooks } from './hooks';
import { isValidEmail } from './validation';

export interface MyOrdersRequestProps {
  hooks: CommerceHooks;
  locale?: string;
}

export function MyOrdersRequest({ hooks, locale }: MyOrdersRequestProps) {
  const { t } = useCommerceT(locale);
  const link = hooks.useAccessLink();
  const [email, setEmail] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!isValidEmail(email)) {
      setErr(t('common.invalid_email'));
      return;
    }
    setErr(null);
    try {
      await link.mutateAsync({ email: email.trim().toLowerCase() });
    } catch {
      // Surfaced below via `link.error` (rate limit / network) — not swallowed.
    }
  }

  if (link.isSuccess) {
    return <p role="status" className="rounded-md border p-3 text-sm">{t('myorders.sent')}</p>;
  }
  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3" noValidate>
      <h2 className="text-lg font-semibold">{t('myorders.title')}</h2>
      <p className="text-sm text-muted-foreground">{t('myorders.intro')}</p>
      <Field label={t('checkout.email')} required error={err}>
        <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      {link.isError ? <FormError message={errorMessage(link.error)} /> : null}
      <Button type="submit" disabled={link.isPending}>{link.isPending ? t('common.loading') : t('myorders.send')}</Button>
    </form>
  );
}
