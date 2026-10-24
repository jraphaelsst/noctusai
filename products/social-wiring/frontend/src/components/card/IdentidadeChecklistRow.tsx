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
 * discard, re-read — and are never offered as an upload target.
 *
 * 🔴 THE VALUES ARE SHOWN, NOT ONLY THE FILES (owner e2e 2026-09-21). The
 * old `cpf` row rendered only its FILE, so a CPF typed (or read off another
 * document) showed "—" beside a ticked box — the tick said "we have it", the
 * row said "we don't". The identity item keeps that lesson: the CPF, RG and
 * órgão expedidor on record (`valores`, keyed by column) are listed on the
 * row; the slots below list the files.
 *
 * Every filed slot carries "Ler o documento novamente" — the same re-read
 * the Anexos rows offer (`reextrair_documento_route`), so a checklist file is
 * never a dead end when its reading failed or the readers improved.
 *
 * Same override semantics as `ChecklistItemRow`: the checkbox is a human
 * override, the `manual` badge + ↩ say so and withdraw it.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef, useState } from "react";
import {
  Check,
  Download,
  ExternalLink,
  FileText,
  Pencil,
  RotateCw,
  Trash2,
  Undo2,
  Upload,
  X,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { DocumentoChecklistItem, IdentidadeSlot } from "@/types/cardHub";

import type { DadosPessoais } from "./DadosPessoaisForm";

import { TokenCheckbox, TooltipIconButton, UploadErro, formatBytes } from "@noctusai/lib/components";
import { useUploadDocumento } from "@noctusai/lib/upload-refusal";

export interface IdentidadeChecklistRowProps {
  item: DocumentoChecklistItem;
  onToggle: (key: string, concluido: boolean | null) => void;
  /** Files the upload under the SLOT's type (`cin` / `cnh`), never the item key.
   *  Returns the upload's promise: a refusal is drawn under the slot
   *  (`<UploadErro>`). KB § PATTERNS/frontend/silent-refusal.md. */
  onUploadDocumento?: (item: DocumentoChecklistItem, file: File, tipoDocumento: string) => Promise<unknown>;
  onRemoverDocumento?: (documentoId: string, item: DocumentoChecklistItem) => void;
  uploading?: boolean;
  onVisualizarDocumento?: (documentoId: string) => void;
  onBaixarDocumento?: (documentoId: string, nomeArquivo: string) => void;
  /** Re-queues a slot file's reading — the Anexos rows' same mutation. */
  onReextrairDocumento?: (documentoId: string) => void;
  /** The document whose re-read request is in flight, if any. */
  reextraindoDocumentoId?: string | null;
  /** The record's values, keyed by COLUMN — the identity data on file. */
  valores?: DadosPessoais;
  /** Saves ONE identity field typed by the operator (owner directive
   *  2026-10-24: "a field must not be upload-only, we can set them
   *  manually"). Same callback `ChecklistItemRow` uses. */
  onSaveCampo?: (patch: DadosPessoais) => void;
  savingCampo?: boolean;
  testIdPrefix?: string;
}

/** The identity data shown on the row, in the contract's order. `nome_oficial`
 *  is left out: it has its own "Nome no documento" block below the list. */
const DADOS_IDENTIDADE: ReadonlyArray<{ campo: keyof DadosPessoais; rotulo: string }> = [
  { campo: "cpf", rotulo: "CPF" },
  { campo: "rg", rotulo: "RG" },
  { campo: "rg_orgao_expedidor", rotulo: "Órgão expedidor" },
];

export function IdentidadeChecklistRow({
  item,
  onToggle,
  onUploadDocumento,
  onRemoverDocumento,
  uploading,
  onVisualizarDocumento,
  onBaixarDocumento,
  onReextrairDocumento,
  reextraindoDocumentoId,
  valores,
  onSaveCampo,
  savingCampo,
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
  // Only an ALL-of item (the identity one — it is the item that sends
  // `faltando`) owns identity data; a plain document item (Serasa Crednet)
  // rides this row for its upload slot alone. Every identity field is listed
  // — empty ones too — so each one can be typed when no document carries it.
  const dadosNaFicha = item.faltando !== undefined ? DADOS_IDENTIDADE : [];

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

      {dadosNaFicha.length > 0 && (
        <div
          className="ml-6 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground/90"
          data-testid={`${tid}-dados`}
        >
          {dadosNaFicha.map(({ campo, rotulo }) => (
            <DadoIdentidade
              key={campo}
              campo={campo}
              rotulo={rotulo}
              valor={valores?.[campo]}
              onSaveCampo={onSaveCampo}
              saving={savingCampo}
              tid={`${tid}-dados-${campo}`}
            />
          ))}
        </div>
      )}
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
              {semLeitura.length === 1 ? "esse dado" : "esses dados"}, ou digite
              no lápis ao lado do campo.
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
            onReextrairDocumento={onReextrairDocumento}
            reextraindo={!!slot.documento && reextraindoDocumentoId === slot.documento.id}
            tid={`${tid}-${slot.tipo_documento}`}
          />
        ))}
      </ul>
    </li>
  );
}

/** One identity datum on the row: its value (or "—") and a pencil that
 *  types it in place — a document is a source, never the only way in. */
function DadoIdentidade({
  campo,
  rotulo,
  valor,
  onSaveCampo,
  saving,
  tid,
}: {
  campo: keyof DadosPessoais;
  rotulo: string;
  valor: unknown;
  onSaveCampo?: (patch: DadosPessoais) => void;
  saving?: boolean;
  tid: string;
}) {
  const atual = typeof valor === "string" && valor.trim() !== "" ? valor : null;
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState("");

  function salvar() {
    if (!onSaveCampo) return;
    const limpo = rascunho.trim();
    onSaveCampo({ [campo]: limpo === "" ? null : limpo } as DadosPessoais);
    setEditando(false);
  }

  if (editando) {
    return (
      <span className="flex items-center gap-1" data-testid={tid}>
        {rotulo}:
        <Input
          autoFocus
          className="h-7 w-40"
          value={rascunho}
          aria-label={rotulo}
          data-testid={`${tid}-input`}
          onChange={(e) => setRascunho(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") salvar();
            if (e.key === "Escape") setEditando(false);
          }}
        />
        <TooltipIconButton
          label={`Salvar ${rotulo}`}
          icon={Check}
          testId={`${tid}-salvar`}
          className="h-7 w-7"
          disabled={saving}
          onClick={salvar}
        />
        <TooltipIconButton
          label="Cancelar"
          icon={X}
          testId={`${tid}-cancelar`}
          className="h-7 w-7"
          onClick={() => setEditando(false)}
        />
      </span>
    );
  }

  return (
    <span className="flex items-center gap-0.5" data-testid={tid}>
      {rotulo}:{" "}
      <span className={cn("font-medium", atual ? "text-foreground/90" : "text-muted-foreground")}>
        {atual ?? "—"}
      </span>
      {onSaveCampo && (
        <TooltipIconButton
          label={`Editar ${rotulo}`}
          icon={Pencil}
          testId={`${tid}-editar`}
          className="h-6 w-6"
          onClick={() => {
            setRascunho(atual ?? "");
            setEditando(true);
          }}
        />
      )}
    </span>
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
  onReextrairDocumento,
  reextraindo,
  tid,
}: {
  item: DocumentoChecklistItem;
  slot: IdentidadeSlot;
  onUploadDocumento?: IdentidadeChecklistRowProps["onUploadDocumento"];
  onRemoverDocumento?: IdentidadeChecklistRowProps["onRemoverDocumento"];
  uploading?: boolean;
  onVisualizarDocumento?: (documentoId: string) => void;
  onBaixarDocumento?: (documentoId: string, nomeArquivo: string) => void;
  onReextrairDocumento?: (documentoId: string) => void;
  reextraindo?: boolean;
  tid: string;
}) {
  // 🔴 Its OWN input, held by a ref — several parties' rows are on screen at
  // once, and a shared input would file one person's CNH onto another.
  const inputArquivo = useRef<HTMLInputElement>(null);
  const doc = slot.documento;
  const envio = useUploadDocumento((file: File) =>
    onUploadDocumento ? onUploadDocumento(item, file, slot.tipo_documento) : Promise.resolve(undefined),
  );

  return (
    <li data-testid={`${tid}-slot-wrap`}>
    <div className="flex items-center gap-2" data-testid={`${tid}-slot`}>
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
              if (file) void envio.enviar(file);
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
      {/* Every slot type is read automatically (`fontes.FONTES`), so a filed
          slot is always re-readable — same action, label and pending state as
          the Anexos rows; the error toast lives with the caller's mutation. */}
      {doc && onReextrairDocumento && (
        <TooltipIconButton
          label="Ler o documento novamente"
          icon={RotateCw}
          testId={`${tid}-reextrair`}
          className="h-7 w-7"
          disabled={reextraindo}
          iconClassName={reextraindo ? "animate-spin" : undefined}
          onClick={() => onReextrairDocumento(doc.id)}
        />
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
    </div>
    <UploadErro erro={envio.erro} onDismiss={envio.limpar} className="mt-1" data-testid={`${tid}-upload-erro`} />
    </li>
  );
}
