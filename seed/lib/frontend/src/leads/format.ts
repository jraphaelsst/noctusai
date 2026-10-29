/** Pure display helpers of the leads organ (pt-BR). */
import { formatPhone } from '../phone';
import type { Lead, LeadFiltersState, LeadStageConfig, LeadsConfigData } from './types';

const DAY_MS = 86_400_000;

/** Whole calendar days between `iso` and `now` (never negative). */
export function daysSince(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const startOf = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.max(0, Math.round((startOf(new Date(now)) - startOf(then)) / DAY_MS));
}

/** "hoje" · "há 1 dia" · "há N dias". */
export function daysLabel(days: number | null): string {
  if (days === null) return '';
  if (days === 0) return 'hoje';
  return days === 1 ? 'há 1 dia' : `há ${days} dias`;
}

export function firstContactLabel(lead: Pick<Lead, 'first_contact_at'>, now?: number): string {
  return daysLabel(daysSince(lead.first_contact_at, now));
}

export function displayPhone(phone: string | null | undefined): string {
  return phone ? (formatPhone(phone) ?? phone) : '';
}

export function originLabel(config: LeadsConfigData | undefined, slug: string): string {
  return config?.origins.find((o) => o.slug === slug)?.label ?? slug;
}

export function stageLabel(config: LeadsConfigData | undefined, slug: string): string {
  return config?.stages.find((s) => s.slug === slug)?.label ?? slug;
}

export function stageOf(config: LeadsConfigData | undefined, slug: string): LeadStageConfig | undefined {
  return config?.stages.find((s) => s.slug === slug);
}

/** The coloured tag text of a stage: its `tag`, else its label (an unknown stage shows its slug). */
export function stageTagLabel(stage: LeadStageConfig | undefined, slug = ''): string {
  return stage?.tag || stage?.label || slug;
}

/** The query string of a list / board request: empty filters are not sent. */
export function filterQuery(f: LeadFiltersState = {}): Record<string, string> {
  const out: Record<string, string> = {};
  if (f.q?.trim()) out.q = f.q.trim();
  if (f.origin) out.origin = f.origin;
  if (f.from) out.from = f.from;
  if (f.to) out.to = f.to;
  if (f.stage) out.stage = f.stage;
  return out;
}

export function hasActiveFilters(f: LeadFiltersState = {}): boolean {
  return Object.keys(filterQuery(f)).length > 0;
}

/** `YYYY-MM-DD` of an ISO instant for a date input (local calendar day). */
export function toDateInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Noon of a date-input day, as ISO (noon keeps the calendar day stable across time zones). */
export function fromDateInput(day: string): string | null {
  if (!day) return null;
  const d = new Date(`${day}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function splitTags(text: string): string[] {
  return text.split(',').map((t) => t.trim()).filter(Boolean);
}
