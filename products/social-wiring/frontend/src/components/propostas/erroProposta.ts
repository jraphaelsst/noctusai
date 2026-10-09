/**
 * Maps a failed proposta request to pt-BR copy + the field paths a 400
 * snapshot-validation error names (addendum): `{message, code, campos}`.
 */
import { mensagemErroServidor } from "@/lib/erroServidor";
import { PROPOSTA_ERRO_409 } from "@/types/propostas";

export interface ErroProposta {
  mensagem: string;
  code: string | null;
  campos: string[];
}

function textoDoCaminho(x: unknown): string | null {
  if (typeof x === "string") return x;
  if (Array.isArray(x)) return x.map(String).join(".");
  if (x && typeof x === "object") {
    const o = x as Record<string, unknown>;
    return textoDoCaminho(o.path ?? o.loc ?? o.campo ?? o.field);
  }
  return null;
}

export function lerErroProposta(err: unknown, fallback: string): ErroProposta {
  const envelope = (err as { body?: { error?: Record<string, unknown> } } | null)?.body?.error;
  const code = typeof envelope?.code === "string" ? envelope.code : null;
  const details = envelope?.details as unknown;
  const bruto: unknown[] = Array.isArray(details)
    ? details
    : details && typeof details === "object"
      ? [
          ...(((details as Record<string, unknown>).campos as unknown[]) ?? []),
          ...(((details as Record<string, unknown>).fields as unknown[]) ?? []),
          ...(((details as Record<string, unknown>).errors as unknown[]) ?? []),
        ]
      : [];
  const campos = bruto.map(textoDoCaminho).filter((c): c is string => !!c);
  const amigavel = code ? PROPOSTA_ERRO_409[code.toLowerCase()] : undefined;
  return { mensagem: amigavel ?? mensagemErroServidor(err, fallback), code, campos };
}

/** True when `campos` flags `caminho` itself or anything under it. */
export function campoInvalido(campos: readonly string[], caminho: string): boolean {
  return campos.some((c) => c === caminho || c.startsWith(`${caminho}.`) || c.startsWith(`${caminho}[`));
}
