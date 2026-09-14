/**
 * `<MatriculaAtosContainer/>` — data for `<MatriculaAtosSelector/>`.
 *
 * A CONTAINER, and it lives here rather than under `components/card/**` for
 * the same reason `PessoaDocumentosPanel` does: everything under `card/` is
 * presentational (S3, `lead-card-hub-p2-PROJECT.md` ruling) and is rendered
 * in tests with plain objects and no query client. This file fetches; the
 * selector renders.
 *
 * Owns three queries: the imóvel's transcribed matrículas (to pick FROM), the
 * acts of whichever one is being browsed, and the contract's persisted
 * selection — plus the mutation that replaces it.
 */
import { useEffect, useState } from "react";

import MatriculaAtosSelector from "@/components/card/MatriculaAtosSelector";
import { useMatriculaExtracoes } from "@/hooks/useMatriculas";
import {
  useContratoAtos,
  useDefinirContratoAtos,
  useMatriculaAtos,
} from "@/hooks/useMatriculaEstrutura";

export interface MatriculaAtosContainerProps {
  contratoId: string;
  /** The imóvel código, when this contract is known to be about one — narrows
   *  the extraction picker to that imóvel's matrículas. `undefined`/`null`
   *  offers every transcribed matrícula in the org instead. */
  codigo?: string | null;
}

export function MatriculaAtosContainer({ contratoId, codigo }: MatriculaAtosContainerProps) {
  const [buscaExtracao, setBuscaExtracao] = useState("");
  const [extracaoSelecionadaId, setExtracaoSelecionadaId] = useState<string | null>(null);

  const extracoesQuery = useMatriculaExtracoes(codigo ? { codigo } : undefined);
  const selecaoQuery = useContratoAtos(contratoId);
  const atosQuery = useMatriculaAtos(extracaoSelecionadaId);
  const definirMutation = useDefinirContratoAtos(contratoId);

  // Default the browsed extraction to the contract's PERSISTED one, once it
  // is known — but only ever set it once: an operator who deliberately picks
  // a different matrícula to re-base the quote on must not be bounced back
  // by a background refetch of the same persisted value.
  useEffect(() => {
    if (extracaoSelecionadaId === null && selecaoQuery.data?.extracao_id) {
      setExtracaoSelecionadaId(selecaoQuery.data.extracao_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selecaoQuery.data?.extracao_id]);

  // Two signals off `data`, never `isLoading` — false mid-refetch, so a
  // skeleton/error branch keyed off it would lie over data still good to
  // look at (`KB § PATTERNS/frontend/lying-loading-state.md`).
  const extracoesLoading = extracoesQuery.isPending && !extracoesQuery.data;
  const extracoesError = extracoesQuery.isError && !extracoesQuery.data;
  const atosLoading = atosQuery.isPending && !atosQuery.data;
  const atosError = atosQuery.isError && !atosQuery.data;
  const selecaoLoading = selecaoQuery.isPending && !selecaoQuery.data;
  const selecaoError = selecaoQuery.isError && !selecaoQuery.data;

  return (
    <MatriculaAtosSelector
      contratoId={contratoId}
      codigo={codigo}
      extracoes={(extracoesQuery.data ?? []).map((e) => ({
        id: e.id,
        nome_arquivo: e.nome_arquivo,
        status: e.status,
        created_at: e.created_at,
      }))}
      extracoesLoading={extracoesLoading}
      extracoesError={extracoesError}
      buscaExtracao={buscaExtracao}
      onBuscaExtracaoChange={setBuscaExtracao}
      extracaoSelecionadaId={extracaoSelecionadaId}
      onSelecionarExtracao={setExtracaoSelecionadaId}
      atos={atosQuery.data?.atos ?? []}
      atosLoading={atosLoading}
      atosError={atosError}
      selecao={selecaoQuery.data?.atos}
      selecaoExtracaoId={selecaoQuery.data?.extracao_id ?? null}
      selecaoLoading={selecaoLoading}
      selecaoError={selecaoError}
      selecionadoPor={selecaoQuery.data?.selecionado_por ?? null}
      selecionadoEm={selecaoQuery.data?.selecionado_em ?? null}
      saving={definirMutation.isPending}
      onSave={({ extracaoId, atoIds }) => definirMutation.mutate({ extracaoId, atoIds })}
    />
  );
}
