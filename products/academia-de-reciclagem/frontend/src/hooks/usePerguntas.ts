/**
 * Open-questions data hooks — contract §A.3, §B.3.
 */
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";
import type { Envelope } from "@/lib/types";

export type PerguntaEstado = "aberta" | "respondida" | "todas";

export interface OpenQuestion {
  codigo: string;
  pergunta: string;
  por_que_importa: string;
  bloqueia: string;
  destino_kb: string | null;
  estado: "aberta" | "respondida";
  resposta: string | null;
  respondida_em: string | null;
}

/** `POST /api/questions/{codigo}/answer` response — carries `aviso` when
 * `destino_kb` was set on creation (contract §B.3: the server does NOT
 * write the KB entry, the UI must surface the instruction). */
export interface AnswerResult extends OpenQuestion {
  aviso?: string;
}

const perguntasKeys = {
  all: ["perguntas"] as const,
  list: (estado: PerguntaEstado) => ["perguntas", "list", estado] as const,
};

export function usePerguntasList(estado: PerguntaEstado = "aberta") {
  return useQuery({
    queryKey: perguntasKeys.list(estado),
    queryFn: () => api.get<Envelope<OpenQuestion>>("/api/questions", { estado }),
    placeholderData: keepPreviousData,
  });
}

export interface PerguntaCreateInput {
  pergunta: string;
  por_que_importa: string;
  bloqueia: string;
  destino_kb?: string;
}

export function useCreatePergunta() {
  // Questions are listed by codigo and the server allocates codes sequentially, so the new one
  // is the last row of every unpaginated list its estado belongs to ("todas" and its own estado).
  return useCacheWriteMutation<OpenQuestion, PerguntaCreateInput>({
    mutationFn: (data) => api.post<OpenQuestion>("/api/questions", data),
    targets: [
      {
        queryKey: perguntasKeys.all,
        match: "prefix",
        commit: (old: Envelope<OpenQuestion> | undefined, saved, _vars, _ctx, queryKey) => {
          const [, kind, estado] = queryKey ?? [];
          return kind === "list" && (estado === "todas" || estado === saved.estado)
            ? pageOps.add(old, saved, "append", "codigo")
            : old;
        },
      },
    ],
  });
}

export function useAnswerPergunta(codigo: string | undefined) {
  // The answered question leaves the "aberta" list and is rewritten in "todas"; its
  // place in the "respondida" list (server order) converges on the settle refetch.
  return useCacheWriteMutation<AnswerResult, string>({
    mutationFn: (resposta) =>
      api.post<AnswerResult>(`/api/questions/${codigo}/answer`, { resposta }),
    targets: codigo
      ? [
          {
            queryKey: perguntasKeys.list("aberta"),
            commit: (old: Envelope<OpenQuestion> | undefined) => pageOps.remove(old, codigo, "codigo"),
          },
          {
            queryKey: perguntasKeys.list("todas"),
            commit: (old: Envelope<OpenQuestion> | undefined, answered) => pageOps.replace(old, codigo, answered, "codigo"),
          },
          { queryKey: perguntasKeys.list("respondida") },
        ]
      : [],
  });
}
