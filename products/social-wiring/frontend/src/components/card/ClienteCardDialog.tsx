/**
 * ClienteCardDialog — the two-pane card detail (screenshots 02, 03, 09, 10).
 * PROJECT.md §4.
 *
 * NOT built on the seed `EntityDetailDialog` organ — checked first
 * (`noc-organ-consume-check`). That organ's chrome is a single-column
 * label/value field grid with a footer action row; this view needs an
 * action row that OPENS popovers, two independently-scrollable panes, a
 * chip cluster, a composer, and per-checklist progress bars — none of
 * which the organ's `DetailSection`/`DetailField` shape can express without
 * fighting it. Built directly on the product's `ui/dialog` (Radix) instead,
 * same primitive `LeadDetailModal`'s organ itself is built from one layer
 * down. Flagged as a `scoped-improvement:` candidate: if a second product
 * needs a two-pane detail view, THIS shape (not another bespoke one) is
 * the seed extraction target.
 *
 * Presentational only (S3, §0): everything below is props in / callbacks
 * out. Zero imports from `@/pages/**` or any social-wiring-specific module.
 * The smart wrapper (`@/components/ClienteDetailModal.tsx`, outside
 * `card/**`) owns `useCardHub` and feeds this component.
 *
 * States: loading / error / success at the dialog level (there is no
 * meaningful "empty" state for a single record — a missing record is
 * `notFound`, handled like an error).
 */
import { useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  MoreHorizontal,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type {
  Checklist,
  DatasPatchBody,
  Documento,
  CardDatas,
  Membro,
  Tag,
  TimelineEntry,
  TipoDocumento,
} from "@/types/cardHub";

import { resolveDueState } from "./ClienteCardFace";
import { Timeline } from "./Timeline";
import { AdicionarPopover, type AdicionarOption } from "./popovers/AdicionarPopover";
import { ChecklistDialog } from "./popovers/ChecklistDialog";
import { DatasPopover } from "./popovers/DatasPopover";
import { EtiquetasPopover } from "./popovers/EtiquetasPopover";
import { MembrosPopover } from "./popovers/MembrosPopover";

type PopoverKey = "adicionar" | "etiquetas" | "datas" | "checklist" | "membros" | null;

const DUE_LABEL: Record<string, string> = {
  overdue: "Atrasado",
  soon: "Entregar em breve",
  upcoming: "",
  done: "Concluído",
};

export interface ClienteCardDialogProps {
  open: boolean;
  onClose: () => void;
  isLoading: boolean;
  error?: string | null;
  notFound?: boolean;

  nome: string;

  // Etiquetas
  allTags: Tag[];
  selectedTags: Tag[];
  onToggleTag: (tagId: string) => void;
  onCreateTag: (nome: string, cor: string) => void;
  onEditTag: (tagId: string) => void;
  colorBlindMode: boolean;
  onToggleColorBlindMode: (enabled: boolean) => void;
  tagsSaving?: boolean;

  // Datas
  datas: CardDatas | null;
  onSaveDatas: (body: DatasPatchBody) => void;
  onRemoveDatas: () => void;
  datasSaving?: boolean;

  // Membros
  allMembros: Membro[];
  selectedMembros: Membro[];
  onToggleMembro: (membroId: string) => void;
  membrosSaving?: boolean;

  // Descrição — derived by the container from the oldest non-deleted nota
  // (§4's contract-gap note: `cliente_notas` covers BOTH Descrição and
  // Comentários with no discriminator field; see the container's docblock).
  descricaoCorpo: string;
  onSaveDescricao: (corpo: string) => void;
  descricaoSaving?: boolean;

  // Anexos
  documentos: Documento[];
  documentosLoading: boolean;
  tiposDocumento: TipoDocumento[];
  onUploadDocumento: (file: File, tipoDocumento: string) => void;
  uploadingDocumento?: boolean;
  onOpenDocumento: (documentoId: string) => void;
  onDeleteDocumento: (documentoId: string, motivo: string) => void;

  // Checklists
  checklists: Checklist[];
  checklistsLoading: boolean;
  onCreateChecklist: (titulo: string) => void;
  onRemoveChecklist: (checklistId: string) => void;
  onAddItem: (checklistId: string, texto: string) => void;
  onToggleItem: (checklistId: string, itemId: string, concluido: boolean) => void;
  onRemoveItem: (checklistId: string, itemId: string) => void;

  // Comentários e atividade
  timelineEntries: TimelineEntry[];
  timelineLoading: boolean;
  timelineError?: string | null;
  timelineHasMore?: boolean;
  timelineLoadingMore?: boolean;
  onTimelineLoadMore?: () => void;
  onPostComentario: (corpo: string) => void;
  postingComentario?: boolean;
}

export function ClienteCardDialog(props: ClienteCardDialogProps) {
  const { open, onClose, isLoading, error, notFound, nome } = props;
  const [activePopover, setActivePopover] = useState<PopoverKey>(null);

  function handleAdicionarSelect(option: AdicionarOption) {
    if (option === "anexo") {
      document.getElementById("card-anexo-file-input")?.click();
      return;
    }
    setActivePopover(option);
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="grid h-[85vh] max-w-5xl grid-cols-1 gap-0 overflow-hidden p-0 md:grid-cols-[1fr_360px]"
        data-testid="cliente-card-dialog"
      >
        {error ? (
          <div className="col-span-full flex flex-col items-center justify-center gap-3 p-10 text-center">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive" data-testid="cliente-card-dialog-error">
              Não foi possível carregar este cartão.
            </p>
          </div>
        ) : isLoading ? (
          <div className="col-span-full space-y-3 p-10" data-testid="cliente-card-dialog-loading">
            <div className="h-6 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-32 w-full animate-pulse rounded bg-muted" />
          </div>
        ) : notFound ? (
          <div className="col-span-full flex items-center justify-center p-10">
            <p className="text-sm text-muted-foreground" data-testid="cliente-card-dialog-not-found">
              Cartão não encontrado.
            </p>
          </div>
        ) : (
          <>
            <DialogTitle className="sr-only">{nome}</DialogTitle>
            <DialogDescription className="sr-only">
              Detalhes do cartão de {nome}
            </DialogDescription>

            {/* ── Left pane — content ─────────────────────────────── */}
            <ScrollArea className="border-r p-6">
              <h2 className="mb-4 text-xl font-semibold">{nome}</h2>

              <div className="mb-4 flex flex-wrap gap-2">
                <AdicionarPopover
                  open={activePopover === "adicionar"}
                  onOpenChange={(o) => setActivePopover(o ? "adicionar" : null)}
                  onSelect={handleAdicionarSelect}
                />
                <EtiquetasPopover
                  open={activePopover === "etiquetas"}
                  onOpenChange={(o) => setActivePopover(o ? "etiquetas" : null)}
                  allTags={props.allTags}
                  selectedTagIds={props.selectedTags.map((t) => t.id)}
                  onToggleTag={props.onToggleTag}
                  onCreateTag={props.onCreateTag}
                  onEditTag={props.onEditTag}
                  colorBlindMode={props.colorBlindMode}
                  onToggleColorBlindMode={props.onToggleColorBlindMode}
                  saving={props.tagsSaving}
                />
                <DatasPopover
                  open={activePopover === "datas"}
                  onOpenChange={(o) => setActivePopover(o ? "datas" : null)}
                  datas={props.datas}
                  onSave={props.onSaveDatas}
                  onRemove={props.onRemoveDatas}
                  saving={props.datasSaving}
                />
                <ChecklistDialog
                  open={activePopover === "checklist"}
                  onOpenChange={(o) => setActivePopover(o ? "checklist" : null)}
                  onCreate={(titulo) => {
                    props.onCreateChecklist(titulo);
                    setActivePopover(null);
                  }}
                />
                <MembrosPopover
                  open={activePopover === "membros"}
                  onOpenChange={(o) => setActivePopover(o ? "membros" : null)}
                  allMembros={props.allMembros}
                  selectedMembroIds={props.selectedMembros.map((m) => m.id)}
                  onToggleMembro={props.onToggleMembro}
                  saving={props.membrosSaving}
                />
                <input
                  id="card-anexo-file-input"
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) props.onUploadDocumento(file, props.tiposDocumento[0]?.codigo ?? "outro");
                    e.target.value = "";
                  }}
                />
              </div>

              {props.selectedTags.length > 0 && (
                <div className="mb-4" data-testid="etiquetas-chips">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Etiquetas
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {props.selectedTags.map((tag) => (
                      <span
                        key={tag.id}
                        className="rounded px-2.5 py-1 text-xs font-medium text-white"
                        style={{ backgroundColor: tag.cor }}
                        data-testid={`etiqueta-chip-${tag.id}`}
                      >
                        {tag.nome}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {props.datas?.data_entrega && (
                <div className="mb-4" data-testid="data-entrega-section">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Data Entrega
                  </p>
                  <DataEntregaPill datas={props.datas} />
                </div>
              )}

              <DescricaoSection
                corpo={props.descricaoCorpo}
                onSave={props.onSaveDescricao}
                saving={props.descricaoSaving}
              />

              <AnexosSection
                documentos={props.documentos}
                loading={props.documentosLoading}
                onOpenDocumento={props.onOpenDocumento}
                onDeleteDocumento={props.onDeleteDocumento}
              />

              <ChecklistsSection
                checklists={props.checklists}
                loading={props.checklistsLoading}
                onRemoveChecklist={props.onRemoveChecklist}
                onAddItem={props.onAddItem}
                onToggleItem={props.onToggleItem}
                onRemoveItem={props.onRemoveItem}
              />
            </ScrollArea>

            {/* ── Right pane — Comentários e atividade ────────────── */}
            <div className="flex min-h-0 flex-col p-6">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                Comentários e atividade
              </h3>

              <ComentarioComposer onPost={props.onPostComentario} posting={props.postingComentario} />

              <ScrollArea className="mt-4 flex-1">
                <Timeline
                  entries={props.timelineEntries}
                  loading={props.timelineLoading}
                  error={props.timelineError}
                  hasMore={props.timelineHasMore}
                  loadingMore={props.timelineLoadingMore}
                  onLoadMore={props.onTimelineLoadMore}
                />
              </ScrollArea>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Sub-sections ───────────────────────────────────────────────────────────

function DataEntregaPill({ datas }: { datas: CardDatas }) {
  if (!datas.data_entrega) return null;
  const state = resolveDueState(datas.data_entrega, datas.entrega_concluida);
  const label = DUE_LABEL[state];
  const stateClasses: Record<string, string> = {
    overdue: "bg-red-500/20 text-red-400",
    soon: "bg-amber-500/20 text-amber-400",
    upcoming: "bg-secondary text-secondary-foreground",
    done: "bg-emerald-500/20 text-emerald-400",
  };
  return (
    <span
      className={cn("inline-flex items-center gap-2 rounded px-2.5 py-1 text-sm font-medium", stateClasses[state])}
      data-testid="data-entrega-pill"
    >
      {formatDate(datas.data_entrega, true)}
      {label && <span data-testid="data-entrega-pill-label">{label}</span>}
    </span>
  );
}

function DescricaoSection({
  corpo,
  onSave,
  saving,
}: {
  corpo: string;
  onSave: (corpo: string) => void;
  saving?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(corpo);
  const [expanded, setExpanded] = useState(false);
  const isLong = corpo.length > 240;
  const shown = !isLong || expanded ? corpo : `${corpo.slice(0, 240)}…`;

  return (
    <div className="mb-4" data-testid="descricao-section">
      <div className="mb-1 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <FileText className="h-3.5 w-3.5" />
          Descrição
        </p>
        {!editing && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setDraft(corpo);
              setEditing(true);
            }}
            data-testid="descricao-editar-btn"
          >
            Editar
          </Button>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            data-testid="descricao-textarea"
            autoFocus
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={saving}
              onClick={() => {
                onSave(draft);
                setEditing(false);
              }}
              data-testid="descricao-salvar-btn"
            >
              Salvar
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      ) : corpo ? (
        <>
          <p className="whitespace-pre-wrap break-words text-sm">{shown}</p>
          {isLong && (
            <Button
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => setExpanded((v) => !v)}
              data-testid="descricao-mostrar-mais"
            >
              {expanded ? <ChevronUp className="mr-1 h-3.5 w-3.5" /> : <ChevronDown className="mr-1 h-3.5 w-3.5" />}
              {expanded ? "Mostrar menos" : "Mostrar mais"}
            </Button>
          )}
        </>
      ) : (
        <p className="text-sm italic text-muted-foreground">Sem descrição ainda.</p>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AnexosSection({
  documentos,
  loading,
  onOpenDocumento,
  onDeleteDocumento,
}: {
  documentos: Documento[];
  loading: boolean;
  onOpenDocumento: (id: string) => void;
  onDeleteDocumento: (id: string, motivo: string) => void;
}) {
  return (
    <div className="mb-4" data-testid="anexos-section">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Anexos</p>
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
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onOpenDocumento(doc.id)}
                data-testid={`anexo-abrir-${doc.id}`}
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onDeleteDocumento(doc.id, "Removido pelo usuário")}
                data-testid={`anexo-remover-${doc.id}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ChecklistsSection({
  checklists,
  loading,
  onRemoveChecklist,
  onAddItem,
  onToggleItem,
  onRemoveItem,
}: {
  checklists: Checklist[];
  loading: boolean;
  onRemoveChecklist: (id: string) => void;
  onAddItem: (checklistId: string, texto: string) => void;
  onToggleItem: (checklistId: string, itemId: string, concluido: boolean) => void;
  onRemoveItem: (checklistId: string, itemId: string) => void;
}) {
  if (loading) return <div className="h-16 animate-pulse rounded bg-muted" />;
  if (checklists.length === 0) return null;

  return (
    <div className="space-y-5" data-testid="checklists-section">
      {checklists.map((cl) => (
        <ChecklistBlock
          key={cl.id}
          checklist={cl}
          onRemove={() => onRemoveChecklist(cl.id)}
          onAddItem={(texto) => onAddItem(cl.id, texto)}
          onToggleItem={(itemId, concluido) => onToggleItem(cl.id, itemId, concluido)}
          onRemoveItem={(itemId) => onRemoveItem(cl.id, itemId)}
        />
      ))}
    </div>
  );
}

function ChecklistBlock({
  checklist,
  onRemove,
  onAddItem,
  onToggleItem,
  onRemoveItem,
}: {
  checklist: Checklist;
  onRemove: () => void;
  onAddItem: (texto: string) => void;
  onToggleItem: (itemId: string, concluido: boolean) => void;
  onRemoveItem: (itemId: string) => void;
}) {
  const [novoItem, setNovoItem] = useState("");
  const percent = checklist.total_itens > 0 ? Math.round((checklist.concluidos / checklist.total_itens) * 100) : 0;

  return (
    <div data-testid={`checklist-block-${checklist.id}`}>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-sm font-semibold">{checklist.titulo}</p>
        <Button variant="outline" size="sm" onClick={onRemove} data-testid={`checklist-excluir-${checklist.id}`}>
          Excluir
        </Button>
      </div>
      <div className="mb-2 flex items-center gap-2">
        <span className="w-9 text-xs text-muted-foreground">{percent}%</span>
        <Progress value={percent} className="h-2 flex-1" />
      </div>
      <ul className="space-y-1">
        {checklist.itens.map((item) => (
          <li key={item.id} className="group flex items-center gap-2">
            <input
              type="checkbox"
              checked={item.concluido}
              onChange={(e) => onToggleItem(item.id, e.target.checked)}
              className="h-4 w-4 shrink-0"
              data-testid={`checklist-item-checkbox-${item.id}`}
            />
            <span className={cn("flex-1 text-sm", item.concluido && "text-muted-foreground line-through")}>
              {item.texto}
            </span>
            <button
              type="button"
              onClick={() => onRemoveItem(item.id)}
              className="opacity-0 group-hover:opacity-100"
              data-testid={`checklist-item-remover-${item.id}`}
            >
              <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          placeholder="Adicionar um item"
          value={novoItem}
          onChange={(e) => setNovoItem(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && novoItem.trim()) {
              onAddItem(novoItem.trim());
              setNovoItem("");
            }
          }}
          className="h-8 flex-1 rounded border bg-background px-2 text-sm"
          data-testid={`checklist-novo-item-${checklist.id}`}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (!novoItem.trim()) return;
            onAddItem(novoItem.trim());
            setNovoItem("");
          }}
        >
          Adicionar
        </Button>
      </div>
    </div>
  );
}

function ComentarioComposer({ onPost, posting }: { onPost: (corpo: string) => void; posting?: boolean }) {
  const [corpo, setCorpo] = useState("");
  return (
    <div className="space-y-2">
      <Textarea
        placeholder="Escrever um comentário…"
        value={corpo}
        onChange={(e) => setCorpo(e.target.value)}
        rows={2}
        data-testid="comentario-textarea"
      />
      {corpo.trim().length > 0 && (
        <Button
          size="sm"
          disabled={posting}
          onClick={() => {
            onPost(corpo.trim());
            setCorpo("");
          }}
          data-testid="comentario-enviar-btn"
        >
          {posting ? "Enviando…" : "Comentar"}
        </Button>
      )}
    </div>
  );
}
