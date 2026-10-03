/**
 * The pt-BR sentence to show for a failed request.
 *
 * A typed server refusal (`{error: {code, message}}` — an `AppException`,
 * e.g. migration 157's 409 `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO`)
 * carries its own sentence; `ApiError.message` would prefix it with the
 * status. Anything else falls back to the error's own message, then to the
 * caller's `fallback` — never a silent nothing.
 */
import { toast } from "sonner";
import { ApiError } from "@noctusai/lib";

export function mensagemErroServidor(err: unknown, fallback: string): string {
  const envelope =
    err instanceof ApiError ? (err.body as { error?: { message?: string } } | undefined) : undefined;
  const proprio = (err as { message?: unknown } | null | undefined)?.message;
  return envelope?.error?.message || (typeof proprio === "string" && proprio ? proprio : fallback);
}

export function toastServerError(err: unknown, fallback: string): void {
  toast.error(mensagemErroServidor(err, fallback));
}
