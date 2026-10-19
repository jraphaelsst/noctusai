/**
 * Julia › Conhecimento — "o que a Julia sabe" (contract section 3, wave 1).
 *
 *   GET /api/julia/conhecimento            member: {data:{secoes:{secao:{dados,versao,updated_at}}, preview_md, hash}}
 *   PUT /api/julia/conhecimento/{secao}    admin:  {dados, versao} -> {data:{secao,dados,versao}}; 409 versao_conflito
 *   GET /api/julia/conhecimento/preview    member: {data:{markdown, hash}}
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export interface SecaoSalva {
  dados: unknown;
  versao: number;
  updated_at: string | null;
}

export interface JuliaConhecimento {
  secoes: Record<string, SecaoSalva>;
  preview_md: string;
  hash: string;
}

export interface JuliaPreview {
  markdown: string;
  hash: string;
}

export const JULIA_CONHECIMENTO_KEY = ["sw", "julia", "conhecimento"] as const;

export function useJuliaConhecimento() {
  return useQuery({
    queryKey: JULIA_CONHECIMENTO_KEY,
    queryFn: async () => (await api.get<{ data: JuliaConhecimento }>("/api/julia/conhecimento")).data,
  });
}

export function useSalvarSecao() {
  const qc = useQueryClient();
  return useMutation<
    { data: { secao: string; dados: unknown; versao: number } },
    unknown,
    { secao: string; dados: unknown; versao: number }
  >({
    mutationFn: ({ secao, dados, versao }) => api.put(`/api/julia/conhecimento/${secao}`, { dados, versao }),
    onSuccess: () => qc.invalidateQueries({ queryKey: JULIA_CONHECIMENTO_KEY }),
  });
}

export function usePreviewConhecimento(enabled: boolean) {
  return useQuery({
    queryKey: [...JULIA_CONHECIMENTO_KEY, "preview"],
    enabled,
    queryFn: async () => (await api.get<{ data: JuliaPreview }>("/api/julia/conhecimento/preview")).data,
  });
}

export function codigoErroConhecimento(err: unknown): string | null {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof code === "string" ? code : null;
}

const MENSAGENS: Record<string, string> = {
  versao_conflito: "Outra pessoa alterou esta seção enquanto você editava. Recarregue para ver a versão mais recente.",
  secao_invalida: "Seção desconhecida.",
  invalid_field: "Algum campo está inválido. Revise os valores e tente de novo.",
};

export function mensagemErroConhecimento(err: unknown, fallback: string): string {
  const code = codigoErroConhecimento(err);
  if (code && MENSAGENS[code]) return MENSAGENS[code];
  if ((err as { status?: number } | null)?.status === 403) return "Apenas owner ou admin da organização pode editar.";
  return mensagemErroServidor(err, fallback);
}
