/**
 * Contratos — list per cliente, signed-URL download, "Marcar como assinado"
 * (wave-2 contract, Slice A; roadmap R12). Backend mirror:
 * `app/routers/contrato_router.py`.
 *
 *   GET  /api/contratos?cliente_id=                → {data: Contrato[]}
 *   GET  /api/contratos/{id}/pdf                   → {data: {url, url_assinado}}
 *   POST /api/contratos/{id}/marcar-assinado       multipart, optional `arquivo`
 *                                                  (física only; 409 otherwise)
 *
 * Contracts are CREATED from an accepted orçamento
 * (`useOrcamentoMutations().gerarContrato`), which invalidates this family's
 * key (`["igig", "contratos"]`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, cleanParams, unwrapData } from "@/lib/api";
import type { ModalidadeAssinatura } from "@/types/crm";

export type ContratoStatus = "rascunho" | "aguardando_assinatura" | "ativo" | "encerrado";

export const CONTRATO_STATUS_LABEL: Record<ContratoStatus, string> = {
  rascunho: "Rascunho",
  aguardando_assinatura: "Aguardando assinatura",
  ativo: "Ativo",
  encerrado: "Encerrado",
};

/** Mirror of the `igig.contrato` row (006 + 012 + 018) as the router returns it. */
export interface Contrato {
  id: string;
  cliente_id: string;
  orcamento_id: string | null;
  numero: string | null;
  valor_mensal: number | null;
  posts_por_mes: number | null;
  valor_excedente: number | null;
  dia_vencimento: number | null;
  data_inicio: string | null;
  data_fim: string | null;
  status: ContratoStatus;
  modalidade_assinatura: ModalidadeAssinatura;
  assinado_em: string | null;
  assinado_manual_em: string | null;
  documento_key: string | null;
  documento_assinado_key: string | null;
  link_assinatura: string | null;
  created_at: string;
}

export const CONTRATOS_QUERY_KEY = ["igig", "contratos"] as const;

export function useContratos(clienteId: string | null) {
  const params = cleanParams({ cliente_id: clienteId ?? undefined });
  const query = useQuery({
    queryKey: [...CONTRATOS_QUERY_KEY, "lista", params],
    queryFn: () => api.get("/api/contratos", params).then(unwrapData<Contrato[]>),
    enabled: !!clienteId,
  });
  const data = query.data;
  return {
    ...query,
    contratos: data ?? [],
    showSkeleton: !!clienteId && query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useContratoMutations() {
  const qc = useQueryClient();
  /** Signed, short-TTL URLs — fetched on click, never cached. */
  const urlPdf = useMutation({
    mutationFn: (id: string) =>
      api
        .get(`/api/contratos/${encodeURIComponent(id)}/pdf`)
        .then(unwrapData<{ url: string; url_assinado: string | null }>),
  });
  /** Física only: the printed contract came back signed by hand. */
  const marcarAssinado = useMutation({
    mutationFn: ({ id, arquivo }: { id: string; arquivo?: File | null }) => {
      const form = new FormData();
      if (arquivo) form.append("arquivo", arquivo);
      return api.upload(`/api/contratos/${encodeURIComponent(id)}/marcar-assinado`, form).then(unwrapData<Contrato>);
    },
    // Activating the contract flips the cliente to `ativo` server-side too.
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: CONTRATOS_QUERY_KEY }),
        qc.invalidateQueries({ queryKey: ["igig", "clientes"] }),
      ]),
  });
  return { urlPdf, marcarAssinado };
}
