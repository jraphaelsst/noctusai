/** Opt-out detection on 422 `{detail, code:'perfil_optout'}` (ApiError.code, duck-typed). */
export const CODIGO_PERFIL_OPTOUT = "perfil_optout";
export const MSG_PERFIL_OPTOUT = "Este perfil pediu para não ser monitorado.";

export function ehPerfilOptout(e: unknown): boolean {
  if (!e || typeof e !== "object") return false;
  const x = e as { code?: unknown; body?: { code?: unknown } };
  return x.code === CODIGO_PERFIL_OPTOUT || x.body?.code === CODIGO_PERFIL_OPTOUT;
}

/** Mirrors the backend default (`settings.biblioteca_optout_contato`); used until a profile row
 * (which carries the live, configurable value) is available -- the list can be empty. */
export const CONTATO_OPTOUT_PADRAO = "joaoraphaelsst@gmail.com";

export function textoTransparencia(contato: string = CONTATO_OPTOUT_PADRAO): string {
  return `Somente perfis públicos de empresa/criador podem ser monitorados. Usamos as publicações apenas para estudar a estrutura do conteúdo, nunca para republicar. O criador pode pedir para não ser monitorado pelo e-mail ${contato}.`;
}
