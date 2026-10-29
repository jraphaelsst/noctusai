/**
 * Pure display + calendar helpers of the clients organ (pt-BR).
 *
 * Every date / time of the organ is shown and TYPED in the org's zone (`config.timezone`), not the browser's: a
 * therapist travelling must still see "14:00" for the 14:00 session. `zonedParts` reads an instant in that zone,
 * `zonedIso` turns a typed date + time back into an ISO instant WITH the zone's offset (what the API expects).
 */
import type { ClientFiltersState, ClientFinanceEntry, ClientsConfigData, ClientStatusConfig, PaymentStatus } from './types';

/** The browser's zone -- only until the config (the org's zone) has answered. */
export function fallbackTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

export const tzOf = (config: ClientsConfigData | undefined): string => config?.timezone || fallbackTimezone();

const pad = (n: number) => String(n).padStart(2, '0');

interface ZonedParts {
  /** `YYYY-MM-DD` in the zone. */
  date: string;
  /** `HH:MM` in the zone. */
  time: string;
  /** 0 = Monday ... 6 = Sunday. */
  weekday: number;
}

function partsAt(ms: number, tz: string) {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  const out: Record<string, number> = {};
  for (const p of fmt.formatToParts(new Date(ms))) if (p.type !== 'literal') out[p.type] = Number(p.value);
  return { y: out.year, m: out.month, d: out.day, h: out.hour % 24, mi: out.minute, s: out.second };
}

/** The wall-clock date / time / weekday of an instant in `tz`; null for a bad instant. */
export function zonedParts(iso: string | null | undefined, tz: string): ZonedParts | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  const p = partsAt(ms, tz);
  const date = `${p.y}-${pad(p.m)}-${pad(p.d)}`;
  return { date, time: `${pad(p.h)}:${pad(p.mi)}`, weekday: weekdayOf(date) };
}

/** Minutes `tz` is ahead of UTC at the instant `ms`. */
function offsetMinutes(ms: number, tz: string): number {
  const p = partsAt(ms, tz);
  return Math.round((Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s) - Math.floor(ms / 1000) * 1000) / 60_000);
}

/** A typed `YYYY-MM-DD` + `HH:MM` in `tz` -> ISO instant with that zone's offset (`2026-11-03T14:00:00-03:00`). */
export function zonedIso(date: string, time: string, tz: string): string | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const tm = /^(\d{2}):(\d{2})$/.exec(time);
  if (!dm || !tm) return null;
  const wall = Date.UTC(+dm[1], +dm[2] - 1, +dm[3], +tm[1], +tm[2]);
  let off = offsetMinutes(wall, tz);
  const second = offsetMinutes(wall - off * 60_000, tz);
  if (second !== off) off = second;
  const sign = off < 0 ? '-' : '+';
  const abs = Math.abs(off);
  return `${date}T${time}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

/** Today (`YYYY-MM-DD`) in `tz`. */
export function todayIn(tz: string, now: number = Date.now()): string {
  return zonedParts(new Date(now).toISOString(), tz)!.date;
}

/** Calendar arithmetic on `YYYY-MM-DD` (zone-free). */
export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + days));
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`;
}

/** 0 = Monday ... 6 = Sunday of a `YYYY-MM-DD`. */
export function weekdayOf(date: string): number {
  const [y, m, d] = date.split('-').map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** The Monday of the week holding `date`. */
export function weekStartOf(date: string): string {
  return addDays(date, -weekdayOf(date));
}

export const WEEKDAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'] as const;
export const WEEKDAYS_SHORT = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'] as const;

/** `YYYY-MM-DD` -> `dd/mm/aaaa` (empty for nothing). */
export function formatDay(date: string | null | undefined): string {
  if (!date) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : date;
}

/** `YYYY-MM-DD` -> `dd/mm`. */
export function formatDayShort(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  return m ? `${m[3]}/${m[2]}` : date;
}

/** An instant as `qua, 05/11/2026 14:00` in `tz`. */
export function formatWhen(iso: string | null | undefined, tz: string): string {
  const p = zonedParts(iso, tz);
  return p ? `${WEEKDAYS_SHORT[p.weekday]}, ${formatDay(p.date)} ${p.time}` : '';
}

/** The configured option of `slug` (unknown -> a neutral stand-in showing the slug). */
export function optionOf<T extends ClientStatusConfig>(list: T[] | undefined, slug: string): ClientStatusConfig {
  return list?.find((s) => s.slug === slug) ?? { slug, label: slug, color: null };
}

export const PAYMENT_STATUS: Record<PaymentStatus, { label: string; color: string }> = {
  none: { label: 'Sem cobrança', color: 'muted' },
  open: { label: 'Em aberto', color: 'primary' },
  partial: { label: 'Pago em parte', color: 'warning' },
  paid: { label: 'Pago', color: 'success' },
  overdue: { label: 'Vencido', color: 'destructive' },
};

/** A session's payment status from its receivable (the same rule the server applies). */
export function paymentStatusOf(entry: ClientFinanceEntry | undefined): PaymentStatus {
  if (!entry || entry.status === 'cancelled') return 'none';
  if (entry.amount_cents > 0 && entry.settled_cents >= entry.amount_cents) return 'paid';
  if (entry.overdue) return 'overdue';
  return entry.settled_cents > 0 ? 'partial' : 'open';
}

/** The query string of a list request: empty filters are not sent. */
export function clientsFilterQuery(f: ClientFiltersState = {}): Record<string, string> {
  const out: Record<string, string> = {};
  if (f.q?.trim()) out.q = f.q.trim();
  if (f.status) out.status = f.status;
  if (f.tag) out.tag = f.tag;
  return out;
}

export function hasClientFilters(f: ClientFiltersState = {}): boolean {
  return Object.keys(clientsFilterQuery(f)).length > 0;
}

/** Lower-cased noun for the middle of a sentence ("Novo paciente"). */
export function nounLower(noun: string): string {
  return noun.charAt(0).toLowerCase() + noun.slice(1);
}

/** Only digits of a typed CPF / doc (null when empty). */
export function docDigits(text: string): string | null {
  const d = text.replace(/\D/g, '');
  return d || null;
}
