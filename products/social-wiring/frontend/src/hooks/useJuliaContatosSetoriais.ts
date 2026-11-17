/**
 * Julia › Contatos por setor (owner decision 2026-11-17): who Julia points a person who is NOT a lead to (vendor, partner,
 * legal desk, property owner). Org admin only (server-enforced).
 *
 *   GET /api/julia/contatos-setoriais → {data: {dono, contatos[], legado[], setores[], maximo, declarada}}
 *   PUT /api/julia/contatos-setoriais {contatos: [{setor, finalidade, nome, telefone}]} → the same body
 *
 * `dono` is the org owner's own number, READ-ONLY here: the server derives it from the owner's profile (core
 * `noctus_users.telefone`) at every request, so it is never typed or stored in this screen. Loading = two signals off
 * `data` (never `isLoading`). A refusal is mapped to a pt-BR sentence, never swallowed.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";

export interface ContatoSetorial {
  setor: string;
  finalidade: string;
  nome: string;
  telefone: string;
}

export interface ContatoDono extends ContatoSetorial {
  origem: "perfil";
}

export interface ContatosSetoriais {
  dono: ContatoDono | null;
  contatos: ContatoSetorial[];
  /** Items of an older, unstructured value: shown so nothing disappears silently; saving replaces them. */
  legado: string[];
  setores: string[];
  maximo: number;
  /** False = the platform has not declared the spec yet (saving would fail). */
  declarada: boolean;
}

export const ROTULO_SETOR: Record<string, string> = {
  administrativo: "Administrativo",
  juridico: "Jurídico",
  parcerias: "Parcerias",
  fornecedores: "Fornecedores",
  proprietarios: "Proprietários",
  outro: "Outro",
};

export const JULIA_CONTATOS_SETORIAIS_KEY = ["sw", "julia", "contatos-setoriais"] as const;
const URL = "/api/julia/contatos-setoriais";

/** pt-BR sentence per refusal code this card can provoke (the server's own sentence wins when it sends one). */
export function mensagemErroContatos(err: unknown, fallback: string): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  if (code === "edicao_restrita_plataforma") {
    return "Salvar os contatos por setor ainda não foi liberado pela NoctusAI. Nada foi alterado. Fale com o suporte.";
  }
  return mensagemErroJulia(err, fallback);
}

export function useJuliaContatosSetoriais() {
  return useQuery({
    queryKey: JULIA_CONTATOS_SETORIAIS_KEY,
    queryFn: async () => (await api.get<{ data: ContatosSetoriais }>(URL)).data,
    // A typed 4xx (not connected, not an admin) will not fix itself on a retry.
    retry: (n, err) => {
      const s = (err as { status?: unknown } | null)?.status;
      return (typeof s !== "number" || s >= 500) && n < 2;
    },
  });
}

/** The answer carries the whole saved state (owner entry included): it replaces the cached read. */
export function useSalvarContatosSetoriais() {
  const qc = useQueryClient();
  return useMutation<ContatosSetoriais, unknown, ContatoSetorial[]>({
    mutationFn: async (contatos) => (await api.put<{ data: ContatosSetoriais }>(URL, { contatos })).data,
    onSuccess: (saved) => qc.setQueryData(JULIA_CONTATOS_SETORIAIS_KEY, saved),
  });
}
