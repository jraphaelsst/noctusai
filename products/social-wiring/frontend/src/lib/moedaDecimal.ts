/**
 * Decimal-STRING money + ISO-date display helpers — the negociação's
 * "every money value stays a string, end to end" rule
 * (`@/types/negociacaoEstruturada`): `Decimal` on the wire, never
 * `Number()`'d except to FORMAT a value for reading (never composed into a
 * new stored amount).
 *
 * Shared by the negociação estruturada panel and the contract aditivo editor
 * (both edit the same parcela shape through `ParcelaFormDialog`), so the two
 * can never read "850.000,00" differently.
 */

/** Formats for READING (pt-BR currency); the value itself is untouched. */
export function exibirMoeda(v: string | null | undefined): string {
  if (v == null || v.trim() === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Bare number for an EDITABLE field, no currency symbol: `850000` → `850.000,00`. */
export function formatarValorEditavel(v: string): string {
  const n = Number(v);
  if (v.trim() === "" || !Number.isFinite(n)) return v;
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Reads what a Brazilian actually types: `850.000,00`, `850000,00`, `850000`. */
export function lerValorDigitado(entrada: string): string {
  const limpo = entrada.replace(/[^\d.,-]/g, "");
  if (limpo.includes(",")) return limpo.replace(/\./g, "").replace(",", ".");
  if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) return limpo.replace(/\./g, "");
  return limpo;
}

/** `YYYY-MM-DD` → `DD/MM/YYYY`; anything else is returned as-is. */
export function exibirData(v: string | null | undefined): string | null {
  if (!v) return null;
  const [ano, mes, dia] = v.split("-");
  if (!ano || !mes || !dia) return v;
  return `${dia}/${mes}/${ano}`;
}
