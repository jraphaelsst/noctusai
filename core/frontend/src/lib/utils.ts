/**
 * Shared utility functions for the NoctusAI Core frontend.
 */
export { cn, formatDate, getTodayAtMidnight, stripTime } from '@noctusai/shared/utils';

// Core has its own formatCurrency that returns "Gratis" for 0/null
export function formatCurrency(value: number | null | undefined): string {
  if (value == null || value === 0) return 'Gratis';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}
