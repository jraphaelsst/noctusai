/**
 * `<MatriculaAtosContainer/>` — data for `<MatriculaAtosSelector/>` and, when
 * the deal pays partly in property, for one `<MatriculaPermutaGrupo/>` per
 * permuta ativo (migration 115).
 *
 * A CONTAINER, and it lives here rather than under `components/card/**` for
 * the same reason `PessoaDocumentosPanel` does: everything under `card/` is
 * presentational (S3, `lead-card-hub-p2-PROJECT.md` ruling) and is rendered
 * in tests with plain objects and no query client. This file fetches; the
 * selector renders.
 *
 * 🔴 ONE PUT REPLACES EVERYTHING, SO ONE PLACE HOLDS EVERY DRAFT
 * ---------------------------------------------------------------
 * `PUT /contratos/{id}/atos` replaces the object's quote AND every permuta's
 * in a single body — a group omitted from the payload is a group DELETED. So
 * this container owns both drafts (the object selector runs in controlled
 * mode) and every save composes the full payload, whichever button fired it.
 * Letting each section save "its own" slice would silently drop the others.
 */
import { useEffect, useMemo, useState } from "react";

import MatriculaAtosSelector from "@/components/card/MatriculaAtosSelector";
import {
  MatriculaPermutasSecao,
  type PermutaDraft,
} from "@/components/MatriculaPermutasSecao";
import {
  readableError,
  useMatriculaExtracoes,
  useVincularExtracaoImovel,
} from "@/hooks/useMatriculas";
import {
  useContratoAtos,
  useDefinirContratoAtos,
  useMatriculaAtos,
} from "@/hooks/useMatriculaEstrutura";
import { useNegociacaoEstruturada } from "@/hooks/useNegociacaoEstruturada";

export interface MatriculaAtosContainerProps {
  contratoId: string;
  /** The imóvel código, when this contract is known to be about one — narrows
   *  the extraction picker to that imóvel's matrículas. `undefined`/`null`
   *  offers every transcribed matrícula in the org instead. */
  codigo?: string | null;
  /** The deal's cliente — the permuta ativos hang off the negociação
   *  estruturada, which is keyed by cliente. Omit it and the permuta sections
   *  simply do not render (no deal context ⇒ no ativos to offer). */
  clienteId?: string | null;
}

/**
 * A parcela's linked permuta ativos. `atendimento_parcela_permuta_ativos`
 * (migration 115) is returned per parcela by
 * `negociacao_estruturada_service`, but `types/negociacaoEstruturada.ts` does
 * not declare it yet — narrowed HERE rather than widening a shared type this
 * slice does not own. Reported as a backend/FE type gap in the delivery note.
 */
interface ParcelaComAtivos {
  permuta_ativo_ids?: string[];
}

export function MatriculaAtosContainer({
  contratoId,
  codigo,
  clienteId,
}: MatriculaAtosContainerProps) {
  const [buscaExtracao, setBuscaExtracao] = useState("");
  const [extracaoSelecionadaId, setExtracaoSelecionadaId] = useState<string | null>(null);
  const [draftAtoIds, setDraftAtoIds] = useState<string[]>([]);
  const [permutaDrafts, setPermutaDrafts] = useState<Record<string, PermutaDraft>>({});

  const extracoesQuery = useMatriculaExtracoes(codigo ? { codigo } : undefined);
  // Bug H — an existing transcription may predate this imóvel getting a
  // registry identity, or was uploaded standalone; the scoped query above
  // can never surface it (it has no `codigo` to match). Always fetched
  // (bounded, same cost class as `extracoesQuery`); only usable once
  // `codigo` is known, since linking one needs a target.
  const extracoesSemImovelQuery = useMatriculaExtracoes({ semImovel: true });
  const selecaoQuery = useContratoAtos(contratoId);
  const atosQuery = useMatriculaAtos(extracaoSelecionadaId);
  const definirMutation = useDefinirContratoAtos(contratoId);
  const vincularMutation = useVincularExtracaoImovel();
  const estruturadaQuery = useNegociacaoEstruturada(clienteId ?? null);

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

  // Re-seed the OBJECT draft from the persisted selection when it belongs to
  // the extraction being browsed. Keyed on the ids themselves, not object
  // identity, so an unrelated refetch does not stomp an edit in progress
  // (the discipline `MatriculaAtosSelector` used before the draft moved up).
  const persistidoObjeto = (selecaoQuery.data?.atos ?? []).map((a) => a.ato_id).join(",");
  const selecaoExtracaoId = selecaoQuery.data?.extracao_id ?? null;
  useEffect(() => {
    if (extracaoSelecionadaId && extracaoSelecionadaId === selecaoExtracaoId) {
      setDraftAtoIds(persistidoObjeto ? persistidoObjeto.split(",") : []);
    } else {
      setDraftAtoIds([]);
    }
  }, [extracaoSelecionadaId, selecaoExtracaoId, persistidoObjeto]);

  // Same, per permuta group.
  const persistidoPermutas = JSON.stringify(
    (selecaoQuery.data?.permutas ?? []).map((p) => [
      p.permuta_ativo_id,
      p.extracao_id,
      p.atos.map((a) => a.ato_id),
    ]),
  );
  useEffect(() => {
    setPermutaDrafts(
      Object.fromEntries(
        (selecaoQuery.data?.permutas ?? []).map((p) => [
          p.permuta_ativo_id,
          { extracaoId: p.extracao_id, atoIds: p.atos.map((a) => a.ato_id) },
        ]),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persistidoPermutas]);

  // Which properties this deal pays with: the negociação's own ativo plus any
  // linked to a permuta parcela. A `Set` because the same ativo legitimately
  // appears in both places, and it must produce ONE section.
  const ativoIds = useMemo(() => {
    const dados = estruturadaQuery.data;
    if (!dados) return [] as string[];
    const ids = new Set<string>();
    if (dados.permuta_ativo_id) ids.add(dados.permuta_ativo_id);
    for (const parcela of dados.parcelas ?? []) {
      for (const id of (parcela as ParcelaComAtivos).permuta_ativo_ids ?? []) {
        ids.add(id);
      }
    }
    return [...ids];
  }, [estruturadaQuery.data]);

  const erroSalvar =
    definirMutation.isError && definirMutation.error instanceof Error
      ? readableError(definirMutation.error)
      : null;

  /** The FULL payload — object draft + every permuta group that has a pick. */
  function salvar(objeto: { extracaoId: string | null; atoIds: string[] }) {
    definirMutation.mutate({
      extracaoId: objeto.extracaoId,
      atoIds: objeto.atoIds,
      permutas: Object.entries(permutaDrafts)
        .filter(([, d]) => !!d.extracaoId && d.atoIds.length > 0)
        .map(([permutaAtivoId, d]) => ({
          permutaAtivoId,
          extracaoId: d.extracaoId as string,
          atoIds: d.atoIds,
        })),
    });
  }

  // Attach an unlinked transcription to THIS imóvel, then behave exactly
  // like picking one from the scoped list: browse its acts and select it.
  function vincular(extracaoId: string) {
    if (!codigo) return;
    vincularMutation.mutate(
      { extracaoId, codigo },
      { onSuccess: () => setExtracaoSelecionadaId(extracaoId) },
    );
  }

  // Two signals off `data`, never `isLoading` — false mid-refetch, so a
  // skeleton/error branch keyed off it would lie over data still good to
  // look at (`KB § PATTERNS/frontend/lying-loading-state.md`).
  const extracoesLoading = extracoesQuery.isPending && !extracoesQuery.data;
  const extracoesError = extracoesQuery.isError && !extracoesQuery.data;
  const extracoesSemImovelLoading =
    extracoesSemImovelQuery.isPending && !extracoesSemImovelQuery.data;
  const atosLoading = atosQuery.isPending && !atosQuery.data;
  const atosError = atosQuery.isError && !atosQuery.data;
  const selecaoLoading = selecaoQuery.isPending && !selecaoQuery.data;
  const selecaoError = selecaoQuery.isError && !selecaoQuery.data;

  return (
    <div className="space-y-2">
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
        extracoesSemImovel={
          codigo
            ? (extracoesSemImovelQuery.data ?? []).map((e) => ({
                id: e.id,
                nome_arquivo: e.nome_arquivo,
                status: e.status,
                created_at: e.created_at,
              }))
            : []
        }
        extracoesSemImovelLoading={codigo ? extracoesSemImovelLoading : false}
        onVincularExtracao={vincular}
        vinculando={vincularMutation.isPending}
        buscaExtracao={buscaExtracao}
        onBuscaExtracaoChange={setBuscaExtracao}
        extracaoSelecionadaId={extracaoSelecionadaId}
        onSelecionarExtracao={setExtracaoSelecionadaId}
        atos={atosQuery.data?.atos ?? []}
        atosLoading={atosLoading}
        atosError={atosError}
        selecao={selecaoQuery.data?.atos}
        selecaoExtracaoId={selecaoExtracaoId}
        selecaoLoading={selecaoLoading}
        selecaoError={selecaoError}
        selecionadoPor={selecaoQuery.data?.selecionado_por ?? null}
        selecionadoEm={selecaoQuery.data?.selecionado_em ?? null}
        saving={definirMutation.isPending}
        draftAtoIds={draftAtoIds}
        onDraftAtoIdsChange={setDraftAtoIds}
        errorMessage={erroSalvar}
        onSave={({ extracaoId, atoIds }) => salvar({ extracaoId, atoIds })}
      />

      {/* Rendered only when the deal HAS permuta ativos — see that file's
          header for why the ativo catalog must not be fetched otherwise. */}
      {ativoIds.length > 0 && (
        <MatriculaPermutasSecao
          ativoIds={ativoIds}
          drafts={permutaDrafts}
          onDraftChange={(permutaAtivoId, draft) =>
            setPermutaDrafts((atual) => ({ ...atual, [permutaAtivoId]: draft }))
          }
          saving={definirMutation.isPending}
          errorMessage={erroSalvar}
          onSalvar={() =>
            salvar({ extracaoId: extracaoSelecionadaId, atoIds: draftAtoIds })
          }
        />
      )}
    </div>
  );
}
