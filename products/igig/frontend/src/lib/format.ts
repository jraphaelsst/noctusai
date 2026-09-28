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

/**
 * Parse a money amount typed in pt-BR OR plain-decimal form. `null` on
 * anything unparseable — NEVER `0`, so a caller can show an inline error
 * instead of silently submitting a free line (finding #5, 2026-09 audit:
 * `Number(valor.replace(",", "."))` turned "1.500,00" into `NaN` → `0`).
 *
 * Accepts:
 *   "1500,00"   → 1500     (comma = decimal, the pt-BR convention)
 *   "1.500,00"  → 1500     (dot = thousands separator, comma = decimal)
 *   "1500.00"   → 1500     (no comma at all ⇒ read as a plain decimal,
 *                            the shape a numeric mobile keypad's "." produces)
 *   "1500"      → 1500
 *   ""          → null
 *   "abc"       → null
 */
export function parseValorBR(texto: string): number | null {
  const limpo = texto.trim();
  if (!limpo) return null;
  const normalizado = limpo.includes(",")
    ? limpo.replace(/\./g, "").replace(",", ".")
    : limpo;
  if (!/^-?\d+(\.\d+)?$/.test(normalizado)) return null;
  const numero = Number(normalizado);
  return Number.isFinite(numero) ? numero : null;
}
