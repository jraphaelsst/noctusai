/** Small shared pieces of the clients organ: the product noun, coloured chips, refusal text. */
import * as React from 'react';

import { stageColorClasses, stageTagClasses } from '../components/pipeline/stageTokens';
import { Badge } from '../design-system/ui/Badge';
import { cn } from '../utils';
import { nounLower } from './format';
import { apiErrorCode, errorMessage } from './hooks';
import { t } from './i18n';
import type { ClientsConfigData } from './types';

export interface NounVars extends Record<string, string> {
  Noun: string;
  Nouns: string;
  noun: string;
  nouns: string;
}

/** The product's vocabulary for `t(key, vars)` (generic fallback until the config answers). */
export function nounVars(config: ClientsConfigData | undefined): NounVars {
  const Noun = config?.noun_singular || t('noun.singular');
  const Nouns = config?.noun_plural || t('noun.plural');
  return { Noun, Nouns, noun: nounLower(Noun), nouns: nounLower(Nouns) };
}

/** A label in a pipeline colour token (status, session status, payment status). */
export function ToneBadge({ color, children, className, testId }: { color: string | null | undefined; children: React.ReactNode; className?: string; testId?: string }) {
  return (
    <Badge variant="outline" className={cn(stageTagClasses(color), className)} data-testid={testId}>
      {children}
    </Badge>
  );
}

/** Free-text tags as neutral chips. */
export function TagChips({ tags, testId }: { tags: string[]; testId?: string }) {
  if (tags.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1" data-testid={testId}>
      {tags.map((tag) => (
        <Badge key={tag} variant="muted" className="font-normal">
          {tag}
        </Badge>
      ))}
    </span>
  );
}

/** A refusal in pt-BR: the known codes by name, anything else with the server's message. */
export function clientsErrorText(err: unknown, fallbackKey = 'form.error', vars?: Record<string, string>): string {
  const code = apiErrorCode(err);
  for (const k of code ? [`error.${code}`, `error.${code.toUpperCase()}`] : []) {
    const mapped = t(k, vars);
    if (mapped !== k) return mapped;
  }
  return `${t(fallbackKey, vars)}: ${errorMessage(err)}`;
}

/** A tile with a label and a big number (finance totals, summary). */
export function StatTile({ label, value, tone, testId }: { label: string; value: React.ReactNode; tone?: string; testId?: string }) {
  return (
    <div className="rounded-md border bg-card p-3" data-testid={testId}>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-1 text-lg font-semibold', tone && stageColorClasses(tone).color)}>{value}</p>
    </div>
  );
}
