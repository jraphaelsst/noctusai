/**
 * `<AIFeedbackButtons output_ref/>` — X3 cross-cutting feedback widget
 * shipped by ai-expansion Phase 17 (2026-04-25).
 *
 * Renders thumbs-up / thumbs-down buttons next to any AI surface. Click
 * upserts a row in `<schema>.ai_feedback`; the second click on the same
 * direction is a no-op (UNIQUE(user_id, output_ref) makes it idempotent),
 * the second click on the OPPOSITE direction overwrites.
 *
 * Mount next to `<AIIndicator>` (indicators) or above digest narratives.
 *
 *   <AIFeedbackButtons output_ref={`ai_output:${output.id}`} />
 *   <AIFeedbackButtons output_ref={`digest:audit:${period_token}`} />
 */
import * as React from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';

import { useAIFeedback, useSubmitAIFeedback, type AIFeedbackRating } from './useAIFeedback';

export interface AIFeedbackButtonsProps {
  /** Stable identifier for the output. Conventions:
   *    - indicator: `"ai_output:<uuid>"`
   *    - digest:    `"digest:<service>:<token>"`  */
  output_ref: string;
  /** Optional prompt version snapshot — written once on first feedback so
   *  analytics can correlate ratings with prompt revisions. */
  prompt_version?: string;
  /** Compact size (12px icons) for tight surfaces; default 14px. */
  size?: 'sm' | 'md';
  /** Hide the "obrigado" toast string after rating. Default false. */
  hideThankYou?: boolean;
  /** Optional className passthrough for the wrapper. */
  className?: string;
}

export function AIFeedbackButtons({
  output_ref,
  prompt_version,
  size = 'md',
  hideThankYou,
  className,
}: AIFeedbackButtonsProps) {
  const { data: existing } = useAIFeedback(output_ref);
  const submit = useSubmitAIFeedback();
  const [optimisticRating, setOptimisticRating] = React.useState<AIFeedbackRating | null>(null);

  const currentRating = optimisticRating ?? existing?.rating ?? null;
  const iconSize = size === 'sm' ? 12 : 14;
  const justSubmitted = !hideThankYou && submit.isSuccess && optimisticRating !== null;

  const onClick = (rating: AIFeedbackRating) => {
    if (currentRating === rating) return; // no-op on duplicate
    setOptimisticRating(rating);
    submit.mutate(
      { output_ref, rating, prompt_version },
      { onError: () => setOptimisticRating(null) },
    );
  };

  return (
    <span
      className={className}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}
    >
      <button
        type="button"
        onClick={() => onClick(1)}
        title="Útil"
        aria-pressed={currentRating === 1}
        disabled={submit.isPending}
        style={_buttonStyle(currentRating === 1)}
      >
        <ThumbsUp size={iconSize} />
      </button>
      <button
        type="button"
        onClick={() => onClick(-1)}
        title="Não útil"
        aria-pressed={currentRating === -1}
        disabled={submit.isPending}
        style={_buttonStyle(currentRating === -1)}
      >
        <ThumbsDown size={iconSize} />
      </button>
      {justSubmitted && (
        <span style={{ color: 'var(--muted-foreground, #666)', marginLeft: 4 }}>
          Obrigado!
        </span>
      )}
    </span>
  );
}

function _buttonStyle(active: boolean): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 22,
    height: 22,
    padding: 0,
    border: '1px solid transparent',
    borderRadius: 4,
    cursor: 'pointer',
    background: active ? 'var(--primary, #1a73e8)' : 'transparent',
    color: active ? 'var(--primary-foreground, white)' : 'var(--muted-foreground, #666)',
    transition: 'background 120ms ease, color 120ms ease',
  };
}

export default AIFeedbackButtons;
