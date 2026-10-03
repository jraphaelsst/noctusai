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

export function mensagemErroServidor(err: unknown, fallback: string): string {
  // Duck-typed on the seed `ApiError`'s `body` (no `instanceof`): the same
  // envelope read whichever module instance built the error.
  const envelope = (err as { body?: { error?: { message?: unknown } } } | null | undefined)?.body;
  const proprio = (err as { message?: unknown } | null | undefined)?.message;
  const doEnvelope = envelope?.error?.message;
  if (typeof doEnvelope === "string" && doEnvelope) return doEnvelope;
  return typeof proprio === "string" && proprio ? proprio : fallback;
}

export function toastServerError(err: unknown, fallback: string): void {
  toast.error(mensagemErroServidor(err, fallback));
}
