/**
 * Client-side mirror of the server's host allowlist for "Adicionar por link" (contract §4.2): only
 * `https://(www.)?instagram.com/(p|reel|reels|tv)/<shortcode>/…` is accepted. The server is the authority
 * (`link_invalido`); this only spares a round trip and explains the shape.
 */
const POST_IG = /^https:\/\/(?:www\.)?instagram\.com\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)(?:[/?#].*)?$/;

export type LinkNormalizado = { ok: true; url: string; shortcode: string } | { ok: false; erro: string };

export function normalizarLinkInstagram(bruto: string): LinkNormalizado {
  const s = bruto.trim();
  if (!s) return { ok: false, erro: "Cole o link de um post do Instagram." };
  const comEsquema = /^https?:\/\//i.test(s) ? s.replace(/^http:\/\//i, "https://") : `https://${s}`;
  const m = POST_IG.exec(comEsquema);
  if (!m) {
    return { ok: false, erro: "Cole o link de um post do Instagram (instagram.com/p/…, /reel/… ou /tv/…)." };
  }
  return { ok: true, url: comEsquema, shortcode: m[1] as string };
}
