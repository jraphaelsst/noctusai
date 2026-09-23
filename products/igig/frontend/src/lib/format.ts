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
