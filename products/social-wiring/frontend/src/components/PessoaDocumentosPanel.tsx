/**
 * `<PessoaDocumentosPanel/>` — one comprador's own checklist + documents.
 *
 * A CONTAINER, and it lives here rather than under `components/card/**` for
 * that reason: everything under `card/` is presentational (S3 per PROJECT.md
 * §0) and is rendered in tests with plain objects and no query client. This
 * file fetches; it renders the very same two sections the titular's panel
 * does.
 *
 * 🔴 WHY THIS FILE IS THIS SHORT
 * ------------------------------
 * Because a comprador IS a `clientes` row (migration 073), so their paperwork
 * is reached by exactly the same hooks as the titular's — same endpoints, same
 * checklist definition, same upload path — and rendered by exactly the same
 * two components. This is a second CALLER of that machinery, never a second
 * implementation of it.
 *
 * That is the schema decision made visible one layer up. Had a party been a
 * lightweight record with its own fields, this file would have needed its own
 * checklist component, its own upload flow and its own extraction prompts, and
 * every later fix to the titular's panel would have had to be repeated here —
 * or, far more likely, silently not applied.
 *
 * Mounted only while its section is EXPANDED (see
 * `ClienteCardDialog.PessoaDocumentosSection`), so a card with three parties
 * does not fire six queries for panels nobody has opened.
 *
 * The two sections it renders now live in their OWN files. They used to be
 * exported from `ClienteCardDialog.tsx`, which made the 1691-line dialog a
 * module barrel for components it did not own — an import cycle waiting to
 * happen the moment either side grew.
 */
import { toast } from "sonner";

import {
  useDocumentoChecklist,
  useDocumentoChecklistMutation,
  useDocumentoMutations,
  useDadosPessoaisMutation,
  useDocumentos,
  useExtracaoSugestaoMutation,
  useTiposDocumento,
} from "@/hooks/useCardHub";

import { AnexosSection } from "@/components/card/AnexosSection";
import { DocumentoChecklistSection } from "@/components/card/DocumentoChecklistSection";
import { DadosPessoaisForm } from "@/components/card/DadosPessoaisForm";

export interface PessoaDocumentosPanelProps {
  clienteId: string;
}

function erro(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export function PessoaDocumentosPanel({ clienteId }: PessoaDocumentosPanelProps) {
  const checklist = useDocumentoChecklist(clienteId);
  const documentos = useDocumentos(clienteId);
  const tipos = useTiposDocumento();

  const toggle = useDocumentoChecklistMutation(clienteId);
  const sugestao = useExtracaoSugestaoMutation(clienteId);
  const docs = useDocumentoMutations(clienteId);
  const dados = useDadosPessoaisMutation(clienteId);

  return (
    <>
      {/* Same form the titular gets, for the same reason the checklist is the
          same: a comprador's paperwork is collected exactly like anyone
          else's. Without it her items would be unfillable and her checklist
          permanently red. */}
      <DadosPessoaisForm
        testId={`dados-pessoais-${clienteId}`}
        valores={checklist.data?.valores ?? {}}
        saving={dados.isPending}
        onSave={(valores) =>
          dados.mutate(valores, {
            onError: (e) =>
              toast.error(erro(e, "Não foi possível salvar os dados.")),
          })
        }
      />
      <DocumentoChecklistSection
        // Scoped to THIS person. The titular's checklist is on the same screen
        // now (Geral absorbed the Documentos tab), so an unprefixed testid
        // would name two different people's rows identically.
        testIdPrefix={`documento-checklist-${clienteId}`}
        items={checklist.data?.items ?? []}
        // 🔴 `isPending || isFetching`, never `isLoading`. TanStack v5's
        // `isLoading` is false during a background refetch, so an empty branch
        // would render "nothing here" over data that exists.
        loading={checklist.isPending || checklist.isFetching}
        onToggle={(key, concluido) =>
          toggle.mutate(
            { key, concluido },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível salvar o item.")),
            },
          )
        }
        onResolverSugestao={(documentoId, acao, itemKey) =>
          sugestao.mutate({ documentoId, acao, itemKey })
        }
        sugestaoSaving={sugestao.isPending}
        sugestoesExtras={checklist.data?.sugestoes_extras}
        nomeOficial={checklist.data?.nome_oficial}
        nomeRegistro={checklist.data?.nome_registro}
        // The row's inline editors write through the SAME `PATCH /clientes/{id}`
        // mutation the form above uses — one write path for one set of columns.
        valores={checklist.data?.valores ?? {}}
        savingCampo={dados.isPending}
        onSaveCampo={(patch) =>
          dados.mutate(patch, {
            onError: (e) =>
              toast.error(erro(e, "Não foi possível salvar os dados.")),
          })
        }
        uploading={docs.upload.isPending}
        // A checklist row's file is filed under the ROW's key: the item IS the
        // document type, so `rg` uploads as `rg`. Handing it the catalogue's
        // first type (what the generic Anexos button does) would file every
        // identity document as whatever happens to sort first.
        onUploadDocumento={(item, file) =>
          docs.upload.mutate(
            { file, tipoDocumento: item.key },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível enviar o documento.")),
            },
          )
        }
        onRemoverDocumento={(documentoId, item) =>
          docs.remove.mutate(
            { documentoId, motivo: `Descartado para reenvio de ${item.label}` },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível descartar o documento.")),
            },
          )
        }
      />
      <AnexosSection
        testId={`anexos-section-${clienteId}`}
        documentos={documentos.data ?? []}
        loading={documentos.isPending || documentos.isFetching}
        uploading={docs.upload.isPending}
        onUpload={(file) =>
          docs.upload.mutate(
            {
              file,
              tipoDocumento: tipos.data?.[0]?.tipo_documento ?? "outro",
            },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível enviar o anexo.")),
            },
          )
        }
        onOpenDocumento={(documentoId) =>
          docs.getUrl.mutate(documentoId, {
            onSuccess: (res) =>
              window.open(res.url, "_blank", "noopener,noreferrer"),
            onError: (e) =>
              toast.error(erro(e, "Não foi possível abrir o anexo.")),
          })
        }
        onDeleteDocumento={(documentoId, motivo) =>
          docs.remove.mutate(
            { documentoId, motivo },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível remover o anexo.")),
            },
          )
        }
      />
    </>
  );
}
