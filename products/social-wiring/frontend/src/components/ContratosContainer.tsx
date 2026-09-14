/**
 * `<ContratosContainer/>` — data for the card's Contratos subpage.
 *
 * Same split as `FinanciamentoContainer`/`NegociacaoContainer`: the dialog
 * stays presentational and this owns the query + the mutations that do not
 * need their own modal (status change, new version, deletes, open/download).
 *
 * The CREATE dialog is deliberately NOT owned here — `NovoContratoDialog`
 * renders as a sibling of the card in `ClienteDetailModal` (see its header
 * comment), so this container only receives `onNovoContrato` to flip that
 * dialog's `open` boolean.
 *
 * 🔴 `renderMatriculaAtos` narrows the picker to THIS deal's imóvel: the
 * código comes from `atendimento_negociacao.imovel_codigo` (the same
 * `useNegociacao` query the Negociação tab already runs, so no extra
 * request). The backend refuses a selection from another imóvel's matrícula
 * regardless — this only keeps the operator from being offered one. While the
 * deal has no imóvel yet the picker lists every transcribed matrícula.
 */
import { toast } from "sonner";

import { GeradorContratoContainer } from "@/components/GeradorContratoContainer";
import { MatriculaAtosContainer } from "@/components/MatriculaAtosContainer";
import ContratosPanel from "@/components/card/ContratosPanel";
import { useContratoMutations, useContratos } from "@/hooks/useContratos";
import { useNegociacao } from "@/hooks/useNegociacao";

function toastServerError(err: unknown, fallback: string) {
  const message = err instanceof Error && err.message ? err.message : fallback;
  toast.error(message);
}

export function ContratosContainer({
  clienteId,
  onNovoContrato,
}: {
  clienteId: string;
  onNovoContrato: () => void;
}) {
  const query = useContratos(clienteId);
  const mutations = useContratoMutations(clienteId);
  // The deal's imóvel — narrows the matrícula picker (see header note).
  const negociacao = useNegociacao(clienteId);
  const imovelCodigo = negociacao.data?.imovel_codigo ?? null;

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // an empty/error branch keyed off it would lie over data that is still
  // good to look at.
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  return (
    <ContratosPanel
      contratos={query.data}
      showSkeleton={showSkeleton}
      isRefreshing={isRefreshing}
      isError={query.isError}
      errorMessage={query.error instanceof Error ? query.error.message : null}
      onRetry={() => query.refetch()}
      onNovoContrato={onNovoContrato}
      addingVersaoContratoId={
        mutations.addVersao.isPending
          ? (mutations.addVersao.variables?.contratoId ?? null)
          : null
      }
      patchingContratoId={
        mutations.patch.isPending ? (mutations.patch.variables?.contratoId ?? null) : null
      }
      deletingVersaoId={
        mutations.deleteVersao.isPending
          ? (mutations.deleteVersao.variables?.versaoId ?? null)
          : null
      }
      deletingContratoId={
        mutations.deleteContrato.isPending
          ? (mutations.deleteContrato.variables?.contratoId ?? null)
          : null
      }
      onAddVersao={(contratoId, file) =>
        mutations.addVersao.mutate(
          { contratoId, file },
          { onError: (err) => toastServerError(err, "Não foi possível enviar a nova versão.") },
        )
      }
      onPatchStatus={(contratoId, status) =>
        mutations.patch.mutate(
          { contratoId, patch: { status } },
          { onError: (err) => toastServerError(err, "Não foi possível atualizar o status.") },
        )
      }
      onDeleteVersao={(contratoId, versaoId, motivo) =>
        mutations.deleteVersao.mutate(
          { contratoId, versaoId, motivo },
          { onError: (err) => toastServerError(err, "Não foi possível remover a versão.") },
        )
      }
      onDeleteContrato={(contratoId, motivo) =>
        mutations.deleteContrato.mutate(
          { contratoId, motivo },
          { onError: (err) => toastServerError(err, "Não foi possível remover o contrato.") },
        )
      }
      onOpen={async (contratoId, versaoId) => {
        try {
          // 🔴 Fired only from an explicit click, same discipline as the
          // financiamento document URL — never pre-fetched or refreshed.
          const res = await mutations.getUrl.mutateAsync({ contratoId, versaoId, intent: "view" });
          if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
        } catch (err) {
          toastServerError(err, "Não foi possível abrir o contrato.");
        }
      }}
      onDownload={async (contratoId, versaoId) => {
        try {
          const res = await mutations.getUrl.mutateAsync({
            contratoId,
            versaoId,
            intent: "download",
          });
          if (res?.url) window.open(res.url, "_blank", "noopener,noreferrer");
        } catch (err) {
          toastServerError(err, "Não foi possível baixar o contrato.");
        }
      }}
      renderMatriculaAtos={(contratoId) => (
        <MatriculaAtosContainer contratoId={contratoId} codigo={imovelCodigo} />
      )}
      renderGeradorContrato={(contratoId, aberto) => (
        <GeradorContratoContainer clienteId={clienteId} contratoId={contratoId} aberto={aberto} />
      )}
    />
  );
}
