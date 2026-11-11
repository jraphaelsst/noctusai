/** Props every assignment organ takes: the hooks factory output + optional copy seams. */
import type { AssignmentHooks } from './hooks';
import type { AssignmentTranslate } from './i18n';

export interface AssignmentOrganProps {
  hooks: AssignmentHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: AssignmentTranslate;
  /** Locale for dates (default pt-BR). */
  locale?: string;
  /** Only an org admin edits: the host passes its own role decision (the server enforces it again). */
  canWrite?: boolean;
}

/** `dd/mm` style absence date in the user's locale; an unparsable value shows as-is (never blank, never NaN). */
export function formatDay(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: '2-digit' });
}

/** `<input type=date>` value (yyyy-mm-dd) -> an ISO instant at the start (or end) of that LOCAL day. */
export function dayToIso(day: string, end = false): string | null {
  if (!day) return null;
  const d = new Date(`${day}T${end ? '23:59:59' : '00:00:00'}`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
