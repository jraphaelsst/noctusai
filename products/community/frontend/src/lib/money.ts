/**
 * Money helpers — `preco_centavos` (integer cents) ↔ pt-BR BRL display,
 * per community-m1-contract.md ("Money display: `preco_centavos / 100` as
 * `pt-BR` BRL currency. Input in reais, converted to cents before sending.").
 *
 * `@noctusai/lib`'s own `formatCurrency` IS the canonical pt-BR BRL
 * formatter (`seed/lib/frontend/src/utils.ts`) — consumed here rather than
 * re-implemented (it takes a value already in reais, hence `cents / 100`).
 * Only the cents↔reais conversions are community-local, since no seed
 * helper covers those yet.
 */
import { formatCurrency } from "@noctusai/lib";

/** `preco_centavos` (or any integer-cents amount) → formatted pt-BR BRL. */
export function formatBRLFromCents(cents: number): string {
  return formatCurrency(cents / 100);
}

/** Reais (as typed in a form input, e.g. `"99.90"`) → integer cents, rounded. */
export function reaisToCents(reais: number | string): number {
  const value = typeof reais === "string" ? Number(reais) : reais;
  if (!Number.isFinite(value)) return 0;
  return Math.round(value * 100);
}

/** Integer cents → reais (for pre-filling a number input on edit). */
export function centsToReais(cents: number): number {
  return cents / 100;
}
