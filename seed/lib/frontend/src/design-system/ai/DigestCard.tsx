/**
 * `<DigestCard/>` — uniform container for AI-generated digest narratives
 * across products. Used by PF monthly narrative, Daily Life weekly
 * review, Mailing campaign debrief, Core admin audit digest.
 *
 * Each consumer wraps the card with its own data hook + placement;
 * the card itself just renders the standard shape:
 *   - title (always)
 *   - optional headerActions slot (e.g. period selector)
 *   - paragraphs (the digest prose, split into blocks)
 *   - `<AIFeedbackButtons/>` (when `outputRef` provided)
 *   - loading + error + empty states
 *
 * Renders nothing destructive on error / empty data — the digest is
 * informational; if it can't load, the card surfaces the error inline
 * but doesn't break the surrounding page. LGPD note: digest narratives
 * may contain personal data summaries (PF financial diary, Daily Life
 * personal narrative); the consent guard at the BACKEND prevents
 * generation without consent. The frontend just renders whatever the
 * backend returned — no additional gating here.
 */
import * as React from 'react';
import { Sparkles, AlertCircle } from 'lucide-react';

import { AIFeedbackButtons } from './AIFeedbackButtons';

export interface DigestCardProps {
  /** Header title (e.g. "Resumo do mês", "Sua semana", "Debrief da campanha"). */
  title: string;
  /**
   * Digest prose split into paragraphs. Pass either a pre-split array,
   * or call `splitProseIntoParagraphs(prose)` to derive from a raw string
   * (splits on blank lines).
   */
  paragraphs?: string[];
  /**
   * Stable identifier for `<AIFeedbackButtons/>` — convention:
   *   `digest:<service>:<period_token>` (e.g. `digest:pf:monthly:2026-04`).
   * When omitted, no feedback buttons render (use for surfaces that
   * don't support feedback yet — but prefer to wire feedback on day one
   * per `KB § 04-SHARED-LIBRARY § ai_feedback/`).
   */
  outputRef?: string;
  /**
   * Optional prompt version snapshot — written once on first feedback
   * so analytics can correlate ratings with prompt revisions.
   */
  promptVersion?: string;
  /** Loading state — show skeleton. */
  isLoading?: boolean;
  /** Error state — show inline error block. Pass the error directly. */
  error?: Error | null;
  /**
   * Optional header actions slot — period selectors, retry buttons,
   * "regenerate" actions. Renders to the right of the title.
   */
  headerActions?: React.ReactNode;
  /** Optional className appended to the wrapper. */
  className?: string;
}

/**
 * Split a raw prose string into paragraphs by blank lines. Trims each
 * paragraph; empty paragraphs are dropped.
 */
export function splitProseIntoParagraphs(prose: string | null | undefined): string[] {
  if (!prose) return [];
  return prose
    .split(/\n\s*\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function DigestCard({
  title,
  paragraphs,
  outputRef,
  promptVersion,
  isLoading,
  error,
  headerActions,
  className = '',
}: DigestCardProps) {
  return (
    <section
      className={`rounded-lg border border-border bg-background p-4 sm:p-5 ${className}`}
      aria-labelledby="digest-card-title"
    >
      <header className="mb-3 flex items-start justify-between gap-3">
        <h3
          id="digest-card-title"
          className="inline-flex items-center gap-2 text-base font-semibold text-foreground"
        >
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          {title}
        </h3>
        {headerActions && (
          <div className="flex shrink-0 items-center gap-2">{headerActions}</div>
        )}
      </header>

      {isLoading ? (
        <div className="space-y-2">
          <div className="h-4 w-5/6 animate-pulse rounded bg-muted" />
          <div className="h-4 w-4/6 animate-pulse rounded bg-muted" />
          <div className="h-4 w-3/6 animate-pulse rounded bg-muted" />
        </div>
      ) : error ? (
        <div
          role="alert"
          className="inline-flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <span>{error.message || 'Não foi possível carregar este resumo.'}</span>
        </div>
      ) : !paragraphs || paragraphs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nenhum conteúdo disponível para este período ainda.
        </p>
      ) : (
        <div className="space-y-3 text-sm leading-relaxed text-foreground">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}

      {outputRef && !isLoading && !error && paragraphs && paragraphs.length > 0 && (
        <footer className="mt-4 flex items-center justify-end border-t border-border pt-3">
          <AIFeedbackButtons
            output_ref={outputRef}
            prompt_version={promptVersion}
            size="sm"
          />
        </footer>
      )}
    </section>
  );
}

export default DigestCard;
