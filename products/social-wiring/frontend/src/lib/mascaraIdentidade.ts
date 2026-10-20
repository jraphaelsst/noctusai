/**
 * Defence in depth for the hand-off note (julia-v2 0.4): agents already sends the identity MASKED and SW renders only
 * that, but a raw CPF/RG must never reach the screen even if an upstream build regresses. Anything CPF-shaped (11
 * digits, dotted or not) is reduced to its last two digits; the value after an `rg`/`cpf` label is masked unless it
 * already carries a mask. Pure + idempotent (already-masked text is returned unchanged).
 */
const CPF = /(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)/g;
// "rg: 12.345.678-9" / "RG 1234567" — a label followed by a value that is mostly digits and has no mask char.
const ROTULADO = /\b(rg|cpf)(\s*[:=]?\s*)([0-9][0-9.\-\sxX]{3,}[0-9xX])/gi;

const SO_FIM = (v: string) => {
  const digitos = v.replace(/\D/g, "");
  return `${"*".repeat(Math.max(digitos.length - 2, 0))}${digitos.slice(-2)}`;
};

export function mascararIdentidade(texto: string): string {
  return texto
    .replace(ROTULADO, (_m, rot: string, sep: string, valor: string) => `${rot}${sep}${SO_FIM(valor)}`)
    .replace(CPF, (_m, _a, _b, _c, d: string) => `***.***.***-${d}`);
}

const ENTIDADES: Record<string, string> = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&#39;": "'" };
/** The backend html-escapes the note; React escapes again, so undo the entities for display (text only, never HTML). */
export const desescaparEntidades = (t: string) => t.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, (e) => ENTIDADES[e] ?? e);
