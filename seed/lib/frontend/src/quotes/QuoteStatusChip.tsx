/** `<QuoteStatusChip/>` — the quote's status as a pill (and, optionally, its convert-on-accept state). */
import { Badge } from './controls';
import { defaultQuotesT, type QuotesTranslate } from './i18n';
import type { QuoteConversionStatus, QuoteStatus } from './types';

const VARIANT: Record<QuoteStatus, 'default' | 'destructive' | 'muted' | 'outline'> = {
  draft: 'muted',
  sent: 'outline',
  viewed: 'outline',
  accepted: 'default',
  rejected: 'destructive',
  expired: 'muted',
  superseded: 'muted',
};

export interface QuoteStatusChipProps {
  status: QuoteStatus;
  t?: QuotesTranslate;
}

export function QuoteStatusChip({ status, t = defaultQuotesT }: QuoteStatusChipProps) {
  return <Badge variant={VARIANT[status] ?? 'muted'} data-status={status}>{t(`status.${status}`)}</Badge>;
}

export interface QuoteConversionChipProps {
  status: QuoteConversionStatus;
  t?: QuotesTranslate;
}

/** Hidden for `none` (nothing to convert). `failed` is a destructive pill: an operator must act. */
export function QuoteConversionChip({ status, t = defaultQuotesT }: QuoteConversionChipProps) {
  if (status === 'none') return null;
  const variant = status === 'failed' ? 'destructive' : status === 'done' ? 'default' : 'outline';
  return <Badge variant={variant} data-conversion={status}>{t(`conversion.${status}`)}</Badge>;
}
