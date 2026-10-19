/**
 * Julia › Perguntas essenciais (contract wave 2).
 *
 *   GET /api/julia/perguntas                          org member: catalogue + limits
 *   PUT /api/julia/perguntas  {selecao:[{chave,qualificatoria}]}   admin: full replace
 *   GET /api/julia/contatos/{connection_id}/{chat_id} per-chat slots (Conversas panel)
 *
 * Envelope `{data: …}`; typed refusals map to their own pt-BR sentence.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export interface JuliaPergunta {
  chave: string;
  label: string;
  categoria: string;
  operacao: "compra" | "aluguel" | null;
  ativa: boolean;
  qualificatoria: boolean;
  bloqueada: boolean;
  usada_em_criterio: boolean;
}

export interface JuliaPerguntas {
  catalogo: JuliaPergunta[];
  limites: { max_ativas: number; max_qualificatorias: number };
}

export interface JuliaSelecaoItem {
  chave: string;
  qualificatoria: boolean;
}

export interface JuliaContatoLead {
  contato: { operacao?: string | null; [k: string]: unknown } | null;
  slots: Record<string, string | number | null> | null;
  interacao_atual: { operacao?: string | null; [k: string]: unknown } | null;
}

export const JULIA_PERGUNTAS_KEY = ["sw", "julia", "perguntas"] as const;
export const juliaContatoKey = (connectionId: string | null, chatId: string | null) =>
  ["sw", "julia", "contato", connectionId, chatId] as const;

export function useJuliaPerguntas() {
  return useQuery({
    queryKey: JULIA_PERGUNTAS_KEY,
    queryFn: async () => (await api.get<{ data: JuliaPerguntas }>("/api/julia/perguntas")).data,
  });
}

export function useSalvarPerguntas() {
  const qc = useQueryClient();
  return useMutation<{ data: JuliaPerguntas }, unknown, JuliaSelecaoItem[]>({
    mutationFn: (selecao) => api.put<{ data: JuliaPerguntas }>("/api/julia/perguntas", { selecao }),
    onSuccess: (res) => qc.setQueryData(JULIA_PERGUNTAS_KEY, res.data),
  });
}

/** Slots of one chat. Keeps the previous chat's data while the next loads. */
export function useJuliaContato(connectionId: string | null, chatId: string | null) {
  return useQuery({
    queryKey: juliaContatoKey(connectionId, chatId),
    enabled: !!connectionId && !!chatId,
    retry: false,
    queryFn: async () =>
      (
        await api.get<{ data: JuliaContatoLead }>(
          `/api/julia/contatos/${encodeURIComponent(connectionId as string)}/${encodeURIComponent(chatId as string)}`,
        )
      ).data,
    placeholderData: (prev) => prev,
  });
}

interface ErroJulia {
  body?: { error?: { code?: unknown; details?: { criterios?: unknown } } };
}

const MENSAGENS: Record<string, string> = {
  limite_ativas: "Você atingiu o limite de perguntas adicionadas.",
  limite_qualificatorias: "Você atingiu o limite de perguntas qualificatórias.",
  objetivo_obrigatorio: "Esta pergunta é essencial para a identificação da operação correta.",
  chave_desconhecida: "Uma das perguntas selecionadas não existe mais. Recarregue a página.",
};

export function mensagemErroPerguntas(err: unknown, fallback: string): string {
  const e = (err as ErroJulia | null)?.body?.error;
  const code = typeof e?.code === "string" ? e.code : null;
  if (code === "usada_em_criterio") {
    const lista = Array.isArray(e?.details?.criterios) ? (e?.details?.criterios as unknown[]).map(String) : [];
    const base = "Para desativar esta pergunta, primeiro desative os critérios de envio que a usam.";
    return lista.length ? `${base} (${lista.join(", ")})` : base;
  }
  if (code && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, fallback);
}
