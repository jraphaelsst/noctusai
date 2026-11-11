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
 *
 * NAMED SEAM `choices` (2026-11-10, Assistant S4): a closed set of labelled verdicts instead of thumbs, for an owner
 * EVALUATING a model (`ai_feedback_events` -- append-only, one event per judgement). The component is then
 * CONTROLLED: it renders `choices`, shows `selected`, and hands the pick to `onChoose`; the product owns the write
 * (a `useCacheWriteMutation` against its own route). It does not touch `/api/ai/feedback`. Optional `shortcut` keys
 * are bound on `window` while mounted (ignored inside inputs / with a modifier held).
 *
 *   <AIFeedbackButtons output_ref="..." choices={[{ value: 'sim', label: 'Sim', shortcut: '1' }, ...]}
 *                      selected={null} onChoose={(v) => save(v)} />
 */
import * as React from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';

import { useAIFeedback, useSubmitAIFeedback, type AIFeedbackRating } from './useAIFeedback';

export interface AIFeedbackChoice {
  /** The value handed to `onChoose` (e.g. the enum the backend stores). */
  value: string;
  /** Visible button text. */
  label: string;
  /** Optional single-key shortcut (compared case-insensitively against `KeyboardEvent.key`). */
  shortcut?: string;
}

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
  /** NAMED SEAM: a closed set of labelled verdicts instead of thumbs. Switches the component to controlled mode. */
  choices?: AIFeedbackChoice[];
  /** Controlled mode: the currently chosen value (null/undefined = none yet). */
  selected?: string | null;
  /** Controlled mode: called with the picked `value`. The caller performs (and owns the state of) the write. */
  onChoose?: (value: string) => void;
  /** Controlled mode: block picks (e.g. while the write is pending). */
  disabled?: boolean;
}

export function AIFeedbackButtons(props: AIFeedbackButtonsProps) {
  // Two components, not a conditional hook: the thumbs path keeps its exact hook order.
  if (props.choices && props.choices.length > 0) return <AIChoiceButtons {...props} choices={props.choices} />;
  return <AIThumbsButtons {...props} />;
}

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName);
}

function AIChoiceButtons({
  choices,
  selected,
  onChoose,
  disabled,
  className,
}: AIFeedbackButtonsProps & { choices: AIFeedbackChoice[] }) {
  React.useEffect(() => {
    if (!onChoose || disabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return;
      const hit = choices.find((c) => c.shortcut && c.shortcut.toLowerCase() === e.key.toLowerCase());
      if (hit) {
        e.preventDefault();
        onChoose(hit.value);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [choices, onChoose, disabled]);

  return (
    <span className={className} role="group" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {choices.map((c) => (
        <button
          key={c.value}
          type="button"
          data-testid={`ai-choice-${c.value}`}
          aria-pressed={selected === c.value}
          disabled={disabled}
          onClick={() => onChoose?.(c.value)}
          style={_choiceStyle(selected === c.value)}
        >
          {c.label}
          {c.shortcut ? <kbd style={{ marginLeft: 6, opacity: 0.7, fontSize: 11 }}>{c.shortcut}</kbd> : null}
        </button>
      ))}
    </span>
  );
}

function _choiceStyle(active: boolean): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '8px 14px',
    border: '1px solid var(--border, #d0d0d0)',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 14,
    background: active ? 'var(--primary, #1a73e8)' : 'transparent',
    color: active ? 'var(--primary-foreground, white)' : 'inherit',
  };
}

function AIThumbsButtons({
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
