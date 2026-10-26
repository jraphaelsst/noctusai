/** `<LeadCard/>` -- the funnel card: name · phone · origin · "há N dias" since first contact · last-message preview. */
import { Badge } from '../design-system/ui/Badge';
import { displayPhone, firstContactLabel } from './format';
import { t } from './i18n';
import type { Lead } from './types';

export interface LeadCardProps {
  lead: Lead;
  /** Label of `lead.origin` (the host's config). */
  originLabel: string;
  /** Injectable clock for tests. */
  now?: number;
}

export function LeadCard({ lead, originLabel, now }: LeadCardProps) {
  const phone = displayPhone(lead.phone);
  return (
    <div className="space-y-1.5 rounded-md border bg-card p-3 text-sm shadow-sm" data-testid={`lead-card-${lead.id}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 break-words font-medium leading-tight">{lead.name}</p>
        <Badge variant="outline" className="shrink-0">
          {originLabel}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{phone || t('card.no_phone')}</p>
      <p className="text-xs text-muted-foreground" title={lead.first_contact_at}>
        {firstContactLabel(lead, now)}
      </p>
      {lead.last_message_preview ? (
        <p className="line-clamp-2 break-words border-t pt-1.5 text-xs text-foreground/80">{lead.last_message_preview}</p>
      ) : null}
    </div>
  );
}
