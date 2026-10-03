/**
 * The person-record fields only the CONTRACT needs (contrato-partes-CONTRACT
 * §3, migration 193): `identidade_tipo` (RG / RNE / RNM) and the pacto
 * antenupcial citation (`pacto_antenupcial_{data,tabelionato,livro,folha}`),
 * each pacto column with its provenance quintet (`_origem`, `_documento_id`,
 * `_em`, `_confirmado_por`, `_confirmado_em`).
 *
 * Read from `GET /api/clientes/{id}` (the full person row — the checklist's
 * `valores` does not carry these columns); written through the SAME
 * `PATCH /api/clientes/{id}` as every other person field
 * (`useDadosPessoaisMutation`, whose `["sw","clientes"]` invalidation also
 * refreshes this key).
 *
 * No `placeholderData`: keyed by a PERSON id (personal data — the documented
 * lying-loading-state exception).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { IdentidadeTipo } from "@/components/card/DadosPessoaisForm";

export const CAMPOS_PACTO = [
  "pacto_antenupcial_data",
  "pacto_antenupcial_tabelionato",
  "pacto_antenupcial_livro",
  "pacto_antenupcial_folha",
] as const;

export type CampoPacto = (typeof CAMPOS_PACTO)[number];

/** The slice of the person row this surface reads. Provenance keys are
 *  `${campo}_origem` / `${campo}_confirmado_em` (optional for a pre-193
 *  backend). */
export type QualificacaoContratoRegistro = {
  id: string;
  regime_bens?: string | null;
  estado_civil?: string | null;
  identidade_tipo?: IdentidadeTipo | null;
} & Partial<Record<CampoPacto, string | null>> &
  Partial<Record<`${CampoPacto}_origem` | `${CampoPacto}_confirmado_em`, string | null>>;

export const qualificacaoContratoKey = (clienteId: string) =>
  ["sw", "clientes", clienteId, "registro"] as const;

export function useQualificacaoContrato(clienteId: string | null) {
  const query = useQuery({
    queryKey: qualificacaoContratoKey(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<QualificacaoContratoRegistro>(`/api/clientes/${encodeURIComponent(clienteId as string)}`),
    enabled: !!clienteId,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}
