/**
 * Local-time date helpers.
 *
 * The backend stores instants as UTC ISO strings (`2026-06-01T23:30:00Z`).
 * The UI must show / group / edit them in the USER's wall-clock time (BRT).
 * Slicing the ISO string (`iso.slice(0, 16)` / `iso.slice(0, 10)`) reads the
 * UTC wall clock — a 20:30 BRT event lands on the next day and re-saves
 * 3 hours later every time it is edited.
 */
import { format } from "date-fns";

/** UTC ISO instant -> `YYYY-MM-DDTHH:mm` in LOCAL time (for `datetime-local`). */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return format(d, "yyyy-MM-dd'T'HH:mm");
}

/** `datetime-local` value (local wall clock) -> UTC ISO instant. */
export function fromLocalInput(local: string): string {
  return new Date(local).toISOString();
}

/** UTC ISO instant -> `YYYY-MM-DD` of the LOCAL calendar day. */
export function localDayKey(iso: string): string {
  return format(new Date(iso), "yyyy-MM-dd");
}
