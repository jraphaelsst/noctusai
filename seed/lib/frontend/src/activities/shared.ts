/** Props every activities organ takes: the hooks factory output + optional copy / label seams. */
import type { ActivitiesHooks } from './hooks';
import type { ActivitiesTranslate } from './i18n';
import type { AssigneeOption } from './types';

export interface ActivitiesOrganProps {
  hooks: ActivitiesHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: ActivitiesTranslate;
  locale?: string;
  /** Who can be assigned (the team layer owns names). Omitted => the assignee picker is not drawn. */
  assigneeOptions?: readonly AssigneeOption[];
  /** Assignee display name; the host maps a user id -> label (default: none shown). */
  assigneeLabel?: (userId: string) => string | null;
}

export function formatDue(value: string | null, locale = 'pt-BR'): string {
  if (!value) return '';
  return new Date(value).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
}

/** `<input type="datetime-local">` value <-> ISO. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}
