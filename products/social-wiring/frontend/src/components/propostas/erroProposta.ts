/**
 * Maps a failed proposta request to pt-BR copy + the field paths a 400
 * `snapshot_invalido` names. Read through the seed `ApiError`
 * (`err.code`, `err.details`): the backend emits the seed envelope
 * `{error: {code, message, details: {campos: [{path, mensagem}]}}}`.
 * The server's pt-BR `message` wins; the code→copy map is only a fallback.
 */
import { ApiError } from "@noctusai/lib";

import { mensagemErroServidor } from "@/lib/erroServidor";
import { PROPOSTA_ERRO_409 } from "@/types/propostas";

export interface ErroProposta {
  mensagem: string;
  code: string | null;
  campos: string[];
}

export function lerErroProposta(err: unknown, fallback: string): ErroProposta {
  const api = err instanceof ApiError ? err : null;
  const code = api?.code ?? null;
  const details = api?.details as { campos?: { path?: unknown }[] } | null | undefined;
  const campos = (Array.isArray(details?.campos) ? details.campos : [])
    .map((c) => c?.path)
    .filter((p): p is string => typeof p === "string" && !!p);
  // `ApiError.message` carries a `[status] ` prefix: read the envelope's own text.
  const envelope = (api?.body as { error?: { message?: unknown } } | undefined)?.error?.message;
  const doServidor =
    typeof envelope === "string" && envelope
      ? envelope
      : mensagemErroServidor(err, "").replace(/^\[\d+\]\s*/, "").trim();
  const mensagem =
    doServidor || (code ? PROPOSTA_ERRO_409[code.toLowerCase()] : undefined) || fallback;
  // FastAPI 422 (`{detail: [{loc, msg}]}`, malformed types / unknown keys /
  // out-of-range values): highlight by `loc` (minus the leading "body").
  const bruto = (api?.body as { detail?: unknown } | undefined)?.detail;
  const lista422 = api?.status === 422 && Array.isArray(bruto) ? (bruto as { loc?: unknown }[]) : [];
  const campos422 = lista422
    .map((d) => (Array.isArray(d?.loc) ? d.loc.map(String).filter((x) => x !== "body").join(".") : ""))
    .filter(Boolean);
  if (lista422.length > 0) {
    return {
      mensagem: "Alguns campos da proposta estão inválidos. Confira os destacados.",
      code: code ?? "validacao_422",
      campos: campos422,
    };
  }
  return { mensagem, code, campos };
}

/** True when `campos` flags `caminho` itself or anything under it. */
export function campoInvalido(campos: readonly string[], caminho: string): boolean {
  return campos.some((c) => c === caminho || c.startsWith(`${caminho}.`) || c.startsWith(`${caminho}[`));
}
