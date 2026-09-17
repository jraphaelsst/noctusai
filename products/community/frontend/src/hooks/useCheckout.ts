/**
 * Public checkout hook — community-m2-contract.md §Endpoints#Checkout,
 * amendments A1-A5/A10-A11, product decisions P1/P2.
 *
 * `POST /api/checkout` is PUBLIC (no session) — the shared `api` client
 * already sends unauthenticated requests when `getAuthToken()` resolves
 * `null` (`seed/lib/frontend/src/api.ts`), the same mechanism
 * `useSubmitAplicacao` (`/inscrever`, module 1) relies on.
 *
 * Amendment A2 — **the response never reveals whether the e-mail is a
 * member**: a `checkout_url: null` + `status: "verifique_seu_email"` body is
 * a NORMAL, friendly outcome (an already-active e-mail, or any other
 * out-of-band case), never surfaced as an error. `pages/Assinar.tsx` must
 * branch on `checkout_url === null` before touching `pix_qr`, not on any
 * error path.
 *
 * Product decision P1 — CPF is collected here, sent straight through as
 * `cpf`, and NEVER written to any of our own rows/logs (server-side
 * guarantee) — the FE's only obligations are: required for pix/boleto,
 * absent (not just empty) for cartao, digits-only, and never persisted
 * (no localStorage, no query string, never logged to the console).
 */
import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type CheckoutMetodo = "cartao" | "pix" | "boleto";

export interface PixQr {
  payload: string;
  imagem_base64: string;
  expira_em: string;
}

export interface CheckoutInput {
  plano_id: string;
  metodo: CheckoutMetodo;
  nome: string;
  email: string;
  telefone: string;
  /** Required for pix/boleto, must be OMITTED (not `""`) for cartao — P1. */
  cpf?: string;
  turnstile_token: string;
}

export interface CheckoutResponse {
  checkout_url: string | null;
  assinatura_id: string;
  membro_id: string;
  pix_qr: PixQr | null;
  /** Present only on the A2 "already a member" friendly outcome. */
  status?: "verifique_seu_email";
}

/** Strips punctuation, keeps digits only — P1 ("digits-only after stripping punctuation"). */
export function stripCpfPunctuation(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** A CPF is exactly 11 digits once stripped. Client-side shape check only —
 * the backend is the source of truth for validity beyond length. */
export function isValidCpfLength(raw: string): boolean {
  return stripCpfPunctuation(raw).length === 11;
}

/** POST /api/checkout — public, rate-limited server-side. */
export function useCheckout() {
  return useMutation({
    mutationFn: (data: CheckoutInput) => api.post<CheckoutResponse>("/api/checkout", data),
  });
}
