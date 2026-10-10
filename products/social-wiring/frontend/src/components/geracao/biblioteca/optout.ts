/** Opt-out detection on 422 `{detail, code:'perfil_optout'}` (ApiError.code, duck-typed). */
export const CODIGO_PERFIL_OPTOUT = "perfil_optout";
export const MSG_PERFIL_OPTOUT = "Este perfil pediu para não ser monitorado.";

export function ehPerfilOptout(e: unknown): boolean {
  if (!e || typeof e !== "object") return false;
  const x = e as { code?: unknown; body?: { code?: unknown } };
  return x.code === CODIGO_PERFIL_OPTOUT || x.body?.code === CODIGO_PERFIL_OPTOUT;
}

export const TEXTO_TRANSPARENCIA =
  "Somente perfis públicos de empresa/criador podem ser monitorados. Usamos as publicações apenas para estudar a estrutura do conteúdo, nunca para republicar. O criador pode pedir para não ser monitorado pelo contato indicado na Política de Privacidade.";
