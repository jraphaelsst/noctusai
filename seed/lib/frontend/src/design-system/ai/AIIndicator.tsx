/**
 * AIIndicator — drop-in component for surfacing AI outputs on any entity page.
 *
 *   <AIIndicator refType="ativo" refId={imovel.id} />
 *   <AIIndicator refType="contato" refId={contato.id} />
 *   <AIIndicator refType="campanha" refId={campanha.id} />
 *
 * Auto-hides when `refId` is null OR no AI output exists for the entity.
 * Shows the most-recent output by default; pass `showAll` to render every
 * row (the Metas product has its own MetaEventoIndicator that shows all
 * rows — this component is for simpler one-line cases).
 *
 * Backed by the `ai_outputs` standard router (`/api/ai/outputs`) shipped
 * by ai-expansion Tier 2 Phase 3 (P1 pattern). The data shape comes from
 * `noctusai_lib.ai.outputs.AIOutput` — keep `./types.ts` in sync.
 */
import React from 'react';
import { Sparkles } from 'lucide-react';

import { ScorePill } from '../gamification/ScorePill';
import { useAIOutputFor } from './useAIOutputFor';
import { AIFeedbackButtons } from './AIFeedbackButtons';
import type { AIOutput } from './types';

export interface AIIndicatorProps {
  refType: string;
  refId: string | null | undefined;
  /** Show every output row (default: only the most recent). */
  showAll?: boolean;
  /** Optional className appended to the root container. */
  className?: string;
  /** Optional override for the empty-state — defaults to `null` (silent hide). */
  emptyFallback?: React.ReactNode;
  /** Hide the leading sparkles icon (e.g. inside dense table cells). */
  hideIcon?: boolean;
  /** Mount `<AIFeedbackButtons>` next to each output row (X3 — Phase 17).
   *  Off by default to keep existing call sites unchanged. */
  enableFeedback?: boolean;
}

export function AIIndicator({
  refType,
  refId,
  showAll = false,
  className = '',
  emptyFallback = null,
  hideIcon = false,
  enableFeedback = false,
}: AIIndicatorProps) {
  const { data: outputs = [], isLoading } = useAIOutputFor(refType, refId);

  if (isLoading || !refId) return null;
  if (!outputs.length) return <>{emptyFallback}</>;

  const items = showAll ? outputs : outputs.slice(0, 1);

  return (
    <div
      className={`inline-flex flex-wrap items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm ${className}`}
    >
      {!hideIcon && <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />}
      {items.map((out, i) => (
        <span key={out.id ?? i} className="inline-flex items-center gap-1.5">
          <AIOutputRow output={out} />
          {enableFeedback && out.id && (
            <AIFeedbackButtons
              output_ref={`ai_output:${out.id}`}
              prompt_version={out.prompt_version ?? undefined}
              size="sm"
              hideThankYou
            />
          )}
        </span>
      ))}
    </div>
  );
}


function AIOutputRow({ output }: { output: AIOutput }) {
  const { kind, label, score, chip, explanation, confidence } = output;
  // For score-kind outputs, use ScorePill if a numeric score is present;
  // otherwise fall back to label text.
  const showScorePill = kind === 'score' && score !== null && score !== undefined;
  const showFlag = kind === 'flag';
  const tooltipText = explanation || (confidence != null ? `Confiança: ${(confidence * 100).toFixed(0)}%` : undefined);

  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={tooltipText}
    >
      {chip && (
        <span className="inline-flex items-center rounded-full border border-border bg-background px-2 py-0.5 text-xs font-medium">
          {chip}
        </span>
      )}
      {showScorePill ? (
        <ScorePill value={score} label={label} precision={1} />
      ) : showFlag ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
          {label}
        </span>
      ) : (
        <span className="text-foreground">{label}</span>
      )}
      {confidence != null && !showScorePill && (
        <span className="text-xs text-muted-foreground">
          · {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
}
