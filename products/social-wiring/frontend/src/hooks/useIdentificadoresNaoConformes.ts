/**
 * The operators' hand-in for identifiers that do not fit their type
 * (`GET /api/identificadores/nao-conformes`, backed by migration 187's
 * `vw_identificadores_nao_conformes`). The CORRECTION is not a new write path:
 * it goes through the existing manual-edit endpoints, which canonicalize and
 * validate on write.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface IdentificadorNaoConforme {
  chave: string;
  tabela: "clientes" | "imovel_dados" | "certidao_consultas";
  linha_id: string;
  campo: string;
  rotulo_campo: string;
  valor: string;
  canonico: string | null;
  situacao: "nao_cabe" | "canonizavel";
  /** pt-BR reason the stored value does not fit. */
  motivo: string;
  entidade_nome: string;
  link: { tipo: "cliente" | "imovel"; id: string } | null;
  /** Where an inline correction is sent; `null` = fix it at the linked record. */
  edicao: { tipo: "cliente" | "imovel"; id: string; campo: string } | null;
}

export interface IdentificadoresNaoConformesPage {
  items: IdentificadorNaoConforme[];
  total: number;
  page: number;
  page_size: number;
}

export const IDENTIFICADORES_KEY = ["identificadores", "nao-conformes"] as const;

export function useIdentificadoresNaoConformes(page: number, pageSize = 50) {
  return useQuery({
    queryKey: [...IDENTIFICADORES_KEY, page, pageSize],
    queryFn: () =>
      api.get<IdentificadoresNaoConformesPage>(
        `/api/identificadores/nao-conformes?page=${page}&page_size=${pageSize}`,
      ),
    // Paging must not unmount the list it is paging.
    placeholderData: keepPreviousData,
  });
}

/** Sends the corrected value through the EXISTING manual-edit endpoint for the
 *  row's entity (clientes PATCH / imóvel dados PATCH). */
export function useCorrigirIdentificador() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ alvo, valor }: { alvo: NonNullable<IdentificadorNaoConforme["edicao"]>; valor: string }) =>
      alvo.tipo === "cliente"
        ? api.patch(`/api/clientes/${encodeURIComponent(alvo.id)}`, { [alvo.campo]: valor })
        : api.patch(`/api/imoveis/${encodeURIComponent(alvo.id)}/dados`, { [alvo.campo]: valor }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: IDENTIFICADORES_KEY });
    },
  });
}
