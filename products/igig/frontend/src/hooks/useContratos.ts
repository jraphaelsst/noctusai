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
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api, cleanParams, unwrapData } from "@/lib/api";
import { patchById } from "@/lib/cacheOps";
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
  data_encerramento: string | null;
  motivo_encerramento: string | null;
  status: ContratoStatus;
  modalidade_assinatura: ModalidadeAssinatura;
  assinado_em: string | null;
  assinado_manual_em: string | null;
  documento_key: string | null;
  documento_assinado_key: string | null;
  link_assinatura: string | null;
  created_at: string;
}

/** The commercial fields `PATCH /api/contratos/{id}` accepts. */
export type ContratoEdicao = Partial<
  Pick<Contrato, "numero" | "valor_mensal" | "posts_por_mes" | "valor_excedente" | "dia_vencimento" | "data_inicio" | "data_fim">
>;

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
  const lista = [...CONTRATOS_QUERY_KEY, "lista"] as const;
  /** Signed, short-TTL URLs — fetched on click, never cached. */
  const urlPdf = useMutation({ // noc-allow: invalidate-only — a signed short-TTL URL fetched on click and deliberately never cached; no read to update
    mutationFn: (id: string) =>
      api
        .get(`/api/contratos/${encodeURIComponent(id)}/pdf`)
        .then(unwrapData<{ url: string; url_assinado: string | null }>),
  });
  /** Física only: the printed contract came back signed by hand. */
  const marcarAssinado = useCacheWriteMutation<Contrato, { id: string; arquivo?: File | null }>({
    mutationFn: ({ id, arquivo }) => {
      const form = new FormData();
      if (arquivo) form.append("arquivo", arquivo);
      return api.upload(`/api/contratos/${encodeURIComponent(id)}/marcar-assinado`, form).then(unwrapData<Contrato>);
    },
    targets: [patchById<Contrato, { id: string; arquivo?: File | null }>(lista, (v) => v.id)],
    // Activating the contract flips the cliente to `ativo` server-side too.
    invalidate: [["igig", "clientes"]],
  });
  const editar = useCacheWriteMutation<Contrato, { id: string } & ContratoEdicao>({
    mutationFn: ({ id, ...campos }) =>
      api.patch(`/api/contratos/${encodeURIComponent(id)}`, campos).then(unwrapData<Contrato>),
    targets: [
      patchById<Contrato, { id: string } & ContratoEdicao>(lista, (v) => v.id, ({ id: _id, ...campos }) => campos),
    ],
  });
  /** Contratos are never deleted — they are encerrados. */
  const encerrar = useCacheWriteMutation<
    Contrato,
    { id: string; motivo: string; data_encerramento?: string }
  >({
    mutationFn: ({ id, ...corpo }) =>
      api.post(`/api/contratos/${encodeURIComponent(id)}/encerrar`, corpo).then(unwrapData<Contrato>),
    targets: [
      patchById<Contrato, { id: string; motivo: string; data_encerramento?: string }>(
        lista,
        (v) => v.id,
        (v) => ({ status: "encerrado" as const, motivo_encerramento: v.motivo }),
      ),
    ],
  });
  return { urlPdf, marcarAssinado, editar, encerrar };
}
