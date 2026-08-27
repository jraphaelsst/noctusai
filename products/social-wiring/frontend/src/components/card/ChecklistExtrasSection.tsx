/**
 * ChecklistExtrasSection — the rows the OPERATOR creates.
 *
 * The mandatory list above is the same six items for every client, defined
 * server-side, and that is exactly why it cannot carry "cópia da certidão de
 * casamento" or "comprovante de renda do cônjuge": those belong to ONE deal.
 * Before this section the only place to put them was a free-text note nobody
 * could tick, so they were tracked in someone's head.
 *
 * 🔴 TWO KINDS OF ROW, CHOSEN AT CREATION
 * ---------------------------------------
 * A row holds either TEXT or a FILE, and which one is a property of the row,
 * not of the moment. Asking up front is what lets the row render the right
 * affordance forever after: a text row edits in place, a file row uploads.
 * A single "add" button that guessed would have to offer both on every row.
 *
 * 🔴 THESE ROWS ARE DELETABLE; THE MANDATORY ONES ARE NOT
 * -------------------------------------------------------
 * A mandatory row's trash discards its FILE and keeps the row (you cannot
 * delete "CPF" from a checklist the server defines). Here the trash removes
 * the ROW, because the operator created it. The file-only discard is a second,
 * separate affordance on file rows — same distinction, one level down.
 *
 * 🔴 THE TICK IS A READOUT, NOT A CONTROL
 * ---------------------------------------
 * `concluido` arrives derived and the PATCH contract has no field for it, so
 * the checkbox is rendered non-interactive with a hint saying why. A checkbox
 * that moved and then silently failed to persist is the lying-state failure
 * (`CLAUDE.md` §1) wearing a different hat.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useRef, useState } from "react";
import { Check, FileText, FileUp, FileX, ListPlus, Pencil, Trash2, Type, Upload, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ChecklistExtra, ChecklistExtraTipo } from "@/types/cardHub";

import { TokenCheckbox } from "./TokenCheckbox";
import { TooltipIconButton } from "./TooltipIconButton";
import { formatBytes } from "./format";

const TICK_DERIVADO =
  "Marcado automaticamente quando a linha recebe um valor ou um arquivo";

export interface ChecklistExtrasSectionProps {
  items: ChecklistExtra[];
  loading?: boolean;
  error?: string | null;
  onCriar: (body: { label: string; tipo: ChecklistExtraTipo }) => void;
  criando?: boolean;
  onRenomear: (extraId: string, label: string) => void;
  onSalvarTexto: (extraId: string, valorTexto: string) => void;
  onRemover: (extraId: string) => void;
  onUploadDocumento: (extraId: string, file: File) => void;
  /** Discards the FILE and keeps the row — the same rule the mandatory rows
   *  follow, so "delete" never means two different things on one screen. */
  onRemoverDocumento: (extraId: string) => void;
  salvando?: boolean;
  testIdPrefix?: string;
}

export function ChecklistExtrasSection({
  items,
  loading,
  error,
  onCriar,
  criando,
  onRenomear,
  onSalvarTexto,
  onRemover,
  onUploadDocumento,
  onRemoverDocumento,
  salvando,
  testIdPrefix = "checklist-extras",
}: ChecklistExtrasSectionProps) {
  // `null` = not creating. Otherwise it holds the KIND being created, so the
  // one inline input knows what it is about to make.
  const [novoTipo, setNovoTipo] = useState<ChecklistExtraTipo | null>(null);
  const [novoLabel, setNovoLabel] = useState("");

  function criar() {
    const label = novoLabel.trim();
    if (!label || !novoTipo) return;
    onCriar({ label, tipo: novoTipo });
    setNovoLabel("");
    setNovoTipo(null);
  }

  return (
    <div className="mb-5" data-testid={`${testIdPrefix}-section`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Outros dados
        </p>
        <div className="flex items-center gap-1">
          <TooltipIconButton
            label="Adicionar dado de texto"
            icon={Type}
            testId={`${testIdPrefix}-add-texto`}
            className="h-7 w-7"
            disabled={criando}
            onClick={() => {
              setNovoLabel("");
              setNovoTipo("texto");
            }}
          />
          <TooltipIconButton
            label="Adicionar dado de arquivo"
            icon={FileUp}
            testId={`${testIdPrefix}-add-arquivo`}
            className="h-7 w-7"
            disabled={criando}
            onClick={() => {
              setNovoLabel("");
              setNovoTipo("arquivo");
            }}
          />
        </div>
      </div>

      {novoTipo && (
        <div
          className="mb-2 flex items-center gap-1.5 rounded-md border border-dashed border-border px-2.5 py-1.5"
          data-testid={`${testIdPrefix}-novo`}
        >
          <ListPlus className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <Input
            autoFocus
            className="h-7 flex-1"
            placeholder={
              novoTipo === "texto" ? "Nome do dado (texto)" : "Nome do documento (arquivo)"
            }
            aria-label={
              novoTipo === "texto"
                ? "Nome do novo dado de texto"
                : "Nome do novo dado de arquivo"
            }
            value={novoLabel}
            onChange={(e) => setNovoLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") criar();
              if (e.key === "Escape") setNovoTipo(null);
            }}
            data-testid={`${testIdPrefix}-novo-label`}
          />
          <TooltipIconButton
            label="Criar linha"
            icon={Check}
            testId={`${testIdPrefix}-novo-salvar`}
            className="h-7 w-7"
            disabled={criando}
            onClick={criar}
          />
          <TooltipIconButton
            label="Cancelar"
            icon={X}
            testId={`${testIdPrefix}-novo-cancelar`}
            className="h-7 w-7"
            onClick={() => setNovoTipo(null)}
          />
        </div>
      )}

      {loading ? (
        <div className="h-10 animate-pulse rounded bg-muted" data-testid={`${testIdPrefix}-loading`} />
      ) : error ? (
        <p className="text-sm text-destructive" data-testid={`${testIdPrefix}-erro`}>
          {error}
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid={`${testIdPrefix}-empty`}>
          Nenhum dado extra ainda.
        </p>
      ) : (
        <ul className="space-y-1" data-testid={`${testIdPrefix}-lista`}>
          {items.map((extra) => (
            <ChecklistExtraRow
              key={extra.id}
              extra={extra}
              onRenomear={onRenomear}
              onSalvarTexto={onSalvarTexto}
              onRemover={onRemover}
              onUploadDocumento={onUploadDocumento}
              onRemoverDocumento={onRemoverDocumento}
              salvando={salvando}
              testIdPrefix={testIdPrefix}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ChecklistExtraRow({
  extra,
  onRenomear,
  onSalvarTexto,
  onRemover,
  onUploadDocumento,
  onRemoverDocumento,
  salvando,
  testIdPrefix,
}: {
  extra: ChecklistExtra;
  onRenomear: (extraId: string, label: string) => void;
  onSalvarTexto: (extraId: string, valorTexto: string) => void;
  onRemover: (extraId: string) => void;
  onUploadDocumento: (extraId: string, file: File) => void;
  onRemoverDocumento: (extraId: string) => void;
  salvando?: boolean;
  testIdPrefix: string;
}) {
  const tid = `${testIdPrefix}-${extra.id}`;
  // "label" renames the row; "valor" edits what it holds. Two different edits
  // on one line, so the row must say which one is open.
  const [editando, setEditando] = useState<"label" | "valor" | null>(null);
  const [rascunho, setRascunho] = useState("");
  // Its OWN input, per the same rule the mandatory rows follow: several file
  // rows share a screen, and a shared element uploads onto the wrong one.
  const inputArquivo = useRef<HTMLInputElement>(null);

  function abrir(qual: "label" | "valor") {
    setRascunho(qual === "label" ? extra.label : (extra.valor_texto ?? ""));
    setEditando(qual);
  }

  function salvar() {
    const limpo = rascunho.trim();
    if (editando === "label") {
      if (limpo) onRenomear(extra.id, limpo);
    } else if (editando === "valor") {
      onSalvarTexto(extra.id, limpo);
    }
    setEditando(null);
  }

  const ehArquivo = extra.tipo === "arquivo";
  const exibido = ehArquivo
    ? extra.documento
      ? `${extra.documento.nome_original} · ${formatBytes(extra.documento.tamanho_bytes)}`
      : "—"
    : extra.valor_texto || "—";

  return (
    <li
      className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-sm"
      data-testid={`${tid}-row`}
    >
      <TokenCheckbox
        checked={extra.concluido}
        label={extra.label}
        hint={TICK_DERIVADO}
        testId={tid}
      />

      {editando === "label" ? (
        <Input
          autoFocus
          className="h-7 flex-1"
          value={rascunho}
          onChange={(e) => setRascunho(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") salvar();
            if (e.key === "Escape") setEditando(null);
          }}
          aria-label={`Renomear ${extra.label}`}
          data-testid={`${tid}-label-input`}
        />
      ) : (
        <span
          className={cn(
            "shrink-0 font-medium",
            extra.concluido && "text-muted-foreground line-through",
          )}
          data-testid={`${tid}-label`}
        >
          {extra.label}
        </span>
      )}

      {editando === "valor" ? (
        <Input
          autoFocus
          className="h-7 min-w-0 flex-1"
          value={rascunho}
          onChange={(e) => setRascunho(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") salvar();
            if (e.key === "Escape") setEditando(null);
          }}
          aria-label={`${extra.label} — novo valor`}
          data-testid={`${tid}-valor-input`}
        />
      ) : (
        editando === null && (
          <span
            className="min-w-0 flex-1 truncate text-muted-foreground"
            data-testid={`${tid}-valor`}
          >
            {ehArquivo && extra.documento && (
              <FileText className="mr-1 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
            )}
            {exibido}
          </span>
        )
      )}

      {editando !== null ? (
        <>
          <TooltipIconButton
            label="Salvar"
            icon={Check}
            testId={`${tid}-salvar`}
            className="h-7 w-7"
            disabled={salvando}
            onClick={salvar}
          />
          <TooltipIconButton
            label="Cancelar"
            icon={X}
            testId={`${tid}-cancelar`}
            className="h-7 w-7"
            onClick={() => setEditando(null)}
          />
        </>
      ) : (
        <>
          <TooltipIconButton
            label={`Renomear ${extra.label}`}
            icon={Pencil}
            testId={`${tid}-renomear`}
            className="h-7 w-7"
            onClick={() => abrir("label")}
          />
          {ehArquivo ? (
            <>
              <input
                ref={inputArquivo}
                type="file"
                className="hidden"
                data-testid={`${tid}-arquivo-input`}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onUploadDocumento(extra.id, file);
                  e.target.value = "";
                }}
              />
              <TooltipIconButton
                label={
                  extra.documento ? `Substituir ${extra.label}` : `Enviar ${extra.label}`
                }
                icon={Upload}
                testId={`${tid}-upload`}
                className="h-7 w-7"
                disabled={salvando}
                onClick={() => inputArquivo.current?.click()}
              />
              {extra.documento && (
                <TooltipIconButton
                  label={`Descartar o arquivo de ${extra.label}`}
                  icon={FileX}
                  testId={`${tid}-descartar-arquivo`}
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => onRemoverDocumento(extra.id)}
                />
              )}
            </>
          ) : (
            <TooltipIconButton
              label={`Editar ${extra.label}`}
              icon={Type}
              testId={`${tid}-editar`}
              className="h-7 w-7"
              onClick={() => abrir("valor")}
            />
          )}
          <TooltipIconButton
            label={`Remover ${extra.label}`}
            icon={Trash2}
            testId={`${tid}-remover`}
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={() => onRemover(extra.id)}
          />
        </>
      )}
    </li>
  );
}
