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
 * 🔴 NOW A THIN WRAPPER over `DocumentoTipoSlot` (tech-lead decision H7, P0c
 * contract §F/§H7 — `project-history/roadmaps/
 * sw-drive-extraction-P0c-contract.md`): the Cartão CNPJ slot needed the
 * SAME shape (a named single-document upload slot), and duplicating this
 * component's markup for it would have been the recurrence rule's forbidden
 * second copy. `DocumentoTipoSlot` carries the generic behaviour;
 * everything below is this slot's own identity — the type, the label, and
 * the props/testids/DOM callers already depend on, all UNCHANGED.
 *
 * Presentational (`card/**`): reads the ONE `certidao_casamento` document off
 * the party's own `documentos` list — a PROP, not a fetch of its own; the
 * container (`PessoaDocumentosPanel` / `ClienteDetailModal`) already holds
 * that list for its Anexos section — and writes through the SAME
 * upload/open/download/delete callbacks Anexos uses.
 */
import type { Documento } from "@/types/cardHub";

import { DocumentoTipoSlot, documentoDoTipo } from "./DocumentoTipoSlot";

export const TIPO_CERTIDAO_CASAMENTO = "certidao_casamento";

/** The most recent non-deleted `certidao_casamento` in a party's `documentos`
 *  list — `documentos_service.list_documentos` already excludes soft-deleted
 *  rows, the same assumption every other Anexos-list reader in this product
 *  makes. Exported so a caller (or a test) can assert on it without
 *  duplicating the filter. */
export function certidaoCasamentoDe(documentos: Documento[]): Documento | undefined {
  return documentoDoTipo(documentos, TIPO_CERTIDAO_CASAMENTO);
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
  testId = "certidao-casamento",
  ...rest
}: CertidaoCasamentoSlotProps) {
  return (
    <DocumentoTipoSlot
      {...rest}
      tipoDocumento={TIPO_CERTIDAO_CASAMENTO}
      label="Certidão de casamento"
      testId={testId}
    />
  );
}
