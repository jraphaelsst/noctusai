/**
 * Public signup hook — ninho-vazio CONTRACT.md §Identity, `POST /api/cadastro`.
 *
 * PUBLIC (no session) — the shared `api` client sends unauthenticated
 * requests when there is no token, the same mechanism `useCheckout` relies
 * on. Every error (400 terms, 403 Turnstile, 409 existing e-mail / no free
 * plan, 429) carries the backend's own pt-BR `detail`; the page renders it
 * verbatim through `errorMessage`.
 */
import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface CadastroInput {
  nome: string;
  email: string;
  telefone: string | null;
  senha: string;
  turnstile_token: string;
  aceite_termos: boolean;
}

export interface CadastroResponse {
  membro_id: string;
  email: string;
  proximo_passo: "entrar";
}

/** Same shape the backend enforces on `membros.telefone` (`_PHONE_RE`). */
export const TELEFONE_RE = /^\+[1-9]\d{7,14}$/;
export const SENHA_MIN = 8;
export const SENHA_MAX = 72;

export function useCadastro() {
  return useMutation({
    mutationFn: (data: CadastroInput) => api.post<CadastroResponse>("/api/cadastro", data),
  });
}
