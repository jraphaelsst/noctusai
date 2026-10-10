/**
 * Instagram handle normalization for "Solicitar Perfil" (contract §4.3 #11):
 * strip, URL -> handle, reserved path segments rejected, and the server regex
 * `^@?[a-zA-Z0-9._]{1,30}$`. Pure, so the live check and the submit agree.
 */
const RESERVADOS = new Set([
  "p", "reel", "reels", "tv", "explore", "stories", "accounts", "direct", "about",
  "tags", "locations", "web", "legal", "developer", "directory",
]);
const VALIDO = /^[a-zA-Z0-9._]{1,30}$/;

export type HandleNormalizado =
  | { ok: true; handle: string }
  | { ok: false; erro: string };

export function normalizarHandle(bruto: string): HandleNormalizado {
  let s = bruto.trim();
  if (!s) return { ok: false, erro: "Informe o perfil do Instagram." };

  if (/^(https?:\/\/)?(www\.)?instagram\.com\//i.test(s)) {
    const caminho = s
      .replace(/^(https?:\/\/)?(www\.)?instagram\.com\//i, "")
      .split(/[/?#]/)[0];
    s = caminho ?? "";
  }
  s = s.replace(/^@+/, "");

  if (RESERVADOS.has(s.toLowerCase())) {
    return { ok: false, erro: "Informe o perfil, não o link de um post." };
  }
  if (!VALIDO.test(s)) {
    return { ok: false, erro: "Perfil inválido. Use letras, números, ponto ou sublinhado (até 30)." };
  }
  return { ok: true, handle: s.toLowerCase() };
}
