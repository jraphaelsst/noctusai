/**
 * Lais › Perguntas essenciais (contract wave 2).
 *
 *   GET /api/lais/perguntas                          org member: catalogue + limits
 *   PUT /api/lais/perguntas  {selecao:[{chave,qualificatoria}]}   admin: full replace
 *   GET /api/lais/contatos/{connection_id}/{chat_id} per-chat slots (Conversas panel)
 *
 * Envelope `{data: …}`; typed refusals map to their own pt-BR sentence.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export interface LaisPergunta {
  chave: string;
  label: string;
  dica: string | null;
  categoria: string;
  operacao: "compra" | "aluguel" | null;
  ativa: boolean;
  qualificatoria: boolean;
  bloqueada: boolean;
  usada_em_criterio: boolean;
}

export interface LaisPerguntas {
  catalogo: LaisPergunta[];
  limites: { max_ativas: number; max_qualificatorias: number };
}

export interface LaisSelecaoItem {
  chave: string;
  qualificatoria: boolean;
}

export interface LaisContatoLead {
  contato: { operacao?: string | null; [k: string]: unknown } | null;
  slots: Record<string, string | number | null> | null;
  interacao_atual: { operacao?: string | null; [k: string]: unknown } | null;
}

export const LAIS_PERGUNTAS_KEY = ["sw", "lais", "perguntas"] as const;
export const laisContatoKey = (connectionId: string | null, chatId: string | null) =>
  ["sw", "lais", "contato", connectionId, chatId] as const;

export function useLaisPerguntas() {
  return useQuery({
    queryKey: LAIS_PERGUNTAS_KEY,
    queryFn: async () => (await api.get<{ data: LaisPerguntas }>("/api/lais/perguntas")).data,
  });
}

export function useSalvarPerguntas() {
  const qc = useQueryClient();
  return useMutation<{ data: LaisPerguntas }, unknown, LaisSelecaoItem[]>({
    mutationFn: (selecao) => api.put<{ data: LaisPerguntas }>("/api/lais/perguntas", { selecao }),
    onSuccess: (res) => qc.setQueryData(LAIS_PERGUNTAS_KEY, res.data),
  });
}

/** Slots of one chat. Keeps the previous chat's data while the next loads. */
export function useLaisContato(connectionId: string | null, chatId: string | null) {
  return useQuery({
    queryKey: laisContatoKey(connectionId, chatId),
    enabled: !!connectionId && !!chatId,
    retry: false,
    queryFn: async () =>
      (
        await api.get<{ data: LaisContatoLead }>(
          `/api/lais/contatos/${encodeURIComponent(connectionId as string)}/${encodeURIComponent(chatId as string)}`,
        )
      ).data,
    placeholderData: (prev) => prev,
  });
}

interface ErroLais {
  body?: { error?: { code?: unknown; details?: { criterios?: unknown } } };
}

const MENSAGENS: Record<string, string> = {
  limite_ativas: "Você atingiu o limite de perguntas adicionadas.",
  limite_qualificatorias: "Você atingiu o limite de perguntas qualificatórias.",
  objetivo_obrigatorio: "Esta pergunta é essencial para a identificação da operação correta.",
  chave_desconhecida: "Uma das perguntas selecionadas não existe mais. Recarregue a página.",
};

export function mensagemErroPerguntas(err: unknown, fallback: string): string {
  const e = (err as ErroLais | null)?.body?.error;
  const code = typeof e?.code === "string" ? e.code : null;
  if (code === "usada_em_criterio") {
    const lista = Array.isArray(e?.details?.criterios) ? (e?.details?.criterios as unknown[]).map(String) : [];
    const base = "Para desativar esta pergunta, primeiro desative os critérios de envio que a usam.";
    return lista.length ? `${base} (${lista.join(", ")})` : base;
  }
  if (code && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, fallback);
}
