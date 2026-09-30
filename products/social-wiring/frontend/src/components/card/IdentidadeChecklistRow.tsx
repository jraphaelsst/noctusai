/**
 * IdentidadeChecklistRow — the ONE "Documento de identidade" item.
 *
 * [Owner directive, 2026-09-23] one checklist item for RG + CPF, with upload
 * fields per document, only one of which needs to be filled when the data
 * can be read off it.
 *
 * [Owner directive, 2026-09-30] "Also separate the rg cpf cin cnh upload. I
 * want “rg/cpf” in one item, then cnh, then cin. Data comes from whichever is
 * uploaded and not all need to be uploaded, as long as data is complete".
 *
 * So this row carries THREE upload slots (RG/CPF, CNH, CIN — in that order,
 * sent by the server) under one tick, plus a hint that one is enough. The
 * tick is DERIVED server-side (`documento_checklist_service`): it follows the
 * identity DATA the contract needs (nome oficial, RG, órgão expedidor, CPF)
 * — read off whichever document was uploaded, or typed — never the files.
 * While data is missing the row lists WHICH fields, so the operator knows
 * whether another document is needed; a field whose reading is already
 * waiting for confirmation says so (confirm it below instead). An RG read
 * only off a CNH (which omits the check digit) arrives as a missing field
 * with its own explanatory label.
 *
 * Legacy files already filed as `cpf` are listed read-only — view, download,
 * discard — and are never offered as an upload target.
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
  const faltando = item.faltando ?? [];
  const rotulos = item.faltando_rotulos ?? [];
  const comSugestao = new Set(item.faltando_com_sugestao ?? []);
  // Fields no pending reading will fill — only these need another document
  // (or a typed value).
  const semLeitura = faltando.filter((campo) => !comSugestao.has(campo));

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
      {faltando.length > 0 ? (
        <div className="ml-6 text-xs text-amber-700" data-testid={`${tid}-faltando`}>
          <p>Falta:</p>
          <ul className="ml-3 list-disc">
            {faltando.map((campo, i) => (
              <li key={campo} data-testid={`${tid}-faltando-${campo}`}>
                {rotulos[i] ?? campo}
                {comSugestao.has(campo) && (
                  <span data-testid={`${tid}-faltando-${campo}-sugestao`}>
                    {" "}— há uma leitura aguardando confirmação abaixo
                  </span>
                )}
              </li>
            ))}
          </ul>
          {semLeitura.length > 0 && (
            <p data-testid={`${tid}-faltando-acao`}>
              Envie outro documento (RG/CPF, CNH ou CIN) que traga{" "}
              {semLeitura.length === 1 ? "esse dado" : "esses dados"}, ou informe em
              &ldquo;Dados pessoais&rdquo;.
            </p>
          )}
        </div>
      ) : (
        item.derivado && (
          <p className="ml-6 text-xs text-muted-foreground" data-testid={`${tid}-completo`}>
            Dados de identidade completos.
          </p>
        )
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
