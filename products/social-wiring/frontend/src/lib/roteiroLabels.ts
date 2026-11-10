/** Shared pt-BR labels for the roteiro lifecycle (editor + the card's Roteiros tab). */

/** `YYYY-MM-DD` → `dd/mm/aaaa` without a timezone round-trip (a DATE has no
 *  instant; `new Date("2026-10-01")` would render the 30th west of UTC). */
export function dataVisitaBR(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** "Salvo há N s" text for the autosave indicator (`agora` and `em` in ms). */
export function salvoHa(em: number, agora: number): string {
  const s = Math.max(0, Math.round((agora - em) / 1000));
  if (s < 60) return `Salvo há ${s} s`;
  const min = Math.floor(s / 60);
  return `Salvo há ${min} min`;
}
