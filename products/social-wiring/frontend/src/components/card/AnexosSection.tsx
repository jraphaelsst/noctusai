/**
 * AnexosSection — the files attached to one person, as files.
 *
 * Lifted out of `ClienteCardDialog.tsx` alongside the checklist section it
 * sits under: both were already imported from `PessoaDocumentosPanel`, so the
 * dialog was acting as a module barrel for components it did not own, on top
 * of being 1691 lines.
 *
 * Distinct from the checklist rows ABOVE it, and the distinction is the point:
 * a checklist row asks for a SPECIFIC document (the RG, the CPF) and shows
 * whether it arrived; this list is every file on the record, managed as a
 * document — opened, downloaded, removed with a reason.
 *
 * 🔴 THE TIPO PICKER LIVES HERE, NOT AT EACH CALLER.
 * ----------------------------------------------------
 * Every caller used to hand this section's `onUpload` a HARDCODED tipo —
 * `tiposDocumento[0]?.tipo_documento ?? "outro"` — which files whatever
 * happens to sort first in the catalogue, or the literal fallback, onto
 * every generic attachment. On a real card this filed four identity
 * documents (certidões de casamento) as `outro`, and `outro` is never
 * `deve_extrair`-eligible: they were never queued for extraction, silently,
 * and every downstream field they would have filled stayed blank. Requiring
 * the operator to pick a real type HERE — once, in the one place every
 * caller shares — makes that mis-file unspellable instead of merely fixed at
 * today's caller.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef, useState } from "react";
import { AlertTriangle, ExternalLink, FileText, Loader2, RotateCw, Trash2, Upload } from "lucide-react";

import { formatDate } from "@/lib/utils";
import type { Documento, TipoDocumento } from "@/types/cardHub";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { TooltipIconButton } from "./TooltipIconButton";
import { formatBytes } from "./format";

//: Mirrors `documentos_service.ALLOWED_MIME_TYPES` (backend). A rejected
//: upload still gets the server's typed 400 naming the real limit — this
//: filter only keeps an obviously-wrong file from being the first feedback
//: an operator sees, same convention `FinanciamentoPanel.tsx` already uses.
const ACCEPT_DOCUMENTO = "application/pdf,image/jpeg,image/png,image/webp";

//: Extraction states worth a badge. `null`/`"ok"`/`"sem_dados"` render
//: nothing — the common case stays visually quiet.
function extracaoRotulo(status: string | null): { texto: string; tom: "lendo" | "erro" } | null {
  if (status === "pendente" || status === "processando") {
    return { texto: "Lendo…", tom: "lendo" };
  }
  if (status === "erro") {
    return { texto: "Falha na leitura", tom: "erro" };
  }
  return null;
}

export interface AnexosSectionProps {
  documentos: Documento[];
  /** The active catalogue (`GET .../documentos/tipos`) — what the picker
   *  offers. Empty is a legal, if useless, state: the upload trigger stays
   *  disabled until there is something to choose. */
  tipos?: TipoDocumento[];
  /** No `documentos` yet — the FIRST load only. Ignored once the list is
   *  non-empty, so a stale `true` mid-refetch can never blank real rows
   *  (same rule as `DocumentoChecklistSection`). */
  loading: boolean;
  /** A fetch is in flight AND `documentos` already has rows — a small,
   *  non-reserving spinner beside the heading. Never unmounts the list. */
  refreshing?: boolean;
  uploading?: boolean;
  /** `tipoDocumento` is the operator's OWN pick from this section's own
   *  `<Select>` — never a caller-supplied default. */
  onUpload: (file: File, tipoDocumento: string) => void;
  onOpenDocumento: (id: string) => void;
  onDeleteDocumento: (id: string, motivo: string) => void;
  /** Re-queues a stuck/never-run extraction (`POST .../extrair`). Optional:
   *  a caller that has not wired the mutation yet simply gets no retry
   *  affordance, never a crash. */
  onReextrairDocumento?: (id: string) => void;
  /** The document currently being re-queued — disables ONLY that row's
   *  retry button, never the whole list. */
  reextraindoDocumentoId?: string | null;
  testId?: string;
}

export function AnexosSection({
  documentos,
  tipos = [],
  loading,
  refreshing,
  uploading,
  onUpload,
  onOpenDocumento,
  onDeleteDocumento,
  onReextrairDocumento,
  reextraindoDocumentoId,
  testId = "anexos-section",
}: AnexosSectionProps) {
  // 🔴 Its OWN input, held by a ref — NOT the shared
  // `getElementById("card-anexo-file-input")` this used to reach for.
  //
  // That worked only while exactly one Anexos section was mounted. Compradores
  // (migration 073) put one per PERSON on the card, and every "Enviar anexo"
  // button would have opened the same input and uploaded to the titular — a
  // spouse's RG silently filed onto her husband's record, which is a data
  // error and an LGPD one at once.
  //
  // A ref cannot address the wrong element, so the bug becomes unspellable
  // rather than merely fixed. The checklist rows follow the same rule for the
  // same reason.
  const inputRef = useRef<HTMLInputElement>(null);
  // No tipo pre-selected, ever — see the module docblock. A silent default
  // (the catalogue's first entry, `outro`) is exactly the bug this section
  // exists to make unspellable.
  const [tipoEscolhido, setTipoEscolhido] = useState<string>("");

  const tiposIdentidade = tipos.filter((t) => t.identidade);
  const tiposComuns = tipos.filter((t) => !t.identidade);
  const podeEnviar = !!tipoEscolhido && !uploading;

  return (
    <div className="mb-4" data-testid={testId}>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_DOCUMENTO}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file && tipoEscolhido) {
            onUpload(file, tipoEscolhido);
            // Reset — the NEXT attachment gets its own deliberate pick
            // rather than silently reusing this one's type.
            setTipoEscolhido("");
          }
          // Cleared so re-picking the SAME file fires `change` again.
          e.target.value = "";
        }}
      />
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Anexos</p>
          {refreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="anexos-refreshing"
            />
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Select value={tipoEscolhido} onValueChange={setTipoEscolhido}>
            <SelectTrigger
              className="h-7 w-44 text-xs"
              data-testid="anexo-tipo-select"
              aria-label="Tipo do documento"
            >
              <SelectValue placeholder="Tipo do documento" />
            </SelectTrigger>
            <SelectContent>
              {tiposIdentidade.length > 0 && (
                <div className="px-2 py-1 text-[10px] font-semibold uppercase text-muted-foreground">
                  Identidade
                </div>
              )}
              {tiposIdentidade.map((t) => (
                <SelectItem key={t.tipo_documento} value={t.tipo_documento}>
                  {t.descricao ?? t.tipo_documento}
                </SelectItem>
              ))}
              {tiposComuns.length > 0 && (
                <div className="px-2 py-1 text-[10px] font-semibold uppercase text-muted-foreground">
                  Outros
                </div>
              )}
              {tiposComuns.map((t) => (
                <SelectItem key={t.tipo_documento} value={t.tipo_documento}>
                  {t.descricao ?? t.tipo_documento}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* The section owns its trigger AND its input. Icon-only now, with
              the words it used to show carried by the tooltip AND by
              `aria-label` — a hover caption alone is invisible to a screen
              reader. Disabled until a tipo is chosen — never a silent
              default. */}
          <TooltipIconButton
            label={
              uploading
                ? "Enviando anexo…"
                : tipoEscolhido
                  ? "Enviar anexo"
                  : "Escolha o tipo do documento antes de enviar"
            }
            icon={Upload}
            testId="anexo-enviar-btn"
            className="h-7 w-7"
            disabled={!podeEnviar}
            onClick={() => inputRef.current?.click()}
          />
        </div>
      </div>
      {/* `documentos.length === 0` guards the skeleton the same way the
          checklist above does: a stale `loading=true` mid-refetch can never
          replace rows that are already here. */}
      {loading && documentos.length === 0 ? (
        <div className="h-10 animate-pulse rounded bg-muted" />
      ) : documentos.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="anexos-empty">
          Nenhum anexo ainda.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {documentos.map((doc) => {
            const rotulo = extracaoRotulo(doc.extracao_status);
            const reextraindo = reextraindoDocumentoId === doc.id;
            return (
            <li
              key={doc.id}
              className="flex items-center gap-2 rounded border p-2 text-sm"
              data-testid={`anexo-item-${doc.id}`}
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{doc.nome_original}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(doc.tamanho_bytes)} · {formatDate(doc.created_at, true)}
                </p>
                {/* Gap 4 — before this, `extracao_status === "erro"` showed
                    NOWHERE on the card: a document could sit permanently
                    unread (an OpenAI 429, a corrupt PDF) and look identical
                    to one that was simply never meant to be extracted. */}
                {rotulo && (
                  <p
                    className={
                      "mt-0.5 flex min-w-0 items-center gap-1 text-xs " +
                      (rotulo.tom === "erro" ? "text-destructive" : "text-muted-foreground")
                    }
                    data-testid={`anexo-extracao-status-${doc.id}`}
                    title={rotulo.tom === "erro" ? doc.extracao_erro ?? undefined : undefined}
                  >
                    {rotulo.tom === "erro" ? (
                      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                    ) : (
                      <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden="true" />
                    )}
                    <span className="shrink-0">{rotulo.texto}</span>
                    {/* An extraction error (e.g. a raw OpenAI 400 body) can run
                        hundreds of characters. `min-w-0` is load-bearing here:
                        without it a flex child ignores `truncate`'s ellipsis
                        and keeps its full one-line width, pushing the whole
                        card into a horizontal scrollbar and shoving every
                        field to its right off-screen. The full text stays
                        reachable via the `<p>`'s own `title` above. */}
                    {rotulo.tom === "erro" && doc.extracao_erro && (
                      <span className="min-w-0 flex-1 truncate italic">
                        — {doc.extracao_erro}
                      </span>
                    )}
                  </p>
                )}
              </div>
              {rotulo?.tom === "erro" && onReextrairDocumento && (
                <TooltipIconButton
                  label="Tentar ler o documento novamente"
                  icon={RotateCw}
                  testId={`anexo-reextrair-${doc.id}`}
                  disabled={reextraindo}
                  iconClassName={reextraindo ? "animate-spin" : undefined}
                  onClick={() => onReextrairDocumento(doc.id)}
                />
              )}
              <TooltipIconButton
                label={`Abrir ${doc.nome_original}`}
                icon={ExternalLink}
                testId={`anexo-abrir-${doc.id}`}
                onClick={() => onOpenDocumento(doc.id)}
              />
              <TooltipIconButton
                label={`Remover ${doc.nome_original}`}
                icon={Trash2}
                testId={`anexo-remover-${doc.id}`}
                className="text-muted-foreground hover:text-destructive"
                onClick={() => onDeleteDocumento(doc.id, "Removido pelo usuário")}
              />
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
