/**
 * `<MonthlyNarrativeCard/>` — PF dashboard surface for the monthly
 * narrative service (PF-monthly-narrative AI feature).
 *
 * Wraps the seed-lib `<DigestCard/>` with PF-specific data: consumes
 * `useMonthlyNarrative()`, splits the prose into paragraphs, threads
 * a stable `outputRef` for `<AIFeedbackButtons/>`.
 *
 * Mounted on `pages/Dashboard.tsx`.
 */
import { DigestCard, splitProseIntoParagraphs } from '@noctusai/lib/design-system';

import { useMonthlyNarrative } from '@/hooks/useAI';

export function MonthlyNarrativeCard() {
  const periodDays = 30;
  const { data, isLoading, error } = useMonthlyNarrative(periodDays);

  // The backend returns `{subject, html, text, summary}`. We render the
  // plain-text variant (paragraph-friendly) — `html` is for email.
  const paragraphs = splitProseIntoParagraphs(data?.text);

  // Stable per-period outputRef so feedback rows correlate to a specific
  // month's narrative (not "the most recent narrative").
  const periodToken = new Date().toISOString().slice(0, 7); // YYYY-MM
  const outputRef = `digest:pf:monthly:${periodToken}`;

  return (
    <DigestCard
      title={data?.subject || 'Resumo financeiro do mês'}
      paragraphs={paragraphs}
      outputRef={outputRef}
      isLoading={isLoading}
      error={error}
    />
  );
}

export default MonthlyNarrativeCard;
