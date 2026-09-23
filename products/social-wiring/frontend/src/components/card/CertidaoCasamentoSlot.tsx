/**
 * `<CertidaoCasamentoSlot/>` — the marriage certificate's own first-class
 * upload slot, wired exactly like the mandatory checklist's RG/CPF rows: the
 * upload is filed under the `certidao_casamento` `tipo_documento`, so
 * `identidade_extracao_service` runs (that type has read extraction since
 * migration 103) instead of sitting unread under a generic pick.
 *
 * 🔴 WHY THIS EXISTS
 * ------------------
 * Three real certidões de casamento sat on prod cards typed `outro` and were
 * NEVER read, because there was nowhere on the card that said what a
 * marriage certificate WAS — an operator uploading through the generic
 * Anexos `<Select>` had to already know the exact type name to pick it
 * correctly, and evidently did not. This is that place: a NAMED slot, gated
 * by the party's own marriage state (`estadoCivilExigeConjuge` — see
 * `CasadoToggle`), so it is never shown to a single person either. An empty
 * slot nobody can fill answers a question nobody asked.
 *
 * Presentational (`card/**`): reads the ONE `certidao_casamento` document off
 * the party's own `documentos` list — a PROP, not a fetch of its own; the
 * container (`PessoaDocumentosPanel` / `ClienteDetailModal`) already holds
 * that list for its Anexos section — and writes through the SAME
 * upload/open/download/delete callbacks Anexos uses.
 */
import { useRef } from "react";
import { Download, ExternalLink, Trash2, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Documento } from "@/types/cardHub";
import { TooltipIconButton, formatBytes } from "@noctusai/lib/components";

export const TIPO_CERTIDAO_CASAMENTO = "certidao_casamento";

/** The most recent non-deleted `certidao_casamento` in a party's `documentos`
 *  list — `documentos_service.list_documentos` already excludes soft-deleted
 *  rows, the same assumption every other Anexos-list reader in this product
 *  makes. Exported so a caller (or a test) can assert on it without
 *  duplicating the filter. */
export function certidaoCasamentoDe(documentos: Documento[]): Documento | undefined {
  return documentos.find((d) => d.tipo_documento === TIPO_CERTIDAO_CASAMENTO);
}

export interface CertidaoCasamentoSlotProps {
  documentos: Documento[];
  onUpload: (file: File) => void;
  uploading?: boolean;
  onVisualizar?: (documentoId: string) => void;
  /** Absent where the caller has no distinct download-under-original-name
   *  round trip wired (the titular's generic Anexos props only expose
   *  "open") — the button simply does not render, same shape
   *  `ChecklistItemRow` already uses for its own optional callbacks. */
  onBaixar?: (documentoId: string, nomeArquivo: string) => void;
  onRemover?: (documentoId: string, motivo: string) => void;
  /** Disambiguates testids when several people's slots are on screen. */
  testId?: string;
}

export function CertidaoCasamentoSlot({
  documentos,
  onUpload,
  uploading,
  onVisualizar,
  onBaixar,
  onRemover,
  testId = "certidao-casamento",
}: CertidaoCasamentoSlotProps) {
  const documento = certidaoCasamentoDe(documentos);
  const inputArquivo = useRef<HTMLInputElement>(null);

  return (
    <div
      className="mb-3 flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-sm"
      data-testid={`${testId}-row`}
    >
      <span className="shrink-0 font-medium" data-testid={`${testId}-label`}>
        Certidão de casamento
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-muted-foreground/90",
          !documento && "text-muted-foreground",
        )}
        data-testid={`${testId}-valor`}
      >
        {documento
          ? `${documento.nome_original} · ${formatBytes(documento.tamanho_bytes)}`
          : "—"}
      </span>

      <input
        ref={inputArquivo}
        type="file"
        className="hidden"
        data-testid={`${testId}-arquivo-input`}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
          // Cleared so re-picking the SAME file fires `change` again.
          e.target.value = "";
        }}
      />
      {/* Only while the slot is still ASKING — once it holds a file the
          answer is in, mirroring `ChecklistItemRow`'s RG/CPF rows. */}
      {!documento && (
        <TooltipIconButton
          label="Enviar certidão de casamento"
          icon={Upload}
          testId={`${testId}-upload`}
          className="h-7 w-7"
          disabled={uploading}
          onClick={() => inputArquivo.current?.click()}
        />
      )}

      {documento && onVisualizar && (
        <TooltipIconButton
          label="Visualizar certidão de casamento"
          icon={ExternalLink}
          testId={`${testId}-visualizar`}
          className="h-7 w-7"
          onClick={() => onVisualizar(documento.id)}
        />
      )}
      {documento && onBaixar && (
        <TooltipIconButton
          label="Baixar certidão de casamento"
          icon={Download}
          testId={`${testId}-baixar`}
          className="h-7 w-7"
          onClick={() => onBaixar(documento.id, documento.nome_original)}
        />
      )}
      {documento && onRemover && (
        <TooltipIconButton
          label="Descartar a certidão de casamento"
          icon={Trash2}
          testId={`${testId}-descartar`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() =>
            onRemover(documento.id, "Descartado para reenvio da certidão de casamento")
          }
        />
      )}
    </div>
  );
}
