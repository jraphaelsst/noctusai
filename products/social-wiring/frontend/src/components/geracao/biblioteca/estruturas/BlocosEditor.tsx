/**
 * The ordered blocks of an Estrutura (admin). Each block names a canonical TYPE from the platform catalog
 * (`GET /estruturas/tipos-bloco`) and carries its own display name, tempo (or slide/frame label),
 * instruction, note and repeat count.
 *
 * Reordering is drag-and-drop (dnd-kit; keyboard sensor on the handle) AND move up/down buttons — dragging
 * must never be the only way (WCAG 2.5.7). The editor is controlled: the parent owns the draft and the
 * "unsaved" state (`useUnsavedChanges`); nothing here talks to the server.
 */
import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { Bloco, TipoBloco } from "@/types/estruturas";
import { ProvenienciaBadge } from "./ProvenienciaBadge";
import { campoBloco, type BlocoRascunho } from "./rotulos";
import type { ErrosRascunho } from "./schema";

export const BLOCOS_MAX = 60;

interface Props {
  blocos: BlocoRascunho[];
  onChange: (blocos: BlocoRascunho[]) => void;
  tipos: TipoBloco[];
  /** Persisted blocks — the source of each field's provenance (by server id). */
  salvos: Bloco[];
  erros: ErrosRascunho;
  somenteLeitura?: boolean;
  onConfirmarCampo?: (campo: string) => void;
  confirmarDesabilitado?: boolean;
  motivoConfirmar?: string;
}

const CLASSE_SELECT =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

export function BlocosEditor({
  blocos,
  onChange,
  tipos,
  salvos,
  erros,
  somenteLeitura = false,
  onConfirmarCampo,
  confirmarDesabilitado,
  motivoConfirmar,
}: Props) {
  const seq = useRef(0);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ativos = tipos.filter((t) => t.ativo);
  const tipoPadrao = ativos.find((t) => t.nome === "Outro") ?? ativos[0];

  const alterar = (chave: string, mudanca: Partial<BlocoRascunho>) =>
    onChange(blocos.map((b) => (b.chave === chave ? { ...b, ...mudanca } : b)));
  const mover = (de: number, para: number) => {
    if (para < 0 || para >= blocos.length) return;
    onChange(arrayMove(blocos, de, para));
  };
  const remover = (chave: string) => onChange(blocos.filter((b) => b.chave !== chave));
  const adicionar = () => {
    if (!tipoPadrao || blocos.length >= BLOCOS_MAX) return;
    seq.current += 1;
    onChange([
      ...blocos,
      { chave: `novo-${seq.current}`, nome: "", tipo_id: tipoPadrao.id, tempo: "", instrucao: "", nota: "", repeticoes: 1 },
    ]);
  };
  const aoSoltar = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const de = blocos.findIndex((b) => b.chave === e.active.id);
    const para = blocos.findIndex((b) => b.chave === e.over!.id);
    if (de >= 0 && para >= 0) onChange(arrayMove(blocos, de, para));
  };

  return (
    <section aria-label="Blocos" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Blocos ({blocos.length})</h2>
        {!somenteLeitura && (
          <Button type="button" size="sm" variant="outline" onClick={adicionar} disabled={!tipoPadrao || blocos.length >= BLOCOS_MAX}>
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" /> Adicionar bloco
          </Button>
        )}
      </div>
      {erros.blocos && (
        <p role="alert" className="text-sm text-destructive">
          {erros.blocos}
        </p>
      )}
      {blocos.length === 0 ? (
        <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          Nenhum bloco ainda. Adicione o primeiro para definir a sequência do roteiro.
        </p>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={aoSoltar}>
          <SortableContext items={blocos.map((b) => b.chave)} strategy={verticalListSortingStrategy}>
            <ol className="flex flex-col gap-3">
              {blocos.map((b, i) => (
                <BlocoLinha
                  key={b.chave}
                  indice={i}
                  total={blocos.length}
                  bloco={b}
                  salvo={b.id ? salvos.find((s) => s.id === b.id) : undefined}
                  tipos={tipos}
                  erros={erros}
                  somenteLeitura={somenteLeitura}
                  onAlterar={(m) => alterar(b.chave, m)}
                  onMover={mover}
                  onRemover={() => remover(b.chave)}
                  onConfirmarCampo={onConfirmarCampo}
                  confirmarDesabilitado={confirmarDesabilitado}
                  motivoConfirmar={motivoConfirmar}
                />
              ))}
            </ol>
          </SortableContext>
        </DndContext>
      )}
    </section>
  );
}

interface LinhaProps {
  indice: number;
  total: number;
  bloco: BlocoRascunho;
  salvo: Bloco | undefined;
  tipos: TipoBloco[];
  erros: ErrosRascunho;
  somenteLeitura: boolean;
  onAlterar: (m: Partial<BlocoRascunho>) => void;
  onMover: (de: number, para: number) => void;
  onRemover: () => void;
  onConfirmarCampo?: (campo: string) => void;
  confirmarDesabilitado?: boolean;
  motivoConfirmar?: string;
}

function BlocoLinha({ indice, total, bloco, salvo, tipos, erros, somenteLeitura, onAlterar, onMover, onRemover, onConfirmarCampo, confirmarDesabilitado, motivoConfirmar }: LinhaProps) {
  const n = indice + 1;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: bloco.chave, disabled: somenteLeitura });
  const tipoAtual = tipos.find((t) => t.id === bloco.tipo_id);
  // The catalog read only carries active types for members; an admin sees all. Keep the current value selectable.
  const opcoes = tipos.filter((t) => t.ativo || t.id === bloco.tipo_id);
  const erro = (c: string) => erros[`bloco.${bloco.chave}.${c}`];
  const id = (c: string) => `bloco-${bloco.chave}-${c}`;
  const prov = salvo?.proveniencia;
  const confirmar = (c: "nome" | "tipo" | "tempo" | "instrucao") =>
    salvo && onConfirmarCampo ? () => onConfirmarCampo(campoBloco(salvo.id, c)) : undefined;

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("rounded-lg border bg-card p-3 shadow-xs", isDragging && "opacity-60 ring-2 ring-primary")}
      data-testid={`bloco-${n}`}
    >
      <div className="mb-3 flex items-center gap-2">
        {!somenteLeitura && (
          <button
            type="button"
            className="flex cursor-grab touch-none items-center text-muted-foreground hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`Arrastar bloco ${n}`}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
        <span className="text-sm font-semibold">Bloco {n}</span>
        {!somenteLeitura && (
          <div className="ml-auto flex items-center gap-1">
            <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label={`Mover bloco ${n} para cima`} disabled={indice === 0} onClick={() => onMover(indice, indice - 1)}>
              <ArrowUp className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label={`Mover bloco ${n} para baixo`} disabled={indice === total - 1} onClick={() => onMover(indice, indice + 1)}>
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-destructive" aria-label={`Remover bloco ${n}`} onClick={onRemover}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-[2fr_1.5fr_1fr_6rem]">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor={id("nome")}>Nome</Label>
            <ProvenienciaBadge origem={prov?.nome} campo={`o nome do bloco ${n}`} onConfirmar={confirmar("nome")} desabilitado={confirmarDesabilitado} motivoDesabilitado={motivoConfirmar} />
          </div>
          <Input id={id("nome")} aria-label={`Nome do bloco ${n}`} aria-invalid={!!erro("nome")} aria-describedby={erro("nome") ? id("nome-erro") : undefined} value={bloco.nome} onChange={(e) => onAlterar({ nome: e.target.value })} disabled={somenteLeitura} maxLength={200} />
          {erro("nome") && <p id={id("nome-erro")} className="text-xs text-destructive">{erro("nome")}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor={id("tipo")}>Tipo</Label>
            <ProvenienciaBadge origem={prov?.tipo} campo={`o tipo do bloco ${n}`} onConfirmar={confirmar("tipo")} desabilitado={confirmarDesabilitado} motivoDesabilitado={motivoConfirmar} />
          </div>
          <select id={id("tipo")} aria-label={`Tipo do bloco ${n}`} className={CLASSE_SELECT} value={bloco.tipo_id} onChange={(e) => onAlterar({ tipo_id: e.target.value })} disabled={somenteLeitura}>
            {!tipoAtual && <option value={bloco.tipo_id}>{salvo?.tipo.nome ?? "Tipo desconhecido"}</option>}
            {opcoes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nome}
                {t.ativo ? "" : " (inativo)"}
              </option>
            ))}
          </select>
          {erro("tipo_id") && <p className="text-xs text-destructive">{erro("tipo_id")}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor={id("tempo")}>Tempo</Label>
            <ProvenienciaBadge origem={prov?.tempo} campo={`o tempo do bloco ${n}`} onConfirmar={confirmar("tempo")} desabilitado={confirmarDesabilitado} motivoDesabilitado={motivoConfirmar} />
          </div>
          <Input id={id("tempo")} aria-label={`Tempo do bloco ${n}`} aria-invalid={!!erro("tempo")} aria-describedby={erro("tempo") ? id("tempo-erro") : undefined} value={bloco.tempo} placeholder={tipoAtual?.tempo_tipico ?? "3–7s, slide 2…"} onChange={(e) => onAlterar({ tempo: e.target.value })} disabled={somenteLeitura} maxLength={80} />
          {erro("tempo") && <p id={id("tempo-erro")} className="text-xs text-destructive">{erro("tempo")}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={id("rep")}>Repetições</Label>
          <Input id={id("rep")} aria-label={`Repetições do bloco ${n}`} type="number" min={1} max={20} aria-invalid={!!erro("repeticoes")} aria-describedby={erro("repeticoes") ? id("rep-erro") : undefined} value={Number.isNaN(bloco.repeticoes) ? "" : bloco.repeticoes} onChange={(e) => onAlterar({ repeticoes: e.target.value === "" ? Number.NaN : Number(e.target.value) })} disabled={somenteLeitura} />
          {erro("repeticoes") && <p id={id("rep-erro")} className="text-xs text-destructive">{erro("repeticoes")}</p>}
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor={id("instrucao")}>Instrução</Label>
            <ProvenienciaBadge origem={prov?.instrucao} campo={`a instrução do bloco ${n}`} onConfirmar={confirmar("instrucao")} desabilitado={confirmarDesabilitado} motivoDesabilitado={motivoConfirmar} />
          </div>
          <Textarea id={id("instrucao")} aria-label={`Instrução do bloco ${n}`} aria-invalid={!!erro("instrucao")} aria-describedby={erro("instrucao") ? id("instrucao-erro") : undefined} rows={3} value={bloco.instrucao} placeholder={tipoAtual ? `Padrão do tipo: ${tipoAtual.instrucao_referencia}` : undefined} onChange={(e) => onAlterar({ instrucao: e.target.value })} disabled={somenteLeitura} />
          {erro("instrucao") && <p id={id("instrucao-erro")} className="text-xs text-destructive">{erro("instrucao")}</p>}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={id("nota")}>Nota da fonte</Label>
          <Textarea id={id("nota")} aria-label={`Nota do bloco ${n}`} aria-invalid={!!erro("nota")} aria-describedby={erro("nota") ? id("nota-erro") : undefined} rows={3} value={bloco.nota} placeholder="Descreve o vídeo original; é exibida, não vira modelo." onChange={(e) => onAlterar({ nota: e.target.value })} disabled={somenteLeitura} />
          {erro("nota") && <p id={id("nota-erro")} className="text-xs text-destructive">{erro("nota")}</p>}
        </div>
      </div>
    </li>
  );
}
