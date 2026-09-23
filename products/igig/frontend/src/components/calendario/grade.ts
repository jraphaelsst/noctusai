/**
 * Month-grid arithmetic for the editorial calendar (smoke finding 6: the old
 * grid had no weekday headers and started every month on the first column,
 * so "dia 1" sat under whatever weekday the eye assumed).
 *
 * Weeks start on MONDAY — the same order the product uses everywhere else a
 * weekday appears (the orçamento item's weekday toggles S T Q Q S S D and its
 * `dias_semana` bitmask, seg=1 … dom=64). One convention per product.
 *
 * Pure functions, no React: the offset rule is the thing that was wrong, so it
 * is the thing under test (`grade.test.ts`).
 */

/** Column headers, Monday first. */
export const DIAS_SEMANA_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"] as const;

/**
 * How many empty cells precede day 1 in a Monday-first grid.
 * `Date#getDay()` is Sunday=0 … Saturday=6; Monday-first shifts it by one.
 */
export function deslocamentoInicial(ano: number, mes: number): number {
  return (new Date(ano, mes, 1).getDay() + 6) % 7;
}

export function diasNoMes(ano: number, mes: number): number {
  return new Date(ano, mes + 1, 0).getDate();
}

/**
 * The cells of a month grid: `null` for leading/trailing padding, otherwise
 * the day number. Always a whole number of weeks (length % 7 === 0), so the
 * last row never renders ragged.
 */
export function celulasDoMes(ano: number, mes: number): (number | null)[] {
  const antes = deslocamentoInicial(ano, mes);
  const dias = diasNoMes(ano, mes);
  const celulas: (number | null)[] = [
    ...Array.from({ length: antes }, () => null),
    ...Array.from({ length: dias }, (_, i) => i + 1),
  ];
  while (celulas.length % 7 !== 0) celulas.push(null);
  return celulas;
}

/** `YYYY-MM-DD` in LOCAL time — `toISOString()` would shift the day in UTC−3. */
export function isoLocal(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}
