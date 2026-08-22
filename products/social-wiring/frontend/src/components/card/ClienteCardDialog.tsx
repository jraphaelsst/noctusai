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
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  AlertCircle,
  Bell,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  MoreHorizontal,
  Trash2,
} from "lucide-react";

import { DetailSections } from "@noctusai/lib/components";
import type { DetailSection } from "@noctusai/lib/components";
import { campanhaCardSubpages, leadCardSubpages } from "@/pages/leads/leadDetailSections";
import type { CardSubpageSections } from "@/pages/leads/leadDetailSections";
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
  Agendamento,
  AgendamentoCreateBody,
  CardAtendimento,
  Checklist,
  Documento,
  DocumentoChecklistItem,
  CardDatas,
  Membro,
  Tag,
  TimelineEntry,
  TipoDocumento,
} from "@/types/cardHub";

import { resolveDueState } from "./ClienteCardFace";
import { Timeline } from "./Timeline";
import { ChecklistDialog } from "./popovers/ChecklistDialog";
import { AgendamentoPopover } from "./popovers/AgendamentoPopover";
import { CardSidebarNav } from "./CardSidebarNav";
import type { CardSubpageKey } from "./CardSidebarNav";
import { EtiquetasPopover } from "./popovers/EtiquetasPopover";
import { MembrosPopover } from "./popovers/MembrosPopover";

type PopoverKey = "etiquetas" | "agendamento" | "checklist" | "membros" | null;

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
  /** Surface-specific actions rendered beside the title — e.g. the Processos
   *  board's "arquivar". The card itself owns nothing board-specific, so the
   *  board passes what only it can mean. */
  acoes?: ReactNode;
  /**
   * The person's atendimentos, each with its ORIGIN record embedded. The card
   * renders the lead's own data from these — `clientes` holds identity and card
   * state and no contact fields, so this is the only source for a phone, an
   * email or the answers someone typed into a campaign form.
   */
  atendimentos?: CardAtendimento[];

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
  /**
   * Many appointments per card (migration 061), replacing the single
   * `CardDatas` slot that physically could not hold two.
   */
  agendamentos?: Agendamento[];
  agendamentosLoading?: boolean;
  onCreateAgendamento: (body: AgendamentoCreateBody) => void;
  onRemoveAgendamento: (id: string) => void;
  agendamentoSaving?: boolean;

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

  // Documento checklist — the six identity fields every new client owes us.
  // The LIST is canonical server-side, so there is no create/remove here.
  documentoChecklist?: DocumentoChecklistItem[];
  documentoChecklistLoading?: boolean;
  onToggleDocumentoChecklist: (key: string, concluido: boolean | null) => void;

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
  const { open, onClose, isLoading, error, notFound, nome, acoes } = props;
  const [activePopover, setActivePopover] = useState<PopoverKey>(null);
  // `geral` is the open-on-mount subpage: the card is opened to DO something
  // far more often than to read the record behind it.
  const [subpage, setSubpage] = useState<CardSubpageKey>("geral");
  const record = useRecordSections(props.atendimentos);
  const emptyKeys = useMemo(
    () =>
      [
        record.cliente.length ? null : "cliente",
        record.campanha.length ? null : "campanha",
      ].filter(Boolean) as CardSubpageKey[],
    [record],
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="grid h-[85vh] max-w-6xl grid-cols-1 gap-0 overflow-hidden p-0 md:grid-cols-[184px_1fr_360px]"
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

            {/* ── Left rail — subpage navigation ──────────────────── */}
            <CardSidebarNav active={subpage} onSelect={setSubpage} emptyKeys={emptyKeys} />

            {/* ── Middle pane — the active subpage ────────────────── */}
            <ScrollArea className="border-r p-6">
              <div className="mb-4 flex items-start justify-between gap-3">
                <h2 className="text-xl font-semibold">{nome}</h2>
                {acoes ? <div className="flex shrink-0 gap-2">{acoes}</div> : null}
              </div>

              {/* The action row belongs to Geral. It was card-level chrome while
                  Geral held everything; now that agendamentos and anexos have
                  their own tabs, a row of quick-actions floating above an
                  unrelated tab is just noise. Each of those tabs carries its own
                  trigger instead — the specific button next to the thing it
                  acts on, which is the same rule that retired `Adicionar`. */}
              {subpage === "geral" && (
              <div className="mb-4 flex flex-wrap gap-2">
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
                <AgendamentoPopover
                  open={activePopover === "agendamento"}
                  onOpenChange={(o) => setActivePopover(o ? "agendamento" : null)}
                  onCreate={props.onCreateAgendamento}
                  saving={props.agendamentoSaving}
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
              </div>
              )}

              {/* The anexo picker lives OUTSIDE the tab switch on purpose: its
                  trigger is on Documentos, and an input unmounted with the Geral
                  row could not be opened from there.

                  It had no trigger at all between 2026-08-19 and now — removing
                  the generic `Adicionar` button took the only thing that opened
                  it, and the comment that replaced it claimed the Anexos section
                  owned a trigger that was never written. Uploading was
                  unreachable in the UI for two days. `AnexosSection` now really
                  does own it. */}
              <input
                id="card-anexo-file-input"
                type="file"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) props.onUploadDocumento(file, props.tiposDocumento[0]?.tipo_documento ?? "outro");
                  e.target.value = "";
                }}
              />

              {/* The sidebar picks WHICH of these the middle pane shows.
                  Geral keeps what you act on continuously — etiquetas, the
                  description, the working checklists. Agendamentos and
                  Documentos each own a tab because each is a workflow of its
                  own, not a section you scroll past. */}
              {subpage === "geral" && (
                <>
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

                  <DescricaoSection
                    corpo={props.descricaoCorpo}
                    onSave={props.onSaveDescricao}
                    saving={props.descricaoSaving}
                  />

                  <ChecklistsSection
                    checklists={props.checklists}
                    loading={props.checklistsLoading}
                    onRemoveChecklist={props.onRemoveChecklist}
                    onAddItem={props.onAddItem}
                    onToggleItem={props.onToggleItem}
                    onRemoveItem={props.onRemoveItem}
                  />

                </>
              )}

              {subpage === "agendamentos" && (
                <AgendamentosSection
                  agendamentos={props.agendamentos ?? []}
                  loading={props.agendamentosLoading}
                  onRemove={props.onRemoveAgendamento}
                  acao={
                    <AgendamentoPopover
                      open={activePopover === "agendamento"}
                      onOpenChange={(o) => setActivePopover(o ? "agendamento" : null)}
                      onCreate={props.onCreateAgendamento}
                      saving={props.agendamentoSaving}
                    />
                  }
                />
              )}

              {subpage === "documentos" && (
                <>
                  {/* The permanent checklist sits ABOVE anexos: it is the list of
                      what must be COLLECTED, and the anexos below are what has
                      arrived. Reading order follows the work. */}
                  <DocumentoChecklistSection
                    items={props.documentoChecklist ?? []}
                    loading={props.documentoChecklistLoading}
                    onToggle={props.onToggleDocumentoChecklist}
                  />
                  <AnexosSection
                    documentos={props.documentos}
                    loading={props.documentosLoading}
                    uploading={props.uploadingDocumento}
                    onOpenDocumento={props.onOpenDocumento}
                    onDeleteDocumento={props.onDeleteDocumento}
                  />
                </>
              )}

              {(subpage === "cliente" || subpage === "campanha") && (
                <RecordSubpage sections={record[subpage]} subpage={subpage} />
              )}
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
  uploading,
  onOpenDocumento,
  onDeleteDocumento,
}: {
  documentos: Documento[];
  loading: boolean;
  uploading?: boolean;
  onOpenDocumento: (id: string) => void;
  onDeleteDocumento: (id: string, motivo: string) => void;
}) {
  return (
    <div className="mb-4" data-testid="anexos-section">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Anexos</p>
        {/* The section owns its trigger — the claim the old comment made and
            never delivered. It opens the hidden input the dialog keeps mounted
            outside the tab switch. */}
        <Button
          variant="outline"
          size="sm"
          disabled={uploading}
          onClick={() => document.getElementById("card-anexo-file-input")?.click()}
          data-testid="anexo-enviar-btn"
        >
          {uploading ? "Enviando…" : "Enviar anexo"}
        </Button>
      </div>
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

/**
 * The record behind the card, split into the two read-only subpages.
 *
 * Built from the SAME descriptors the Leads table and the detail dialog use
 * (`leadCardSubpages` / `campanhaCardSubpages`), and rendered by the SAME grid
 * organ (`DetailSections` in @noctusai/lib). A hand-written field list here
 * would drift from those two the first time a field is added — which is the
 * exact reason `leadDetailSections` exists.
 *
 * A card can carry SEVERAL atendimentos (D17 keeps closed deals as history), so
 * both lists are concatenated across them rather than showing only the first.
 */
function useRecordSections(atendimentos?: CardAtendimento[]): CardSubpageSections {
  return useMemo(() => {
    const out: CardSubpageSections = { cliente: [], campanha: [] };
    for (const atendimento of atendimentos ?? []) {
      const split = atendimento.lead
        ? leadCardSubpages(atendimento.lead as never)
        : atendimento.campanha
          ? campanhaCardSubpages(atendimento.campanha)
          : null;
      if (!split) continue;
      out.cliente.push(...split.cliente);
      out.campanha.push(...split.campanha);
    }
    // `DetailSections` drops a section whose every field is empty/hidden, but it
    // cannot drop the PAGE — so an all-empty split must read as empty here, or
    // the rail would offer a subpage that renders nothing.
    return {
      cliente: hasAnyField(out.cliente) ? out.cliente : [],
      campanha: hasAnyField(out.campanha) ? out.campanha : [],
    };
  }, [atendimentos]);
}

function hasAnyField(sections: DetailSection[]): boolean {
  return sections.some((section) => section.fields.some((field) => !field.hidden));
}

/** The two READ-ONLY record subpages. `geral`, `agendamentos` and `documentos`
 *  are workflows with their own components, not field grids. */
type RecordSubpageKey = Extract<CardSubpageKey, "cliente" | "campanha">;

const SUBPAGE_HEADING: Record<RecordSubpageKey, string> = {
  cliente: "Dados do cliente",
  campanha: "Campanha e imóvel",
};

function RecordSubpage({
  sections,
  subpage,
}: {
  sections: DetailSection[];
  subpage: RecordSubpageKey;
}) {
  return (
    <div data-testid={`card-subpage-${subpage}`}>
      <h3 className="mb-3 text-sm font-semibold">{SUBPAGE_HEADING[subpage]}</h3>
      {sections.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid={`card-subpage-${subpage}-empty`}>
          Nada registrado para este cartão.
        </p>
      ) : (
        <DetailSections sections={sections} testId={`card-subpage-${subpage}-fields`} />
      )}
    </div>
  );
}

const LEMBRETE_LABEL: Record<number, string> = {
  0: "na hora",
  5: "5 minutos antes",
  10: "10 minutos antes",
  15: "15 minutos antes",
  30: "30 minutos antes",
  60: "1 hora antes",
  120: "2 horas antes",
  1440: "1 dia antes",
  2880: "2 dias antes",
  10080: "1 semana antes",
};

function lembreteLabel(minutos: number): string {
  return LEMBRETE_LABEL[minutos] ?? `${minutos} minutos antes`;
}

const TIPO_LABEL: Record<string, string> = {
  visita: "Visita",
  ligacao: "Ligação",
  reuniao: "Reunião",
  outro: "Compromisso",
};

function AgendamentosSection({
  agendamentos,
  loading,
  onRemove,
  acao,
}: {
  agendamentos: Agendamento[];
  loading?: boolean;
  onRemove: (id: string) => void;
  /** The section's own trigger, rendered beside its heading. On its own tab
   *  the card-level action row is gone, so without this there is no way to
   *  book an appointment from the page that lists them. */
  acao?: ReactNode;
}) {
  // A LIST, not a slot. The card used to show one appointment because it could
  // only hold one; booking a second silently replaced the first.
  //
  // This owns a TAB now, so an empty list renders the heading and its trigger
  // rather than nothing. Returning null was right while this was one section
  // among several on Geral; on its own tab it would render a blank page with no
  // way to book the first appointment.
  if (loading) {
    return (
      <div className="mb-5" data-testid="agendamentos-loading">
        <div className="h-4 w-40 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const agora = Date.now();

  return (
    <div className="mb-5" data-testid="agendamentos-section">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Agendamentos
        </p>
        {acao}
      </div>
      {agendamentos.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="agendamentos-empty">
          Nenhum agendamento marcado.
        </p>
      ) : (
      <div className="space-y-2">
        {agendamentos.map((a) => {
          const passou = new Date(a.quando).getTime() < agora;
          return (
            <div
              key={a.id}
              className={cn(
                "rounded border px-3 py-2",
                // Past appointments stay visible — they are history, and D17
                // keeps history — but must not read as "coming up".
                passou && "opacity-60",
              )}
              data-testid={`agendamento-${a.id}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {TIPO_LABEL[a.tipo] ?? a.tipo} · {formatDate(a.quando, true)}
                  </p>
                  {a.lembrete_minutos_antes !== null && (
                    <p className="mt-0.5 text-xs text-muted-foreground" data-testid="agendamento-lembrete">
                      <Bell className="mr-1 inline h-3 w-3 align-[-1px]" />
                      Lembrete {lembreteLabel(a.lembrete_minutos_antes)}
                    </p>
                  )}
                  {a.nota && <p className="mt-1 text-sm text-muted-foreground">{a.nota}</p>}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => onRemove(a.id)}
                  aria-label="Remover agendamento"
                  data-testid={`agendamento-remover-${a.id}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>
      )}
    </div>
  );
}

/**
 * The permanent document checklist — the six identity fields every lead owes us
 * once they become a client.
 *
 * There is no add/remove: the list is the SAME for every client by definition,
 * so it is defined server-side once (`documento_checklist_service.ITENS`).
 *
 * Ticks are DERIVED (migration 068): an item is done when the client record
 * carries the field or the document has been uploaded. Nothing here posts a
 * tick when data arrives — the next read simply reflects it, which is what
 * makes every ingestion channel (Meta, OLX, ImovelWeb, Vista, import, manual)
 * covered without any of them knowing this list exists.
 *
 * So a checkbox here is an OVERRIDE control, not the state itself. Clicking it
 * asserts a human opinion; the ↩ button beside an overridden item withdraws
 * that opinion and hands the item back to the data. Without that affordance
 * the first click on an item would pin it forever.
 */
function DocumentoChecklistSection({
  items,
  loading,
  onToggle,
}: {
  items: DocumentoChecklistItem[];
  loading?: boolean;
  onToggle: (key: string, concluido: boolean | null) => void;
}) {
  if (loading) {
    return (
      <div className="mb-5" data-testid="documento-checklist-loading">
        <div className="h-4 w-48 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const done = items.filter((i) => i.concluido).length;
  const pct = items.length ? Math.round((done / items.length) * 100) : 0;

  return (
    <div className="mb-5" data-testid="documento-checklist-section">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Dados obrigatórios
        </p>
        <span className="text-xs text-muted-foreground" data-testid="documento-checklist-progresso">
          {done}/{items.length}
        </span>
      </div>
      <Progress value={pct} className="mb-2 h-1.5" />
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 shrink-0 rounded border-muted-foreground/40"
              checked={item.concluido}
              onChange={(e) => onToggle(item.key, e.target.checked)}
              data-testid={`documento-checklist-${item.key}`}
              aria-label={item.label}
            />
            <span className={cn(item.concluido && "text-muted-foreground line-through")}>
              {item.label}
            </span>
            {item.origem === "manual" && (
              <>
                {/* An overridden item says so. A tick that disagrees with the
                    record is exactly the one a reader must not mistake for
                    evidence that the data is there. */}
                <span
                  className="rounded bg-muted px-1 text-[10px] uppercase tracking-wide text-muted-foreground"
                  title={
                    item.derivado === item.concluido
                      ? "Marcado manualmente"
                      : `Marcado manualmente — os dados indicam "${
                          item.derivado ? "preenchido" : "pendente"
                        }"`
                  }
                  data-testid={`documento-checklist-${item.key}-manual`}
                >
                  manual
                </span>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onToggle(item.key, null)}
                  title="Voltar a seguir os dados"
                  aria-label={`Voltar ${item.label} a seguir os dados`}
                  data-testid={`documento-checklist-${item.key}-limpar`}
                >
                  ↩
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
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
