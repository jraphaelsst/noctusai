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
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef } from "react";
import { ExternalLink, FileText, Trash2, Upload } from "lucide-react";

import { formatDate } from "@/lib/utils";
import type { Documento } from "@/types/cardHub";

import { TooltipIconButton } from "./TooltipIconButton";
import { formatBytes } from "./format";

export interface AnexosSectionProps {
  documentos: Documento[];
  loading: boolean;
  uploading?: boolean;
  onUpload: (file: File) => void;
  onOpenDocumento: (id: string) => void;
  onDeleteDocumento: (id: string, motivo: string) => void;
  testId?: string;
}

export function AnexosSection({
  documentos,
  loading,
  uploading,
  onUpload,
  onOpenDocumento,
  onDeleteDocumento,
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

  return (
    <div className="mb-4" data-testid={testId}>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
          // Cleared so re-picking the SAME file fires `change` again.
          e.target.value = "";
        }}
      />
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Anexos</p>
        {/* The section owns its trigger AND its input. Icon-only now, with the
            words it used to show carried by the tooltip AND by `aria-label` —
            a hover caption alone is invisible to a screen reader. */}
        <TooltipIconButton
          label={uploading ? "Enviando anexo…" : "Enviar anexo"}
          icon={Upload}
          testId="anexo-enviar-btn"
          className="h-7 w-7"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        />
      </div>
      {loading ? (
        <div className="h-10 animate-pulse rounded bg-muted" />
      ) : documentos.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="anexos-empty">
          Nenhum anexo ainda.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {documentos.map((doc) => (
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
              </div>
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
          ))}
        </ul>
      )}
    </div>
  );
}
