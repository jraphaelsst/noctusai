/**
 * `<StorefrontShell/>` — the public storefront frame (CONTRACT §4 `GET /api/storefront`).
 *
 * - `brand_tokens` → CSS variables on the wrapper (`--commerce-<token>`) so every
 *   storefront component themes without a build step.
 * - Legal footer with the Decreto 7.962 art. 2 disclosures: legal name, CNPJ,
 *   address, contact (+ the withdrawal text).
 * - Mounts a `CommerceLocaleProvider` from the store's `locale`.
 * - Unknown host (404) renders the "no store on this address" state.
 */
import * as React from 'react';
import { Skeleton } from '../design-system/ui/Skeleton';
import { ErrorState } from './controls';
import { Button } from '../design-system/ui/Button';
import { CommerceLocaleProvider, useCommerceT } from './i18n';
import { maskCnpj } from './format';
import { apiErrorStatus, errorMessage, type CommerceHooks } from './hooks';
import { StorefrontContext } from './storefrontContext';
import type { Address, BrandTokens, Storefront } from './types';

export { useStorefrontData } from './storefrontContext';

/** `brand_tokens` → inline CSS variables. Only safe token names/values are emitted. */
export function brandTokensToCssVars(tokens: BrandTokens | undefined): React.CSSProperties {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(tokens ?? {})) {
    if (/^[a-z][a-z0-9_-]*$/i.test(k) && typeof v === 'string' && !/[;{}<>]/.test(v)) {
      out[`--commerce-${k.replace(/_/g, '-')}`] = v;
    }
  }
  return out as React.CSSProperties;
}

export function formatAddress(a: Address | undefined): string {
  if (!a) return '';
  const line1 = [a.street, a.number].filter(Boolean).join(', ');
  const line2 = [a.complement, a.district].filter(Boolean).join(' - ');
  const line3 = [a.city, a.state].filter(Boolean).join('/');
  return [line1, line2, line3, a.zip].filter(Boolean).join(' · ');
}

export interface StorefrontShellProps {
  hooks: CommerceHooks;
  children: React.ReactNode;
  /** Optional nav/cart slot rendered at the right of the header. */
  headerActions?: React.ReactNode;
  /** Header title click (e.g. navigate home). */
  onHome?: () => void;
}

export function StorefrontShell({ hooks, children, headerActions, onHome }: StorefrontShellProps) {
  const sf = hooks.useStorefront();
  const data = sf.data;

  if (sf.showSkeleton) {
    return (
      <div className="space-y-4 p-6" data-testid="storefront-loading">
        <Skeleton height={48} width="100%" />
        <Skeleton height={240} width="100%" announce={false} />
      </div>
    );
  }
  if (!data) {
    return <ShellProblem notFound={apiErrorStatus(sf.error) === 404} message={sf.error ? errorMessage(sf.error) : ''} onRetry={() => sf.refetch()} />;
  }
  const tok = data.brand_tokens ?? {};
  return (
    <StorefrontContext.Provider value={data}>
      <CommerceLocaleProvider locale={data.locale}>
        <div
          data-testid="storefront-shell"
          className="flex min-h-screen flex-col"
          style={{ ...brandTokensToCssVars(tok), background: 'var(--commerce-background, #fff)', color: 'var(--commerce-foreground, #0f172a)' }}
        >
          <header className="flex items-center justify-between border-b px-6 py-4" style={{ borderColor: 'var(--commerce-secondary, #e2e8f0)' }}>
            <button type="button" onClick={onHome} className="text-lg font-semibold" style={{ color: 'var(--commerce-primary, #4f46e5)' }}>
              {data.trade_name}
            </button>
            <div>{headerActions}</div>
          </header>
          <main className="flex-1 p-6">{children}</main>
          <LegalFooter storefront={data} />
        </div>
      </CommerceLocaleProvider>
    </StorefrontContext.Provider>
  );
}

function ShellProblem({ notFound, message, onRetry }: { notFound: boolean; message: string; onRetry: () => void }) {
  const { t } = useCommerceT();
  if (notFound) {
    return (
      <div className="p-10 text-center" data-testid="storefront-no-store">
        <h1 className="text-lg font-semibold">{t('shell.no_store_title')}</h1>
        <p className="text-sm text-muted-foreground">{t('shell.no_store_body')}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2 p-10 text-center">
      <ErrorState message={`${t('common.error_loading')}: ${message}`} />
      <Button variant="outline" onClick={onRetry}>{t('common.retry')}</Button>
    </div>
  );
}

export function LegalFooter({ storefront: s }: { storefront: Storefront }) {
  const { t } = useCommerceT();
  const address = formatAddress(s.address);
  return (
    <footer className="border-t px-6 py-4 text-xs" style={{ borderColor: 'var(--commerce-secondary, #e2e8f0)' }} data-testid="legal-footer">
      <p className="font-medium">{s.legal_name}</p>
      <p>CNPJ {maskCnpj(s.cnpj)}</p>
      {address ? <p>{address}</p> : null}
      <p>
        {[s.contact?.email, s.contact?.phone].filter(Boolean).join(' · ')}
      </p>
      {s.legal?.withdrawal_text ? <p className="mt-2 text-muted-foreground">{s.legal.withdrawal_text}</p> : null}
      <p className="mt-2 text-muted-foreground">
        {t('footer.terms')} v{s.legal?.terms_version} · {t('footer.privacy')} v{s.legal?.privacy_version}
      </p>
    </footer>
  );
}
