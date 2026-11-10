/**
 * The pt-BR sentence to show for a failed request.
 *
 * A typed server refusal (`{error: {code, message}}` — an `AppException`,
 * e.g. migration 157's 409 `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO`)
 * (or `{detail: {code, message}}`) carries its own sentence; `ApiError.message` would prefix it with the
 * status. Anything else falls back to the error's own message, then to the
 * caller's `fallback` — never a silent nothing.
 */
import { toast } from "sonner";

export function mensagemErroServidor(err: unknown, fallback: string): string {
  // Duck-typed on the seed `ApiError`'s `body` (no `instanceof`): the same
  // envelope read whichever module instance built the error.
  const envelope = (
    err as
      | { body?: { error?: { message?: unknown }; detail?: { message?: unknown } | unknown } }
      | null
      | undefined
  )?.body;
  const proprio = (err as { message?: unknown } | null | undefined)?.message;
  const doEnvelope = envelope?.error?.message;
  if (typeof doEnvelope === "string" && doEnvelope) return doEnvelope;
  // `{detail: {code, message}}` — the shape the roteiro lifecycle routes answer
  // with (roteiro-ciclo CONTRACT §3); `message` is ready-to-show pt-BR.
  const detalhe = envelope?.detail;
  const doDetalhe =
    detalhe && typeof detalhe === "object" ? (detalhe as { message?: unknown }).message : undefined;
  if (typeof doDetalhe === "string" && doDetalhe) return doDetalhe;
  return typeof proprio === "string" && proprio ? proprio : fallback;
}

export function toastServerError(err: unknown, fallback: string): void {
  toast.error(mensagemErroServidor(err, fallback));
}
