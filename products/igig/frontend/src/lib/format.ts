/** pt-BR formatters shared by the CRM screens. */
const BRL_FMT = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function brl(valor: number | null | undefined): string {
  return BRL_FMT.format(Number(valor ?? 0));
}

/** `2026-09-23` / ISO datetime → `23/09/2026`. Empty for null. */
export function dataBR(iso: string | null | undefined): string {
  if (!iso) return "";
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  if (!ano || !mes || !dia) return iso;
  return `${dia}/${mes}/${ano}`;
}

/** Percentage with one decimal, pt-BR comma. */
export function pct(valor: number | null | undefined): string {
  return `${Number(valor ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

/** A plain ratio/ count, pt-BR comma, fixed decimal places (e.g. taxa de
 * refação) — `.toFixed()` always renders an American decimal POINT, which
 * `l.margem_percentual.toFixed(1)`/`linha.taxa_refacao.toFixed(2)` did
 * fleet-wide until this (tech-lead addendum, 2026-09). */
export function numeroBR(valor: number | null | undefined, casas = 2): string {
  return Number(valor ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

/** `1.5` → "1,5 h"; `12` → "12 h" — the BI table's raw `horas` number used
 * to render bare (an American decimal point, no unit). */
export function horasBR(valor: number | null | undefined): string {
  return `${Number(valor ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} h`;
}

/**
 * Parse a money amount typed in pt-BR OR plain-decimal form. `null` on
 * anything unparseable — NEVER `0`, so a caller can show an inline error
 * instead of silently submitting a free line (finding #5, 2026-09 audit:
 * `Number(valor.replace(",", "."))` turned "1.500,00" into `NaN` → `0`).
 *
 * Accepts:
 *   "1500,00"   → 1500     (comma = decimal, the pt-BR convention)
 *   "1.500,00"  → 1500     (dot = thousands separator, comma = decimal)
 *   "1.500"     → 1500     (no comma; a dot followed by exactly 3-digit
 *                            groups is the pt-BR THOUSANDS separator, not a
 *                            decimal point — `Number("1.500")` alone reads
 *                            1.5, which is how this used to silently
 *                            undercharge a R$ 1.500,00 item as R$ 1,50)
 *   "1500.00"   → 1500     (no comma, dot followed by 1-2 digits ⇒ a plain
 *                            decimal, the shape a numeric mobile keypad's
 *                            "." produces)
 *   "1500"      → 1500
 *   ""          → null
 *   "abc"       → null
 */
export function parseValorBR(texto: string): number | null {
  const limpo = texto.trim();
  if (!limpo) return null;
  let normalizado: string;
  if (limpo.includes(",")) {
    normalizado = limpo.replace(/\./g, "").replace(",", ".");
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) {
    // No comma, and every dot-separated group past the first is exactly
    // 3 digits ⇒ this IS the pt-BR thousands separator ("1.500" ⇒ 1500),
    // never a decimal point.
    normalizado = limpo.replace(/\./g, "");
  } else {
    normalizado = limpo;
  }
  if (!/^-?\d+(\.\d+)?$/.test(normalizado)) return null;
  const numero = Number(normalizado);
  return Number.isFinite(numero) ? numero : null;
}
