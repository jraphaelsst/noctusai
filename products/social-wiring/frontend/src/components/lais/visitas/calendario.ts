/** Pure date helpers for the Visitas calendar (local time, ISO yyyy-mm-dd keys). */
export const pad = (n: number) => String(n).padStart(2, "0");
export const chaveData = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export function paraData(chave: string): Date {
  const [y, m, d] = chave.split("-").map(Number);
  return new Date(y, m - 1, d);
}
export function somarDias(chave: string, n: number): string {
  const d = paraData(chave);
  d.setDate(d.getDate() + n);
  return chaveData(d);
}
/** Monday of the week containing `chave`. */
export function inicioSemana(chave: string): string {
  const d = paraData(chave);
  return somarDias(chave, -((d.getDay() + 6) % 7));
}
export function diasDaJanela(view: "semana" | "dia", chave: string): string[] {
  if (view === "dia") return [chave];
  const ini = inicioSemana(chave);
  return Array.from({ length: 7 }, (_, i) => somarDias(ini, i));
}
export const hhmm = (iso: string) => {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
export const dataDe = (iso: string) => chaveData(new Date(iso));
/** datetime-local value <-> ISO */
export const paraInputLocal = (iso: string) => `${dataDe(iso)}T${hhmm(iso)}`;
export const deInputLocal = (v: string) => new Date(v).toISOString();
