/**
 * `<CampaignDebriefSection/>` — Mailing CampaignDetail tab content for the
 * AI campaign-debrief service (M4 — narrative summary of campaign
 * performance).
 *
 * Wraps the seed-lib `<DigestCard/>` with Mailing-specific data:
 * consumes `useCampaignDebrief(campaignId)`, splits the prose into
 * paragraphs, threads a stable `outputRef` for `<AIFeedbackButtons/>`.
 *
 * Mounted on `pages/CampaignDetail.tsx` as the "Debrief" section.
 */
import { DigestCard, splitProseIntoParagraphs } from '@noctusai/lib/design-system';

import { useCampaignDebrief } from '@/hooks/useAI';

export interface CampaignDebriefSectionProps {
  campaignId: string;
}

export function CampaignDebriefSection({ campaignId }: CampaignDebriefSectionProps) {
  const { data, isLoading, error } = useCampaignDebrief(campaignId);

  const paragraphs = splitProseIntoParagraphs(data?.text);

  // Stable per-campaign outputRef so feedback rows correlate to a
  // specific debrief (not "the most recent debrief").
  const outputRef = `digest:mailing:debrief:${campaignId}`;

  return (
    <DigestCard
      title={data?.subject || 'Debrief da campanha'}
      paragraphs={paragraphs}
      outputRef={outputRef}
      isLoading={isLoading}
      error={error}
    />
  );
}

export default CampaignDebriefSection;
