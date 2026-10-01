/**
 * The backend's own pt-BR message for a failed request (contract §0 "Errors":
 * every user-visible message is the exact copy to ship), minus the transport's
 * `[409] ` status prefix. Falls back only when the error carries no message —
 * never replaces a message the operator can act on with a generic one.
 */
export function mensagemDoErro(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : "";
  const limpa = message.replace(/^\[\d+\]\s*/, "").trim();
  return limpa || fallback;
}
