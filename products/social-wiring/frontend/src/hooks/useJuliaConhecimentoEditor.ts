/**
 * Julia › Conhecimento as an editor of three agents org specs (Lais study S8, owner decision 2026-11-17):
 * `conhecimento_venda`, `conhecimento_locacao`, `conhecimento_politicas` (long text, at most `max_chars` each).
 *
 *   GET /api/julia/conhecimento-editor → {data: {itens[{chave, rotulo, valor, declarada, updated_at, updated_by_nome, sugestao}], max_chars}}
 *   PUT /api/julia/conhecimento-editor {valores: {chave: texto}} → the same body   (org admin; owner 2026-11-18: org-owned data)
 *
 * `sugestao` = what the old knowledge form held for that key (never written until the person saves). Loading = two signals
 * off `data` (never `isLoading`); a refusal is a pt-BR sentence, never silent.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import { JULIA_ESPECIFICACOES_KEY } from "@/hooks/useJuliaEspecificacoes";

export type ChaveConhecimento = "conhecimento_venda" | "conhecimento_locacao" | "conhecimento_politicas";

export interface ItemConhecimento {
  chave: ChaveConhecimento;
  rotulo: string;
  valor: string;
  declarada: boolean;
  updated_at: string | null;
  updated_by_nome: string | null;
  sugestao: string | null;
}

export interface ConhecimentoEditor {
  itens: ItemConhecimento[];
  max_chars: number;
}

export const JULIA_CONHECIMENTO_EDITOR_KEY = ["sw", "julia", "conhecimento-editor"] as const;
const URL = "/api/julia/conhecimento-editor";

export function mensagemErroConhecimento(err: unknown, fallback: string): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return mensagemErroJulia(err, fallback);
}

export function useJuliaConhecimentoEditor() {
  return useQuery({
    queryKey: JULIA_CONHECIMENTO_EDITOR_KEY,
    queryFn: async () => (await api.get<{ data: ConhecimentoEditor }>(URL)).data,
    retry: (n, err) => {
      const s = (err as { status?: unknown } | null)?.status;
      return (typeof s !== "number" || s >= 500) && n < 2;
    },
  });
}

/** The answer carries every key's saved state: it replaces the cached read; the generic specs read is refreshed. */
export function useSalvarConhecimento() {
  return useCacheWriteMutation<ConhecimentoEditor, Partial<Record<ChaveConhecimento, string>>>({
    mutationFn: async (valores) => (await api.put<{ data: ConhecimentoEditor }>(URL, { valores })).data,
    targets: [
      { queryKey: JULIA_CONHECIMENTO_EDITOR_KEY, commit: (_old: ConhecimentoEditor | undefined, saved) => saved },
      { queryKey: JULIA_ESPECIFICACOES_KEY },
    ],
  });
}
