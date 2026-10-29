/**
 * `<LeadCard/>` -- the funnel card: name · coloured stage tag · phone · origin · "há N dias" since first contact ·
 * free tags (neutral chips) · last-message preview.
 */
import { Badge } from '../design-system/ui/Badge';
import { stageTagClasses } from '../components/pipeline/stageTokens';
import { displayPhone, firstContactLabel, stageTagLabel } from './format';
import { t } from './i18n';
import type { Lead, LeadStageConfig } from './types';

export interface LeadCardProps {
  lead: Lead;
  /** Label of `lead.origin` (the host's config). */
  originLabel: string;
  /** The config of `lead.stage` (its tag text + colour token). Omitted -> no stage tag. */
  stage?: LeadStageConfig;
  /** Injectable clock for tests. */
  now?: number;
}

export function LeadCard({ lead, originLabel, stage, now }: LeadCardProps) {
  const phone = displayPhone(lead.phone);
  return (
    <div className="space-y-1.5 rounded-md border bg-card p-3 text-sm shadow-sm" data-testid={`lead-card-${lead.id}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 break-words font-medium leading-tight">{lead.name}</p>
        <Badge variant="outline" className="shrink-0">
          {originLabel}
        </Badge>
      </div>
      {stage ? (
        <Badge variant="outline" className={stageTagClasses(stage.color)} data-testid={`lead-stage-tag-${lead.id}`}>
          {stageTagLabel(stage, lead.stage)}
        </Badge>
      ) : null}
      <p className="text-xs text-muted-foreground">{phone || t('card.no_phone')}</p>
      <p className="text-xs text-muted-foreground" title={lead.first_contact_at}>
        {firstContactLabel(lead, now)}
      </p>
      {lead.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1" data-testid={`lead-tags-${lead.id}`}>
          {lead.tags.map((tag) => (
            <Badge key={tag} variant="muted" className="font-normal">
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}
      {lead.last_message_preview ? (
        <p className="line-clamp-2 break-words border-t pt-1.5 text-xs text-foreground/80">{lead.last_message_preview}</p>
      ) : null}
    </div>
  );
}
