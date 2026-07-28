/**
 * BRL formatter for the pipeline boards.
 *
 * NOT `lib/formatCurrency.ts`'s `formatCents` — that one takes an integer
 * number of CENTS, while `valor_estimado` / `valor` are `NUMERIC(12,2)` in
 * reais. Scaling one into the other would be a lossy conversion in both
 * directions, so the boards format their own values directly.
 */
export function formatValor(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value || 0));
}
