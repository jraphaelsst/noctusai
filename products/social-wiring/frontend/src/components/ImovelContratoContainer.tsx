/**
 * `<ImovelContratoContainer/>` — data for `<ImovelContratoCard/>` and
 * `<ImovelCertidoesCard/>`.
 *
 * A CONTAINER, in `components/` rather than `components/imovel/**`, for the
 * same reason `MatriculaAtosContainer` is: everything under `imovel/` is
 * presentational and is rendered in tests with plain objects and no query
 * client. This file fetches; those cards render.
 *
 * It owns four reads (título phrase, ônus creditor, previous owners, the CND
 * group) and three writes. The certidão UPLOAD reuses
 * `useImovelDocumentoMutations` — the CND is an ordinary `imovel_documentos`
 * row, and a second upload path to the same endpoint is how two callers drift
 * apart on validation and cache invalidation.
 */
import ImovelCertidoesCard from "@/components/imovel/ImovelCertidoesCard";
import ImovelContratoCard from "@/components/imovel/ImovelContratoCard";
import {
  useAntigosProprietarios,
  useConfirmarDocumentoExtracao,
  useConfirmarOnusCredor,
  useConfirmarTitulo,
  useImovelCertidoes,
  useOnusCredor,
  useTituloAquisitivo,
} from "@/hooks/useImovelContrato";
import { useImovelDocumentoMutations } from "@/hooks/useImovelDados";

export function ImovelContratoContainer({ codigo }: { codigo: string }) {
  const tituloQuery = useTituloAquisitivo(codigo);
  const onusQuery = useOnusCredor(codigo);
  const antigosQuery = useAntigosProprietarios(codigo);
  const certidoesQuery = useImovelCertidoes(codigo);

  const confirmarTitulo = useConfirmarTitulo(codigo);
  const confirmarOnus = useConfirmarOnusCredor(codigo);
  const confirmarExtracao = useConfirmarDocumentoExtracao(codigo);
  const documentoMutations = useImovelDocumentoMutations(codigo);

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // a skeleton/empty branch keyed off it would lie over data still good to
  // look at — and `isFetching` alone would UNMOUNT the editors on every
  // confirmation's refetch. KB § PATTERNS/frontend/lying-loading-state.md
  return (
    <>
      <ImovelContratoCard
        codigo={codigo}
        titulo={tituloQuery.data}
        tituloShowSkeleton={tituloQuery.isPending && !tituloQuery.data}
        tituloIsRefreshing={tituloQuery.isFetching && !!tituloQuery.data}
        tituloIsError={tituloQuery.isError && !tituloQuery.data}
        savingTitulo={confirmarTitulo.isPending}
        onConfirmarTitulo={(texto) => confirmarTitulo.mutate(texto)}
        onus={onusQuery.data}
        onusShowSkeleton={onusQuery.isPending && !onusQuery.data}
        onusIsRefreshing={onusQuery.isFetching && !!onusQuery.data}
        onusIsError={onusQuery.isError && !onusQuery.data}
        savingOnus={confirmarOnus.isPending}
        onConfirmarOnusCredor={(credor) => confirmarOnus.mutate(credor)}
        antigos={antigosQuery.data}
        antigosShowSkeleton={antigosQuery.isPending && !antigosQuery.data}
        antigosIsError={antigosQuery.isError && !antigosQuery.data}
      />

      <ImovelCertidoesCard
        certidoes={certidoesQuery.data}
        showSkeleton={certidoesQuery.isPending && !certidoesQuery.data}
        isRefreshing={certidoesQuery.isFetching && !!certidoesQuery.data}
        isError={certidoesQuery.isError && !certidoesQuery.data}
        uploading={documentoMutations.upload.isPending}
        savingDocumentoId={
          confirmarExtracao.isPending
            ? (confirmarExtracao.variables?.documentoId ?? null)
            : null
        }
        errorMessage={
          documentoMutations.upload.error?.message ??
          confirmarExtracao.error?.message ??
          null
        }
        onUpload={(file, tipoDocumento) =>
          documentoMutations.upload.mutate({ file, tipoDocumento })
        }
        onConfirmar={(documentoId, _tipo, patch) =>
          confirmarExtracao.mutate({ documentoId, patch })
        }
      />
    </>
  );
}
