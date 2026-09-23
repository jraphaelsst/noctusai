/**
 * IdentidadeChecklistRow — the ONE "Documento de identidade (RG e CPF)" item.
 *
 * [Owner directive, 2026-09-23] "make rg/cpf 1 single checklist item. then i
 * need the CIN field and the CNH field. only one of those fields need to be
 * filled, if they are able to extract rg and cpf from it, otherwise the
 * mechanism shall block generation missing one of those fields (rg/cpf)."
 *
 * So this row carries TWO upload slots (CIN, CNH) under one tick, plus a hint
 * that only one is needed. The tick is still DERIVED server-side
 * (`documento_checklist_service`): it follows the RG and CPF numbers on the
 * record — read off the document and confirmed, or typed — never the file
 * alone. While either number is missing the row names which, because that is
 * exactly what the contract gate will refuse over.
 *
 * A CIN is never extracted (no real one exists yet): after uploading it, the
 * operator types its RG and CPF in "Dados pessoais". A CIN's RG equals its CPF
 * by design — nothing here compares the two.
 *
 * Legacy files already filed as `rg`/`cpf` (a CNH filed as `rg` before the
 * `cnh` type existed) are listed read-only — view, download, discard — and
 * are never offered as an upload target.
 *
 * Same override semantics as `ChecklistItemRow`: the checkbox is a human
 * override, the `manual` badge + ↩ say so and withdraw it.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef } from "react";
import { Download, ExternalLink, FileText, Trash2, Undo2, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DocumentoChecklistItem, IdentidadeSlot } from "@/types/cardHub";

import { TokenCheckbox, TooltipIconButton, formatBytes } from "@noctusai/lib/components";

export interface IdentidadeChecklistRowProps {
  item: DocumentoChecklistItem;
  onToggle: (key: string, concluido: boolean | null) => void;
  /** Files the upload under the SLOT's type (`cin` / `cnh`), never the item key. */
  onUploadDocumento?: (item: DocumentoChecklistItem, file: File, tipoDocumento: string) => void;
  onRemoverDocumento?: (documentoId: string, item: DocumentoChecklistItem) => void;
  uploading?: boolean;
  onVisualizarDocumento?: (documentoId: string) => void;
  onBaixarDocumento?: (documentoId: string, nomeArquivo: string) => void;
  testIdPrefix?: string;
}

export function IdentidadeChecklistRow({
  item,
  onToggle,
  onUploadDocumento,
  onRemoverDocumento,
  uploading,
  onVisualizarDocumento,
  onBaixarDocumento,
  testIdPrefix = "documento-checklist",
}: IdentidadeChecklistRowProps) {
  const tid = `${testIdPrefix}-${item.key}`;
  const slots = item.documentos ?? [];
  const faltando = item.faltando_rotulos ?? [];

  return (
    <li
      className="rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-sm"
      data-testid={`${tid}-row`}
    >
      <div className="flex items-center gap-2">
        <TokenCheckbox
          checked={item.concluido}
          onCheckedChange={(c) => onToggle(item.key, c)}
          label={item.label}
          testId={tid}
        />
        <span
          className={cn(
            "min-w-0 flex-1 font-medium",
            item.concluido && "text-muted-foreground line-through",
          )}
          data-testid={`${tid}-label`}
        >
          {item.label}
        </span>
        {item.origem === "manual" && (
          <>
            <span
              className="shrink-0 rounded bg-muted px-1 text-[10px] uppercase tracking-wide text-muted-foreground"
              title={
                item.derivado === item.concluido
                  ? "Marcado manualmente"
                  : `Marcado manualmente — os dados indicam "${
                      item.derivado ? "preenchido" : "pendente"
                    }"`
              }
              data-testid={`${tid}-manual`}
            >
              manual
            </span>
            <TooltipIconButton
              label={`Voltar ${item.label} a seguir os dados`}
              icon={Undo2}
              testId={`${tid}-limpar`}
              className="h-7 w-7"
              onClick={() => onToggle(item.key, null)}
            />
          </>
        )}
      </div>

      {item.dica && (
        <p className="ml-6 text-xs text-muted-foreground" data-testid={`${tid}-dica`}>
          {item.dica}
        </p>
      )}
      {faltando.length > 0 && (
        <p className="ml-6 text-xs text-amber-700" data-testid={`${tid}-faltando`}>
          Falta: {faltando.join(" e ")}
          {" — "}envie a CIN ou a CNH, ou informe em &ldquo;Dados pessoais&rdquo;.
        </p>
      )}

      <ul className="ml-6 mt-1 space-y-1">
        {slots.map((slot) => (
          <IdentidadeSlotLinha
            key={slot.tipo_documento}
            item={item}
            slot={slot}
            onUploadDocumento={onUploadDocumento}
            onRemoverDocumento={onRemoverDocumento}
            uploading={uploading}
            onVisualizarDocumento={onVisualizarDocumento}
            onBaixarDocumento={onBaixarDocumento}
            tid={`${tid}-${slot.tipo_documento}`}
          />
        ))}
      </ul>
    </li>
  );
}

function IdentidadeSlotLinha({
  item,
  slot,
  onUploadDocumento,
  onRemoverDocumento,
  uploading,
  onVisualizarDocumento,
  onBaixarDocumento,
  tid,
}: {
  item: DocumentoChecklistItem;
  slot: IdentidadeSlot;
  onUploadDocumento?: IdentidadeChecklistRowProps["onUploadDocumento"];
  onRemoverDocumento?: IdentidadeChecklistRowProps["onRemoverDocumento"];
  uploading?: boolean;
  onVisualizarDocumento?: (documentoId: string) => void;
  onBaixarDocumento?: (documentoId: string, nomeArquivo: string) => void;
  tid: string;
}) {
  // 🔴 Its OWN input, held by a ref — several parties' rows are on screen at
  // once, and a shared input would file one person's CNH onto another.
  const inputArquivo = useRef<HTMLInputElement>(null);
  const doc = slot.documento;

  return (
    <li className="flex items-center gap-2" data-testid={`${tid}-slot`}>
      <span className="w-32 shrink-0 text-xs font-medium text-muted-foreground">
        {slot.rotulo}
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-xs",
          doc ? "text-muted-foreground/90" : "text-muted-foreground",
        )}
        data-testid={`${tid}-valor`}
      >
        {doc ? (
          <>
            <FileText className="mr-1 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
            {doc.nome_original} · {formatBytes(doc.tamanho_bytes)}
          </>
        ) : (
          "—"
        )}
      </span>

      {slot.upload && onUploadDocumento && (
        <>
          <input
            ref={inputArquivo}
            type="file"
            className="hidden"
            data-testid={`${tid}-arquivo-input`}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUploadDocumento(item, file, slot.tipo_documento);
              e.target.value = "";
            }}
          />
          {/* Only while the slot is empty — replacing a file is the deliberate
              discard-then-upload two-step, same as `ChecklistItemRow`. */}
          {!doc && (
            <TooltipIconButton
              label={`Enviar ${slot.rotulo}`}
              icon={Upload}
              testId={`${tid}-upload`}
              className="h-7 w-7"
              disabled={uploading}
              onClick={() => inputArquivo.current?.click()}
            />
          )}
        </>
      )}
      {doc && onVisualizarDocumento && (
        <TooltipIconButton
          label={`Visualizar ${slot.rotulo}`}
          icon={ExternalLink}
          testId={`${tid}-visualizar`}
          className="h-7 w-7"
          onClick={() => onVisualizarDocumento(doc.id)}
        />
      )}
      {doc && onBaixarDocumento && (
        <TooltipIconButton
          label={`Baixar ${slot.rotulo}`}
          icon={Download}
          testId={`${tid}-baixar`}
          className="h-7 w-7"
          onClick={() => onBaixarDocumento(doc.id, doc.nome_original)}
        />
      )}
      {doc && onRemoverDocumento && (
        <TooltipIconButton
          label={`Descartar o arquivo de ${slot.rotulo}`}
          icon={Trash2}
          testId={`${tid}-descartar-arquivo`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onRemoverDocumento(doc.id, item)}
        />
      )}
    </li>
  );
}
