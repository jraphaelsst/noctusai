/**
 * `<WeeklyReviewCard/>` — Daily Life dashboard surface for the weekly
 * review service (D6 — past-week review for the calling user).
 *
 * Wraps the seed-lib `<DigestCard/>` with Daily Life-specific data:
 * consumes `useWeeklyReview()`, splits the prose into paragraphs,
 * threads a stable `outputRef` for `<AIFeedbackButtons/>`.
 *
 * Mounted on `pages/Dashboard.tsx` below the stats cards.
 */
import { DigestCard, splitProseIntoParagraphs } from '@noctusai/lib/design-system';

import { useWeeklyReview } from '@/hooks/useAI';

export function WeeklyReviewCard() {
  const periodDays = 7;
  const { data, isLoading, error } = useWeeklyReview(periodDays);

  const paragraphs = splitProseIntoParagraphs(data?.text);

  // ISO week token (YYYY-Www) anchors the feedback row to a specific week.
  // Compute from current date — this is the most-recent-week digest.
  const now = new Date();
  const isoYear = now.getFullYear();
  const isoWeek = (() => {
    const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  })();
  const periodToken = `${isoYear}-W${String(isoWeek).padStart(2, '0')}`;
  const outputRef = `digest:daily_life:weekly:${periodToken}`;

  return (
    <DigestCard
      title={data?.subject || 'Sua semana — revisão'}
      paragraphs={paragraphs}
      outputRef={outputRef}
      isLoading={isLoading}
      error={error}
    />
  );
}

export default WeeklyReviewCard;
