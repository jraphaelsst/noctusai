/**
 * `<ImovelContratoContainer/>` — data for `<ImovelContratoCard/>` and
 * `<ImovelCertidoesCard/>`.
 *
 * A CONTAINER, in `components/` rather than `components/imovel/**`, for the
 * same reason `MatriculaAtosContainer` is: everything under `imovel/` is
 * presentational and is rendered in tests with plain objects and no query
 * client. This file fetches; those cards render.
 *
 * It owns its reads (título phrase, endereço, descrição do imóvel, ônus
 * creditor, previous owners, the CND group) and their writes — including the
 * migration-306 manual entries (descrição typed, certidão typed with no
 * file). The certidão UPLOAD reuses
 * `useImovelDocumentoMutations` — the CND is an ordinary `imovel_documentos`
 * row, and a second upload path to the same endpoint is how two callers drift
 * apart on validation and cache invalidation.
 */
import ImovelCertidoesCard from "@/components/imovel/ImovelCertidoesCard";
import ImovelContratoCard from "@/components/imovel/ImovelContratoCard";
import {
  useAntigosProprietarios,
  useConfirmarDescricaoImovel,
  useConfirmarDocumentoExtracao,
  useConfirmarEnderecoRegistro,
  useConfirmarOnusCredor,
  useConfirmarTitulo,
  useConfirmarUltimaTransferenciaManual,
  useDescricaoImovel,
  useEnderecoRegistro,
  useImovelCertidoes,
  useOnusCredor,
  useRemoverCertidaoManual,
  useSalvarCertidaoManual,
  useTituloAquisitivo,
} from "@/hooks/useImovelContrato";
import {
  codigoDoDocumento,
  useImovelDados,
  useImovelDocumentoMutations,
  useImovelDocumentos,
} from "@/hooks/useImovelDados";

export function ImovelContratoContainer({ codigo }: { codigo: string }) {
  const tituloQuery = useTituloAquisitivo(codigo);
  const enderecoRegistroQuery = useEnderecoRegistro(codigo);
  const onusQuery = useOnusCredor(codigo);
  const antigosQuery = useAntigosProprietarios(codigo);
  const certidoesQuery = useImovelCertidoes(codigo);
  const descricaoQuery = useDescricaoImovel(codigo);

  const confirmarTitulo = useConfirmarTitulo(codigo);
  const confirmarEnderecoRegistro = useConfirmarEnderecoRegistro(codigo);
  const confirmarOnus = useConfirmarOnusCredor(codigo);
  const confirmarUltimaTransferencia = useConfirmarUltimaTransferenciaManual(codigo);
  const confirmarExtracao = useConfirmarDocumentoExtracao(codigo);
  const confirmarDescricao = useConfirmarDescricaoImovel(codigo);
  const salvarCertidaoManual = useSalvarCertidaoManual(codigo);
  const removerCertidaoManual = useRemoverCertidaoManual(codigo);
  const documentoMutations = useImovelDocumentoMutations(codigo);
  // Shared cache entries with the page's own cards — no extra requests.
  const dadosQuery = useImovelDados(codigo);
  const documentosQuery = useImovelDocumentos(codigo);

  // 🔴 Two signals off `data`, never `isLoading`: it is false mid-refetch, so
  // a skeleton/empty branch keyed off it would lie over data still good to
  // look at — and `isFetching` alone would UNMOUNT the editors on every
  // confirmation's refetch. KB § PATTERNS/frontend/lying-loading-state.md
  return (
    <>
      <ImovelContratoCard
        codigo={codigo}
        vinculoLegal={dadosQuery.data?.vinculo_legal}
        titulo={tituloQuery.data}
        tituloShowSkeleton={tituloQuery.isPending && !tituloQuery.data}
        tituloIsRefreshing={tituloQuery.isFetching && !!tituloQuery.data}
        tituloIsError={tituloQuery.isError && !tituloQuery.data}
        savingTitulo={confirmarTitulo.isPending}
        onConfirmarTitulo={(texto) => confirmarTitulo.mutate(texto)}
        enderecoRegistro={enderecoRegistroQuery.data}
        enderecoRegistroShowSkeleton={enderecoRegistroQuery.isPending && !enderecoRegistroQuery.data}
        enderecoRegistroIsRefreshing={
          enderecoRegistroQuery.isFetching && !!enderecoRegistroQuery.data
        }
        enderecoRegistroIsError={enderecoRegistroQuery.isError && !enderecoRegistroQuery.data}
        savingEnderecoRegistro={confirmarEnderecoRegistro.isPending}
        onConfirmarEnderecoRegistro={(texto) => confirmarEnderecoRegistro.mutate(texto)}
        descricao={descricaoQuery.data}
        descricaoShowSkeleton={descricaoQuery.isPending && !descricaoQuery.data}
        descricaoIsRefreshing={descricaoQuery.isFetching && !!descricaoQuery.data}
        descricaoIsError={descricaoQuery.isError && !descricaoQuery.data}
        savingDescricao={confirmarDescricao.isPending}
        onConfirmarDescricao={(texto) => confirmarDescricao.mutate(texto)}
        onus={onusQuery.data}
        onusShowSkeleton={onusQuery.isPending && !onusQuery.data}
        onusIsRefreshing={onusQuery.isFetching && !!onusQuery.data}
        onusIsError={onusQuery.isError && !onusQuery.data}
        savingOnus={confirmarOnus.isPending}
        onConfirmarOnusCredor={(credor) => confirmarOnus.mutate(credor)}
        antigos={antigosQuery.data}
        antigosShowSkeleton={antigosQuery.isPending && !antigosQuery.data}
        antigosIsError={antigosQuery.isError && !antigosQuery.data}
        savingUltimaTransferenciaManual={confirmarUltimaTransferencia.isPending}
        onConfirmarUltimaTransferenciaManual={(input) =>
          confirmarUltimaTransferencia.mutate(input)
        }
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
        savingManualTipo={
          salvarCertidaoManual.isPending
            ? (salvarCertidaoManual.variables?.tipo ?? null)
            : removerCertidaoManual.isPending
              ? (removerCertidaoManual.variables?.tipo ?? null)
              : null
        }
        // An upload refusal is drawn by the card itself, with the file name.
        errorMessage={
          confirmarExtracao.error?.message ??
          salvarCertidaoManual.error?.message ??
          removerCertidaoManual.error?.message ??
          null
        }
        onSalvarManual={(tipo, valores) => salvarCertidaoManual.mutate({ tipo, valores })}
        onRemoverManual={(tipo) => removerCertidaoManual.mutate({ tipo })}
        onUpload={(file, tipoDocumento) =>
          documentoMutations.upload.mutateAsync({ file, tipoDocumento })
        }
        onConfirmar={(documentoId, _tipo, patch) => {
          // The certidão may belong to the linked manual record: the PATCH
          // path needs the document's OWN código.
          const doc = documentosQuery.data?.find((d) => d.id === documentoId);
          confirmarExtracao.mutate({
            documentoId,
            patch,
            codigo: doc ? codigoDoDocumento(doc, codigo) : codigo,
          });
        }}
      />
    </>
  );
}
