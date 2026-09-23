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
  useConflitosPendentes,
  useDocumentoChecklist,
  useDocumentoChecklistMutation,
  useDocumentoMutations,
  useDadosPessoaisMutation,
  useDocumentos,
  useExtracaoPollingInvalidation,
  useExtracaoSugestaoMutation,
  useTiposDocumento,
} from "@/hooks/useCardHub";

import { AnexosSection } from "@/components/card/AnexosSection";
import { DocumentoChecklistSection } from "@/components/card/DocumentoChecklistSection";
import { DadosPessoaisForm } from "@/components/card/DadosPessoaisForm";
import { CasadoToggle } from "@/components/card/CasadoToggle";
import { CertidaoCasamentoSlot, TIPO_CERTIDAO_CASAMENTO } from "@/components/card/CertidaoCasamentoSlot";
import { baixarArquivo } from "@noctusai/lib/components";
import { ConflitosPendentesPanel } from "@/components/ConflitosPendentesPanel";
import { estadoCivilExigeConjuge, temArquivoCin } from "@/types/qualificacaoCompletude";

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
  // Bug 2 (prod card 755253934) — keeps THIS party's checklist/qualificação
  // from going stale once the server finishes extracting a document they
  // just uploaded. Side-effect only; see the hook's own docblock.
  useExtracaoPollingInvalidation(clienteId);

  const toggle = useDocumentoChecklistMutation(clienteId);
  const sugestao = useExtracaoSugestaoMutation(clienteId);
  const docs = useDocumentoMutations(clienteId);
  const dados = useDadosPessoaisMutation(clienteId);
  // Durable pending-state read (owner directive, 2026-09-19) —
  // `DadosPessoaisForm`'s notice must survive a reload, unlike the last
  // mutation's own transient response.
  const conflitosPendentes = useConflitosPendentes(clienteId);

  // 🔴 Gates the "Casado(a)" toggle + the certidão-de-casamento slot below.
  // Read off the SAME checklist response the values/rows below already use
  // — never a second fetch — so the gate can never disagree with the record
  // the rest of this panel is showing.
  const casado = estadoCivilExigeConjuge(checklist.data?.valores?.estado_civil);

  return (
    <>
      {/* Visible only while married — see `CasadoToggle`'s docblock for why
          turning it off writes `estado_civil`, not a second column. */}
      {casado && (
        <CasadoToggle
          testId={`casado-toggle-${clienteId}`}
          salvando={dados.isPending}
          onDesmarcar={() =>
            dados.mutate(
              { estado_civil: null },
              {
                onError: (e) =>
                  toast.error(erro(e, "Não foi possível salvar os dados.")),
              },
            )
          }
        />
      )}
      {/* Same form the titular gets, for the same reason the checklist is the
          same: a comprador's paperwork is collected exactly like anyone
          else's. Without it her items would be unfillable and her checklist
          permanently red. */}
      <DadosPessoaisForm
        testId={`dados-pessoais-${clienteId}`}
        valores={checklist.data?.valores ?? {}}
        saving={dados.isPending}
        // The RG==CPF 400 (migration 110) surfaced inline, same reasoning as
        // the titular's own form in `ClienteDetailModal`.
        saveError={dados.isError ? erro(dados.error, "Não foi possível salvar os dados.") : null}
        // Owner directive, 2026-09-19 — the DURABLE read, not the last
        // mutation's own transient response (see `conflitosPendentes` above).
        pendenteConfirmacao={conflitosPendentes.data
          ?.filter((c) => c.status === "pendente")
          .map((c) => c.campo)}
        temCin={temArquivoCin(checklist.data?.items)}
        onSave={(valores) =>
          dados.mutate(valores, {
            onError: (e) =>
              toast.error(erro(e, "Não foi possível salvar os dados.")),
          })
        }
      />
      <ConflitosPendentesPanel clienteId={clienteId} />
      <DocumentoChecklistSection
        // Scoped to THIS person. The titular's checklist is on the same screen
        // now (Geral absorbed the Documentos tab), so an unprefixed testid
        // would name two different people's rows identically.
        testIdPrefix={`documento-checklist-${clienteId}`}
        items={checklist.data?.items ?? []}
        // 🔴 Two signals, never `isLoading` (KB § lying-loading-state):
        // skeleton only while there is NO data yet; a background refetch over
        // rows that exist is the separate non-reserving `refreshing` spinner.
        loading={checklist.isPending && !checklist.data}
        refreshing={checklist.isFetching && !!checklist.data}
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
        // A checklist row's file is filed under the type the ROW names — the
        // identity item's slot (`cin` / `cnh`). Handing it the catalogue's
        // first type (what the generic Anexos button does) would file every
        // identity document as whatever happens to sort first.
        onUploadDocumento={(_item, file, tipoDocumento) =>
          docs.upload.mutate(
            { file, tipoDocumento },
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
        onVisualizarDocumento={(documentoId) =>
          docs.getUrl.mutate(
            { documentoId, intent: "view" },
            {
              onSuccess: (res) =>
                window.open(res.url, "_blank", "noopener,noreferrer"),
              onError: (e) =>
                toast.error(erro(e, "Não foi possível abrir o documento.")),
            },
          )
        }
        onBaixarDocumento={(documentoId, nomeArquivo) =>
          docs.getUrl.mutate(
            { documentoId, intent: "download" },
            {
              onSuccess: (res) => void baixarArquivo(res.url, nomeArquivo),
              onError: (e) =>
                toast.error(erro(e, "Não foi possível baixar o documento.")),
            },
          )
        }
      />
      {/* Visible only while married, same gate as the toggle above — see the
          file docblock on `CertidaoCasamentoSlot` for why this exists at
          all. Reads `documentos` off the SAME list Anexos below renders,
          never a second fetch. */}
      {casado && (
        <CertidaoCasamentoSlot
          testId={`certidao-casamento-${clienteId}`}
          documentos={documentos.data ?? []}
          uploading={docs.upload.isPending}
          onUpload={(file) =>
            docs.upload.mutate(
              { file, tipoDocumento: TIPO_CERTIDAO_CASAMENTO },
              {
                onError: (e) =>
                  toast.error(erro(e, "Não foi possível enviar a certidão de casamento.")),
              },
            )
          }
          onVisualizar={(documentoId) =>
            docs.getUrl.mutate(
              { documentoId, intent: "view" },
              {
                onSuccess: (res) =>
                  window.open(res.url, "_blank", "noopener,noreferrer"),
                onError: (e) =>
                  toast.error(erro(e, "Não foi possível abrir a certidão de casamento.")),
              },
            )
          }
          onBaixar={(documentoId, nomeArquivo) =>
            docs.getUrl.mutate(
              { documentoId, intent: "download" },
              {
                onSuccess: (res) => void baixarArquivo(res.url, nomeArquivo),
                onError: (e) =>
                  toast.error(erro(e, "Não foi possível baixar a certidão de casamento.")),
              },
            )
          }
          onRemover={(documentoId, motivo) =>
            docs.remove.mutate(
              { documentoId, motivo },
              {
                onError: (e) =>
                  toast.error(erro(e, "Não foi possível descartar a certidão de casamento.")),
              },
            )
          }
        />
      )}
      <AnexosSection
        testId={`anexos-section-${clienteId}`}
        documentos={documentos.data ?? []}
        tipos={tipos.data ?? []}
        loading={documentos.isPending && !documentos.data}
        refreshing={documentos.isFetching && !!documentos.data}
        uploading={docs.upload.isPending}
        // The operator's OWN pick from the section's own `<Select>` — see
        // `AnexosSection`'s module docblock for why the tipo no longer
        // travels as a caller-supplied default (`tipos.data?.[0] ?? "outro"`).
        onUpload={(file, tipoDocumento) =>
          docs.upload.mutate(
            { file, tipoDocumento },
            {
              onError: (e) =>
                toast.error(erro(e, "Não foi possível enviar o anexo.")),
            },
          )
        }
        onOpenDocumento={(documentoId) =>
          docs.getUrl.mutate(
            { documentoId, intent: "view" },
            {
              onSuccess: (res) =>
                window.open(res.url, "_blank", "noopener,noreferrer"),
              onError: (e) =>
                toast.error(erro(e, "Não foi possível abrir o anexo.")),
            },
          )
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
        // Gap 3/4 — re-queues a document stuck in `erro` (or never queued
        // at all) without deleting and re-uploading it.
        onReextrairDocumento={(documentoId) =>
          docs.reextrair.mutate(documentoId, {
            onError: (e) =>
              toast.error(erro(e, "Não foi possível reenviar o documento para leitura.")),
          })
        }
        reextraindoDocumentoId={docs.reextrair.isPending ? (docs.reextrair.variables ?? null) : null}
      />
    </>
  );
}
