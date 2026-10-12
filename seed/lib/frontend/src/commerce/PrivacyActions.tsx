/**
 * `<PrivacyActions/>` — LGPD actions on one customer: export (portability /
 * access) and anonymize (deletion) behind an in-page confirm step. The export
 * is offered as a `data:` download link so no Blob/URL API is required.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { FormError } from './controls';
import { useCommerceT } from './i18n';
import { formatDateTime } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import type { Customer } from './types';

export interface PrivacyActionsProps {
  hooks: CommerceHooks;
  customer: Pick<Customer, 'id' | 'anonymized_at' | 'email'>;
  locale?: string;
  onAnonymized?: () => void;
}

export function PrivacyActions({ hooks, customer, locale, onAnonymized }: PrivacyActionsProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const exportMut = hooks.useExportCustomer();
  const anonymize = hooks.useAnonymizeCustomer();
  const [confirming, setConfirming] = React.useState(false);
  const [download, setDownload] = React.useState<string | null>(null);

  if (customer.anonymized_at) {
    return (
      <p className="text-sm">
        <Badge variant="muted">{t('customers.anonymized')}</Badge> {formatDateTime(customer.anonymized_at, loc)}
      </p>
    );
  }

  return (
    <div className="space-y-3" aria-label={t('privacy.title')}>
      <h3 className="text-sm font-semibold">{t('privacy.title')}</h3>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          disabled={exportMut.isPending}
          onClick={async () => {
            try {
              const data = await exportMut.mutateAsync(customer.id);
              setDownload(`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(data, null, 2))}`);
            } catch {
              // Surfaced via `exportMut.error` below.
            }
          }}
        >
          {exportMut.isPending ? t('common.loading') : t('privacy.export')}
        </Button>
        {download ? (
          <a className="text-sm underline" href={download} download={`customer-${customer.id}.json`}>
            {t('privacy.download')}
          </a>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {confirming ? (
          <>
            <span className="text-sm text-destructive">{t('privacy.anonymize_confirm')}</span>
            <Button
              variant="destructive"
              disabled={anonymize.isPending}
              onClick={async () => {
                try {
                  await anonymize.mutateAsync(customer.id);
                  setConfirming(false);
                  onAnonymized?.();
                } catch {
                  // Surfaced via `anonymize.error` below.
                }
              }}
            >
              {anonymize.isPending ? t('common.saving') : t('privacy.anonymize_do')}
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>{t('common.cancel')}</Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => setConfirming(true)}>{t('privacy.anonymize')}</Button>
        )}
      </div>
      <FormError message={exportMut.error ? errorMessage(exportMut.error) : anonymize.error ? errorMessage(anonymize.error) : null} />
    </div>
  );
}
