/**
 * Shared utility functions used across all NoctusAI frontends.
 *
 * Product-specific utilities should remain in each product's own `lib/utils.ts`
 * and re-export these shared ones for backwards compatibility.
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// ---------------------------------------------------------------------------
// Tailwind class merge helper
// ---------------------------------------------------------------------------

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ---------------------------------------------------------------------------
// Currency formatting (BRL)
// ---------------------------------------------------------------------------

/**
 * Formats a number as Brazilian Real (R$).
 * Returns "R$ 0,00" when value is null/undefined.
 */
export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return 'R$ 0,00';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

/**
 * Formats a date string to Brazilian DD/MM/YYYY format.
 *
 * - DATE-only strings (`YYYY-MM-DD`) are interpreted as local dates (no
 *   timezone shift).
 * - Full ISO timestamps are parsed via the `Date` constructor.
 * - Optionally appends time in the format "as HH:mm".
 */
export function formatDate(dateString: string | null | undefined, includeTime: boolean = false): string {
  if (!dateString) return '-';

  let date: Date;

  const dateOnlyRegex = /^\d{4}-\d{2}-\d{2}$/;

  if (dateOnlyRegex.test(dateString)) {
    const [year, month, day] = dateString.split('-').map(Number);
    date = new Date(year, month - 1, day);
  } else {
    date = new Date(dateString);
  }

  if (isNaN(date.getTime())) return '-';

  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const yyyy = date.getFullYear();
  const formatted = `${dd}/${mm}/${yyyy}`;

  if (includeTime) {
    const hh = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    return `${formatted} \u00e0s ${hh}:${min}`;
  }

  return formatted;
}

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

/**
 * Returns today at midnight (local timezone), useful for date comparisons.
 */
export function getTodayAtMidnight(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/**
 * Strips the time portion from a Date, returning midnight.
 */
export function stripTime(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}
