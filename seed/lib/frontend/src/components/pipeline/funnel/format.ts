/** Funnel formatting — pt-BR, BRL; a missing value is "—", never 0 (canon §8). */
import { formatCurrency } from '../../../utils';
import type { FunnelCard } from './types';

const num = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;

/**
 * "R$ 18.000 + R$ 794/mês" when the card carries the split (`campos.valor_unico` /
 * `campos.valor_mensal`), else the single `valor`. `null` when there is no value at all.
 */
export function formatFunnelValue(card: Pick<FunnelCard, 'valor' | 'campos'>): string | null {
  const unico = num(card.campos?.valor_unico);
  const mensal = num(card.campos?.valor_mensal);
  if (unico !== null || mensal !== null) {
    return [
      unico !== null ? formatCurrency(unico) : null,
      mensal !== null ? `${formatCurrency(mensal)}/mês` : null,
    ]
      .filter(Boolean)
      .join(' + ');
  }
  const total = num(card.valor);
  return total !== null ? formatCurrency(total) : null;
}

export function initialsOf(nome: string): string {
  const parts = nome.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '—';
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '';
  return (first + last).toUpperCase();
}
