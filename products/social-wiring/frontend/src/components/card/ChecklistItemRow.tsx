/**
 * ChecklistItemRow — ONE mandatory item, on ONE line.
 *
 * 🔴 WHY ONE LINE
 * ---------------
 * The three things an operator does with a required item — see whether it is
 * satisfied, supply the value, attach the document — used to live in three
 * places: the checkbox in the checklist, the value in a separate "Editar
 * dados" form, the file in the Anexos list below. Reading "Data de
 * Nascimento — pendente" and then filling it in meant leaving the list,
 * finding the field, saving, and coming back to confirm.
 *
 * This row unifies them: the tick, the value and the file are the same row.
 *
 * 🔴 THE TICK IS STILL DERIVED, AND THE ROW MUST NOT PRETEND OTHERWISE
 * --------------------------------------------------------------------
 * A checkbox here is an OVERRIDE control, not the state itself (migration
 * 068): the server ticks an item when the record carries the field or the
 * document has arrived. So the row keeps BOTH affordances the old list had —
 * the `manual` badge that says a human forced this one, with a title naming
 * what the data actually says, and the ↩ that withdraws the override and
 * hands the item back to the derivation. Dropping either would let a tick
 * that DISAGREES with the record read as evidence the data is there, which is
 * the single failure the derivation exists to prevent.
 *
 * TEXT ITEMS vs DOCUMENT ITEMS
 * ----------------------------
 * A text item (`nome_completo`, `celular`, `email`, `data_nascimento`,
 * `profissao`, `genero`) is satisfied by TYPING, so it carries a pencil and
 * edits in place — writing through the same `PATCH /api/clientes/{id}` path
 * the full form uses, with only the edited field in the body.
 *
 * A document item (`rg`, `cpf`) is satisfied by UPLOADING, so it carries an
 * upload icon and — only once a file exists — a trash that DISCARDS THE FILE
 * AND KEEPS THE ROW. The row itself is not deletable: the list is the same
 * for every client by definition, defined server-side. That asymmetry is
 * deliberate and is what separates these rows from the extras below, which
 * the operator creates and can therefore destroy.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef, useState } from "react";
import { Check, FileText, Pencil, Trash2, Undo2, Upload, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { DocumentoChecklistItem } from "@/types/cardHub";

import { GENEROS, type DadosPessoais } from "./DadosPessoaisForm";
import { TokenCheckbox } from "./TokenCheckbox";
import { TooltipIconButton } from "./TooltipIconButton";
import { formatBytes, formatarDataISO } from "./format";

type CampoTipo = "texto" | "email" | "tel" | "data" | "select";

/**
 * Which checklist key edits which column, and with which control.
 *
 * Mirrors `DadosPessoaisForm`'s field types exactly — same select for
 * `genero`, same `type="date"` for `data_nascimento`. Two editors for one
 * column that disagreed on the control would be two ways to write the same
 * value, and one of them would be wrong first.
 *
 * A key absent from this map and absent from `ITENS_DOCUMENTO` renders as a
 * plain row with a tick and no editor — a new server-side item shows up as
 * itself rather than crashing or silently vanishing.
 */
const CAMPO_POR_ITEM: Record<string, { campo: keyof DadosPessoais; tipo: CampoTipo }> = {
  nome_completo: { campo: "nome_completo", tipo: "texto" },
  celular: { campo: "celular", tipo: "tel" },
  email: { campo: "email", tipo: "email" },
  data_nascimento: { campo: "data_nascimento", tipo: "data" },
  profissao: { campo: "profissao", tipo: "texto" },
  genero: { campo: "genero", tipo: "select" },
};

/** The two satisfied by a FILE rather than by typing. */
const ITENS_DOCUMENTO = new Set(["rg", "cpf"]);

export interface ChecklistItemRowProps {
  item: DocumentoChecklistItem;
  /** The record's current value behind a text item, from the checklist
   *  response's `valores` map. */
  valor?: string | null;
  onToggle: (key: string, concluido: boolean | null) => void;
  /** Saves ONE field. The full-form editor sends the whole shape; this sends
   *  only what was edited, so an inline fix cannot overwrite a sibling field
   *  with a stale draft. */
  onSaveCampo?: (patch: DadosPessoais) => void;
  savingCampo?: boolean;
  onUploadDocumento?: (item: DocumentoChecklistItem, file: File) => void;
  /** Discards the FILE. The row stays, ready for a fresh upload. */
  onRemoverDocumento?: (documentoId: string, item: DocumentoChecklistItem) => void;
  uploading?: boolean;
  /** Disambiguates testids when several people's checklists are on screen. */
  testIdPrefix?: string;
}

export function ChecklistItemRow({
  item,
  valor,
  onToggle,
  onSaveCampo,
  savingCampo,
  onUploadDocumento,
  onRemoverDocumento,
  uploading,
  testIdPrefix = "documento-checklist",
}: ChecklistItemRowProps) {
  const tid = `${testIdPrefix}-${item.key}`;
  const campo = CAMPO_POR_ITEM[item.key];
  const ehDocumento = ITENS_DOCUMENTO.has(item.key);
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState<string>(valor ?? "");
  // 🔴 Its OWN input, held by a ref — never a shared element looked up by id.
  // Several of these rows are on screen at once (one per required document,
  // one set per party), and a shared input would file every buyer's RG onto
  // whoever mounted first. A ref cannot address the wrong element.
  const inputArquivo = useRef<HTMLInputElement>(null);

  function abrirEdicao() {
    setRascunho(valor ?? "");
    setEditando(true);
  }

  function salvar() {
    if (!campo || !onSaveCampo) return;
    const limpo = rascunho.trim();
    onSaveCampo({ [campo.campo]: limpo === "" ? null : limpo } as DadosPessoais);
    setEditando(false);
  }

  const exibido = ehDocumento
    ? item.documento
      ? `${item.documento.nome_original} · ${formatBytes(item.documento.tamanho_bytes)}`
      : "—"
    : valor
      ? campo?.tipo === "data"
        ? formatarDataISO(valor)
        : valor
      : "—";

  return (
    <li
      className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-sm"
      data-testid={`${tid}-row`}
    >
      <TokenCheckbox
        checked={item.concluido}
        onCheckedChange={(c) => onToggle(item.key, c)}
        label={item.label}
        testId={tid}
      />

      <span
        className={cn(
          "shrink-0 font-medium",
          item.concluido && "text-muted-foreground line-through",
        )}
        data-testid={`${tid}-label`}
      >
        {item.label}
      </span>

      {editando && campo ? (
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          {campo.tipo === "select" ? (
            <Select value={rascunho || GENEROS[0]} onValueChange={setRascunho}>
              <SelectTrigger className="h-7 flex-1" data-testid={`${tid}-input`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GENEROS.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              autoFocus
              className="h-7 flex-1"
              type={
                campo.tipo === "data"
                  ? "date"
                  : campo.tipo === "email"
                    ? "email"
                    : campo.tipo === "tel"
                      ? "tel"
                      : "text"
              }
              value={rascunho}
              onChange={(e) => setRascunho(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") salvar();
                if (e.key === "Escape") setEditando(false);
              }}
              aria-label={`${item.label} — novo valor`}
              data-testid={`${tid}-input`}
            />
          )}
          <TooltipIconButton
            label={`Salvar ${item.label}`}
            icon={Check}
            testId={`${tid}-salvar`}
            className="h-7 w-7"
            disabled={savingCampo}
            onClick={salvar}
          />
          <TooltipIconButton
            label="Cancelar"
            icon={X}
            testId={`${tid}-cancelar`}
            className="h-7 w-7"
            onClick={() => setEditando(false)}
          />
        </div>
      ) : (
        <span
          className={cn(
            "min-w-0 flex-1 truncate",
            exibido === "—" ? "text-muted-foreground" : "text-muted-foreground/90",
          )}
          data-testid={`${tid}-valor`}
        >
          {ehDocumento && item.documento && (
            <FileText className="mr-1 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
          )}
          {exibido}
        </span>
      )}

      {item.origem === "manual" && (
        <>
          {/* An overridden item says so. A tick that disagrees with the record
              is exactly the one a reader must not mistake for evidence that
              the data is there. */}
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

      {!editando && campo && onSaveCampo && (
        <TooltipIconButton
          label={`Editar ${item.label}`}
          icon={Pencil}
          testId={`${tid}-editar`}
          className="h-7 w-7"
          onClick={abrirEdicao}
        />
      )}

      {ehDocumento && onUploadDocumento && (
        <>
          <input
            ref={inputArquivo}
            type="file"
            className="hidden"
            data-testid={`${tid}-arquivo-input`}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUploadDocumento(item, file);
              // Cleared so re-picking the SAME file fires `change` again.
              e.target.value = "";
            }}
          />
          <TooltipIconButton
            label={item.documento ? `Substituir ${item.label}` : `Enviar ${item.label}`}
            icon={Upload}
            testId={`${tid}-upload`}
            className="h-7 w-7"
            disabled={uploading}
            onClick={() => inputArquivo.current?.click()}
          />
        </>
      )}

      {/* Only once a file exists — and it discards the FILE, never the row.
          The mandatory list is server-defined; there is no such thing as
          deleting "CPF" from it. */}
      {ehDocumento && item.documento && onRemoverDocumento && (
        <TooltipIconButton
          label={`Descartar o arquivo de ${item.label}`}
          icon={Trash2}
          testId={`${tid}-descartar-arquivo`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => onRemoverDocumento(item.documento!.id, item)}
        />
      )}
    </li>
  );
}
