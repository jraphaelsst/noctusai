/**
 * `<DocumentoTipoSlot/>` — a NAMED single-document upload slot for one
 * `tipo_documento`: a label, the current file (or "—"), an upload button
 * while empty, and view/download/discard once a file is on record.
 *
 * Generalized from `CertidaoCasamentoSlot` (tech-lead decision H7, P0c
 * contract — `project-history/roadmaps/sw-drive-extraction-P0c-contract.md`
 * §F/§H7) so the Cartão CNPJ slot (`EmpresasSection`) does not become a
 * second, near-identical copy of the marriage-certificate slot's markup —
 * the recurrence rule's N=2 triage, resolved by promoting the FIRST
 * instance into the shared shape rather than waiting for a third to force
 * the move. `CertidaoCasamentoSlot` is now a thin wrapper over this
 * component, unchanged in behaviour (props, testids, DOM shape) — see its
 * own docblock.
 *
 * Presentational (`card/**`): reads the ONE document of `tipoDocumento` off
 * a `documentos` PROP — never a fetch of its own — and writes through
 * caller-supplied callbacks, exactly like `CertidaoCasamentoSlot` always
 * did.
 */
import { useRef } from "react";
import { Download, ExternalLink, Trash2, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import { TooltipIconButton, formatBytes } from "@noctusai/lib/components";

/**
 * The narrowest shape this slot needs off a document row — deliberately NOT
 * `@/types/cardHub`'s `Documento` (which carries `categoria_lgpd`,
 * `retencao_ate`, `thumbnail_url`, `extracao_erro` this slot never reads).
 * `Documento` still satisfies this structurally, so every EXISTING caller
 * (`CertidaoCasamentoSlot`) keeps compiling unchanged; the P0c contract's
 * `EmpresaDocumento` (`@/types/empresas`, a narrower row with no LGPD
 * category of its own) satisfies it too — which is the whole point of the
 * generalization (H7): one slot, two unrelated document families, no
 * adapter object required at either call site.
 */
export interface DocumentoTipoSlotDocumento {
  id: string;
  nome_original: string;
  tamanho_bytes: number;
  tipo_documento: string;
}

/** The most recent non-deleted document of `tipoDocumento` in a `documentos`
 *  list — every list this component is handed (`documentos_service.
 *  list_documentos`, `empresa_documentos`) already excludes soft-deleted
 *  rows server-side, the same assumption every Anexos-list reader in this
 *  product makes. Exported so a caller (or a test) can assert on it without
 *  duplicating the filter. */
export function documentoDoTipo<T extends DocumentoTipoSlotDocumento>(
  documentos: T[],
  tipoDocumento: string,
): T | undefined {
  return documentos.find((d) => d.tipo_documento === tipoDocumento);
}

export interface DocumentoTipoSlotProps {
  documentos: DocumentoTipoSlotDocumento[];
  /** Which `tipo_documento` this slot files under — the row IS the type. */
  tipoDocumento: string;
  /** The pt-BR label this slot shows and speaks in every tooltip
   *  ("Enviar {label}", "Visualizar {label}", …). */
  label: string;
  onUpload: (file: File) => void;
  uploading?: boolean;
  onVisualizar?: (documentoId: string) => void;
  /** Absent where the caller has no distinct download-under-original-name
   *  round trip wired — the button simply does not render. */
  onBaixar?: (documentoId: string, nomeArquivo: string) => void;
  onRemover?: (documentoId: string, motivo: string) => void;
  /** Disambiguates testids when several such slots are on screen. */
  testId?: string;
}

export function DocumentoTipoSlot({
  documentos,
  tipoDocumento,
  label,
  onUpload,
  uploading,
  onVisualizar,
  onBaixar,
  onRemover,
  testId = "documento-tipo",
}: DocumentoTipoSlotProps) {
  const documento = documentoDoTipo(documentos, tipoDocumento);
  const inputArquivo = useRef<HTMLInputElement>(null);

  return (
    <div
      className="mb-3 flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-sm"
      data-testid={`${testId}-row`}
    >
      <span className="shrink-0 font-medium" data-testid={`${testId}-label`}>
        {label}
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
          label={`Enviar ${label}`}
          icon={Upload}
          testId={`${testId}-upload`}
          className="h-7 w-7"
          disabled={uploading}
          onClick={() => inputArquivo.current?.click()}
        />
      )}

      {documento && onVisualizar && (
        <TooltipIconButton
          label={`Visualizar ${label}`}
          icon={ExternalLink}
          testId={`${testId}-visualizar`}
          className="h-7 w-7"
          onClick={() => onVisualizar(documento.id)}
        />
      )}
      {documento && onBaixar && (
        <TooltipIconButton
          label={`Baixar ${label}`}
          icon={Download}
          testId={`${testId}-baixar`}
          className="h-7 w-7"
          onClick={() => onBaixar(documento.id, documento.nome_original)}
        />
      )}
      {documento && onRemover && (
        <TooltipIconButton
          label={`Descartar ${label}`}
          icon={Trash2}
          testId={`${testId}-descartar`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onRemover(documento.id, `Descartado para reenvio: ${label}`)}
        />
      )}
    </div>
  );
}
