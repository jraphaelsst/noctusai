/**
 * Possível duplicado + vínculo (S6, CONTRACT §8.6 / §8.7).
 *
 *   GET  /api/imoveis/duplicatas?status=pendente
 *   POST /api/imoveis/duplicatas/{id}/descartar
 *   POST /api/imoveis/duplicatas/{id}/vincular        (admin)
 *   POST /api/imoveis/{codigo}/desvincular            (admin)
 *
 * Every action invalidates the three families that render an imóvel: the
 * catalog (`["sw","imoveis"]`, which covers list + detail), the picker search
 * (`["sw","cardHub","imoveisBusca"]`) and the duplicatas queue itself.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

export type SinalDuplicata =
  | "matricula_cri"
  | "matricula"
  | "endereco"
  | "empreendimento_area_preco";

export const SINAL_LABEL: Record<SinalDuplicata, string> = {
  matricula_cri: "Mesma matrícula e cartório",
  matricula: "Mesma matrícula",
  endereco: "Mesmo endereço",
  empreendimento_area_preco: "Mesmo empreendimento, área e preço próximos",
};

export function sinalLabel(sinal: string): string {
  return SINAL_LABEL[sinal as SinalDuplicata] ?? sinal;
}

export interface ImovelResumo {
  codigo: string;
  titulo: string | null;
  endereco_resumo: string | null;
  valor_venda: number | string | null;
  area_total: number | string | null;
  foto_destaque: string | null;
}

export interface Duplicata {
  id: string;
  score: number;
  sinais: { sinal: string; detalhe?: string | null }[];
  status: string;
  detectado_em: string | null;
  manual: ImovelResumo;
  vista: ImovelResumo;
}

export interface VinculoResultado {
  vinculo: { manual_codigo: string; vista_codigo: string } | null;
  legal?: { status: string; mensagem?: string | null } | null;
}

const DUPLICATAS_KEY = ["sw", "imoveis", "duplicatas"] as const;

/** The three families that render an imóvel: the catalog, the picker search and the duplicatas queue. */
const FAMILIAS_IMOVEL = [
  ["sw", "imoveis"],
  ["sw", "cardHub", "imoveisBusca"],
  DUPLICATAS_KEY,
];

export function useDuplicatasPendentes(enabled = true) {
  return useQuery({
    queryKey: [...DUPLICATAS_KEY, "pendente"],
    queryFn: async () =>
      (await api.get<Duplicata[]>("/api/imoveis/duplicatas?status=pendente")) ?? [],
    enabled,
    placeholderData: (prev) => prev,
  });
}

/** The queue holds PENDING duplicatas: an acted-on one leaves it on the click. */
const sairDaFila = (id: string) => [
  {
    queryKey: [...DUPLICATAS_KEY, "pendente"] as const,
    optimistic: (old: Duplicata[] | undefined) => listOps.remove(old, id),
  },
];

export function useDescartarDuplicata() {
  return useCacheWriteMutation<Duplicata, string>({
    mutationFn: (id) =>
      api.post<Duplicata>(
        `/api/imoveis/duplicatas/${encodeURIComponent(id)}/descartar`,
        {},
      ),
    targets: sairDaFila,
    invalidate: FAMILIAS_IMOVEL,
  });
}

export function useVincularDuplicata() {
  return useCacheWriteMutation<VinculoResultado, string>({
    mutationFn: (id) =>
      api.post<VinculoResultado>(
        `/api/imoveis/duplicatas/${encodeURIComponent(id)}/vincular`,
        {},
      ),
    targets: sairDaFila,
    invalidate: FAMILIAS_IMOVEL,
  });
}

export function useDesvincularImovel() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — unlinking re-opens a duplicata and re-splits two imóveis across the catalog; the response is only the vínculo result
    mutationFn: (codigo: string) =>
      api.post<VinculoResultado>(
        `/api/imoveis/${encodeURIComponent(codigo)}/desvincular`,
        {},
      ),
    onSuccess: () => Promise.all(FAMILIAS_IMOVEL.map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });
}
