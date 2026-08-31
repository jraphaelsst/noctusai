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
 * out. Zero imports from `@/pages/**`-owned data — the smart wrapper
 * (`@/components/ClienteDetailModal.tsx`, outside `card/**`) owns
 * `useCardHub` and feeds this component.
 *
 * States: loading / error / success at the dialog level (there is no
 * meaningful "empty" state for a single record — a missing record is
 * `notFound`, handled like an error).
 *
 * ─── The 2026-08 remodel ────────────────────────────────────────────────
 *
 * 🔴 GERAL ABSORBED THE DOCUMENTOS TAB. Collecting a document is not a
 * separate errand from working the card — it IS the work — and splitting it
 * off meant reading "RG pendente" on one screen and supplying it on another.
 * Geral now reads top to bottom as the job: who this is (etiquetas, the
 * contact line), what was said (descrição), what is still owed (the
 * mandatory rows, then the operator's own extras), whose paperwork it is
 * (each party's panel, then the anexos), and finally the working checklists.
 *
 * 🔴 EVERY ACTION IS AN ICON WITH ITS CAPTION ON HOVER — and with the SAME
 * string as its `aria-label`, because a hover caption is invisible to a
 * screen reader and to a keyboard. `TooltipIconButton` cannot be built
 * without a label, so that pairing is structural rather than remembered.
 * The two places that KEPT their words are documented where they are: the
 * extracted-value Confirmar/Descartar pair (icons there would be confirmed
 * by reflex, which is the failure that whole path exists to prevent) and
 * the comment composer's post action.
 *
 * 🔴 THE SECTIONS LEFT THIS FILE. It was 1691 lines and was additionally
 * acting as a module barrel for two components `PessoaDocumentosPanel`
 * imported. `DocumentoChecklistSection`, `AnexosSection`, the row and the
 * extras listing are now their own files under `card/`.
 */
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  AlertCircle,
  Bell,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Mail,
  MoreHorizontal,
  Pencil,
  Phone,
  Plus,
  Trash2,
  User as UserIcon,
  UserPlus,
  X,
} from "lucide-react";

import { DetailSections } from "@noctusai/lib/components";
import type { DetailSection } from "@noctusai/lib/components";
import {
  campanhaCardSubpages,
  contatoValue,
  leadCardSubpages,
} from "@/pages/leads/leadDetailSections";
import type { CardSubpageSections } from "@/pages/leads/leadDetailSections";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import {
  DadosPessoaisForm,
  type DadosPessoais,
} from "@/components/card/DadosPessoaisForm";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type {
  Agendamento,
  AgendamentoCreateBody,
  CardAtendimento,
  ChecklistExtra,
  ChecklistExtraTipo,
  Comprador,
  Checklist,
  Documento,
  DocumentoChecklistItem,
  ExtracaoSugestao,
  Membro,
  Roteiro,
  StatusVisita,
  Tag,
  TimelineEntry,
  TipoDocumento,
} from "@/types/cardHub";

import { Timeline } from "./Timeline";
import { ChecklistDialog } from "./popovers/ChecklistDialog";
import { AgendamentoPopover } from "./popovers/AgendamentoPopover";
import { CardSidebarNav } from "./CardSidebarNav";
import { RoteirosSection } from "./RoteirosSection";
import type { CardSubpageKey } from "./CardSidebarNav";
import { EtiquetasPopover } from "./popovers/EtiquetasPopover";
import { MembrosPopover } from "./popovers/MembrosPopover";
import { AnexosSection } from "./AnexosSection";
import { ChecklistExtrasSection } from "./ChecklistExtrasSection";
import { DocumentoChecklistSection } from "./DocumentoChecklistSection";
import { TokenCheckbox } from "./TokenCheckbox";
import { TooltipIconButton } from "./TooltipIconButton";

type PopoverKey = "etiquetas" | "agendamento" | "checklist" | "membros" | null;

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

  // ─── Compradores / partes do atendimento (migration 073) ───────────────
  /**
   * The OTHER people party to this atendimento. The titular is not in here —
   * they are the card — so an empty list is the ordinary single-buyer case and
   * the Compradores block hides itself entirely.
   */
  compradores?: Comprador[];
  compradoresLoading?: boolean;
  onAdicionarComprador?: () => void;
  onRemoverComprador?: (parteId: string) => void;
  /**
   * Renders one party's OWN checklist + documents panel.
   *
   * A render prop rather than data, because each party's panel needs its own
   * queries keyed by THEIR `cliente_id`, and this component is presentational
   * — it is rendered in tests with plain objects and no query client. The
   * container owns the fetching; this file owns the collapsible chrome and the
   * order people appear in.
   */
  renderDocumentosDePessoa?: (clienteId: string) => ReactNode;

  /**
   * The Negociação and Financiamento/Escritura subpages.
   *
   * Render props for the same reason `renderDocumentosDePessoa` is one: both
   * need their own queries and mutations, and this component is presentational
   * — it is rendered in tests with plain objects and no query client. Thunks,
   * not elements, so a subpage nobody has opened costs nothing.
   */
  renderNegociacao?: () => ReactNode;
  renderFinanciamento?: () => ReactNode;

  /** Current values behind the typed checklist items — read by the inline row
   *  editors AND by the full form on the Dados do cliente tab. */
  dadosPessoais?: DadosPessoais;
  onSaveDadosPessoais?: (valores: DadosPessoais) => void;
  dadosPessoaisSaving?: boolean;
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

  // Roteiros (migration 082) — the qualificação → visita funnel. The Agendar
  // button no longer offers "Visita"; a visit is a roteiro entry now, because
  // only that can hold several properties, an order, and an outcome.
  roteiros?: Roteiro[];
  roteirosLoading?: boolean;
  /** A fetch is in flight AND `roteiros` already has rows — never unmounts
   *  the list (`KB § PATTERNS/frontend/lying-loading-state.md`). */
  roteirosRefreshing?: boolean;
  roteirosError?: string | null;
  onCriarRoteiro: () => void;
  onRemoverRoteiro: (roteiroId: string) => void;
  onGerarRoteiroPdf: (roteiroId: string) => void;
  onPatchVisita: (
    roteiroId: string,
    visitaId: string,
    body: { status?: StatusVisita; observacao?: string | null },
  ) => void;
  roteiroPdfPendingId?: string | null;

  // Membros
  allMembros: Membro[];
  selectedMembros: Membro[];
  onToggleMembro: (membroId: string) => void;
  membrosSaving?: boolean;

  // Descrição — derived by the container from the card's single description
  // note (see the container's docblock for the `tipo` discriminator).
  descricaoCorpo: string;
  onSaveDescricao: (corpo: string) => void;
  descricaoSaving?: boolean;

  // Documento checklist — the identity fields every new client owes us.
  // The LIST is canonical server-side, so there is no create/remove here.
  documentoChecklist?: DocumentoChecklistItem[];
  /** Extracted fields that are not checklist items — today `nome_oficial`. */
  sugestoesExtras?: Record<string, ExtracaoSugestao>;
  nomeOficial?: string | null;
  nomeRegistro?: string | null;
  documentoChecklistLoading?: boolean;
  /** A fetch is in flight AND `documentoChecklist` already has rows — never
   *  unmounts the section (`KB § PATTERNS/frontend/lying-loading-state.md`). */
  documentoChecklistRefreshing?: boolean;
  onToggleDocumentoChecklist: (key: string, concluido: boolean | null) => void;
  /** Uploads the file that satisfies `rg` / `cpf`, filed under that item's key
   *  as its `tipo_documento` — the row IS the type. */
  onUploadDocumentoChecklist?: (item: DocumentoChecklistItem, file: File) => void;
  /** Discards that file. The ROW stays: the mandatory list is server-defined
   *  and there is no such thing as deleting "CPF" from it. */
  onRemoverDocumentoChecklist?: (
    documentoId: string,
    item: DocumentoChecklistItem,
  ) => void;
  onResolverSugestao?: (
    documentoId: string,
    acao: "confirmar" | "descartar",
    itemKey: string,
  ) => void;
  sugestaoSaving?: boolean;

  // Checklist extras — the rows the OPERATOR creates, beside the mandatory
  // ones. Separate props (not folded into `documentoChecklist`) because the
  // two lists differ in every operation: these are created, renamed and
  // destroyed by the person using the card.
  checklistExtras?: ChecklistExtra[];
  checklistExtrasLoading?: boolean;
  /** A fetch is in flight AND `checklistExtras` already has rows — never
   *  unmounts the list (`KB § PATTERNS/frontend/lying-loading-state.md`). */
  checklistExtrasRefreshing?: boolean;
  checklistExtrasError?: string | null;
  onCriarChecklistExtra?: (body: { label: string; tipo: ChecklistExtraTipo }) => void;
  onRenomearChecklistExtra?: (extraId: string, label: string) => void;
  onSalvarTextoChecklistExtra?: (extraId: string, valorTexto: string) => void;
  onRemoverChecklistExtra?: (extraId: string) => void;
  onUploadChecklistExtra?: (extraId: string, file: File) => void;
  onRemoverDocumentoChecklistExtra?: (extraId: string) => void;
  checklistExtrasSaving?: boolean;

  // Anexos
  documentos: Documento[];
  documentosLoading: boolean;
  /** A fetch is in flight AND `documentos` already has rows — never unmounts
   *  the list (`KB § PATTERNS/frontend/lying-loading-state.md`). */
  documentosRefreshing?: boolean;
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

  /**
   * The tab the user just opened.
   *
   * 🔴 Exists so the owner can fetch that tab's data ON DEMAND. Opening a card
   * fired eight parallel reads — resumo, timeline, checklists, documentos,
   * documento-checklist, agendamentos, compradores, negociação, financiamento
   * — several taking 1,4–2,4 s in production, for panels the person may never
   * open. Only this component knows which tab is active, so only it can say.
   *
   * Still fired after the Documentos tab was absorbed into Geral: the tabs
   * that remain (agendamentos, roteiros, negociação, financiamento) are still
   * fetched on first open. What CHANGED is that documentos + the required-data
   * checklist are now Geral's, and Geral is the open-on-mount tab — so those
   * two are read when the card opens. That is the cost of putting the work on
   * the first screen, and it is paid deliberately.
   */
  onSubpageChange?: (key: CardSubpageKey) => void;
}

export function ClienteCardDialog(props: ClienteCardDialogProps) {
  const { open, onClose, isLoading, error, notFound, nome, acoes } = props;
  const [activePopover, setActivePopover] = useState<PopoverKey>(null);
  // `geral` is the open-on-mount subpage: the card is opened to DO something
  // far more often than to read the record behind it.
  const [subpage, setSubpage] = useState<CardSubpageKey>("geral");

  // 🔴 Reported upward so the owner can fetch a tab's data WHEN IT IS OPENED.
  function selecionar(key: CardSubpageKey) {
    setSubpage(key);
    props.onSubpageChange?.(key);
  }
  const record = useRecordSections(props.atendimentos);
  const emptyKeys = useMemo(
    () =>
      [
        record.cliente.length ? null : "cliente",
        record.campanha.length ? null : "campanha",
      ].filter(Boolean) as CardSubpageKey[],
    [record],
  );

  const compradores = props.compradores ?? [];

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {/*
        90vh × 90vw. The card carries three panes and the middle one now holds
        everything the Documentos tab used to; at `max-w-6xl` the checklist
        rows wrapped and the comment pane was a column of two-word lines.

        The rail's column is the rail's COLLAPSED width and stays that width
        while it is open — see `CardSidebarNav`: the expansion floats over the
        middle pane rather than squeezing it.
      */}
      <DialogContent
        className={cn(
          "grid h-[90vh] w-[90vw] max-w-[90vw] grid-cols-1 gap-0 overflow-hidden p-0",
          "md:grid-cols-[3.25rem_1fr_360px]",
        )}
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

            {/* ── Left rail — subpage navigation (hover rail) ─────── */}
            <CardSidebarNav active={subpage} onSelect={selecionar} emptyKeys={emptyKeys} />

            {/* ── Middle pane — the active subpage ────────────────── */}
            <ScrollArea className="border-r p-6">
              <div className="mb-4 flex items-start justify-between gap-3">
                <h2 className="text-xl font-semibold">{nome}</h2>
                {/* Top-right action row. `acoes` is whatever board opened the
                    card (its own buttons); "Adicionar Comprador" is card-level
                    and belongs beside them rather than buried in a tab,
                    because "this buyer is married" is discovered while reading
                    anything on the card. */}
                <div className="flex shrink-0 items-center gap-1">
                  {props.onAdicionarComprador && (
                    <TooltipIconButton
                      label="Adicionar Comprador"
                      icon={UserPlus}
                      variant="outline"
                      testId="adicionar-comprador-btn"
                      onClick={props.onAdicionarComprador}
                    />
                  )}
                  {acoes}
                </div>
              </div>

              {/* The action row belongs to Geral. It was card-level chrome while
                  Geral held everything; a row of quick-actions floating above an
                  unrelated tab is just noise. Each other tab carries its own
                  trigger instead — the specific button next to the thing it
                  acts on, which is the same rule that retired `Adicionar`. */}
              {subpage === "geral" && (
              <div className="mb-4 flex flex-wrap gap-1">
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

              {/* ── GERAL ──────────────────────────────────────────
                  The order below is the brief's, and it is the order the work
                  happens in: who this is, what was said, what is still owed,
                  whose paperwork it is, and only then the ad-hoc lists. */}
              {subpage === "geral" && (
                <>
                  {/* a. Etiquetas — only when set. An empty heading on every
                         card would be furniture that means nothing. */}
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

                  {/* b. The contact line. Three one-line rows, above
                         everything, because they are what an operator reads
                         BEFORE picking up the phone — and reaching them used
                         to mean opening the Dados do cliente tab. */}
                  <ContatoResumo
                    dados={props.dadosPessoais}
                    origem={contatoDeOrigem(props.atendimentos)}
                  />

                  {/* c. Descrição */}
                  <DescricaoSection
                    corpo={props.descricaoCorpo}
                    onSave={props.onSaveDescricao}
                    saving={props.descricaoSaving}
                  />

                  {/* d. The mandatory checklist, as unified one-line rows. */}
                  <DocumentoChecklistSection
                    items={props.documentoChecklist ?? []}
                    loading={props.documentoChecklistLoading}
                    refreshing={props.documentoChecklistRefreshing}
                    onToggle={props.onToggleDocumentoChecklist}
                    onResolverSugestao={props.onResolverSugestao}
                    sugestaoSaving={props.sugestaoSaving}
                    sugestoesExtras={props.sugestoesExtras}
                    nomeOficial={props.nomeOficial}
                    nomeRegistro={props.nomeRegistro}
                    valores={props.dadosPessoais}
                    onSaveCampo={props.onSaveDadosPessoais}
                    savingCampo={props.dadosPessoaisSaving}
                    onUploadDocumento={props.onUploadDocumentoChecklist}
                    onRemoverDocumento={props.onRemoverDocumentoChecklist}
                    uploading={props.uploadingDocumento}
                  />

                  {/* e. The operator's own rows. */}
                  {props.onCriarChecklistExtra && (
                    <ChecklistExtrasSection
                      items={props.checklistExtras ?? []}
                      loading={props.checklistExtrasLoading}
                      refreshing={props.checklistExtrasRefreshing}
                      error={props.checklistExtrasError}
                      onCriar={props.onCriarChecklistExtra}
                      criando={props.checklistExtrasSaving}
                      onRenomear={props.onRenomearChecklistExtra ?? (() => {})}
                      onSalvarTexto={props.onSalvarTextoChecklistExtra ?? (() => {})}
                      onRemover={props.onRemoverChecklistExtra ?? (() => {})}
                      onUploadDocumento={props.onUploadChecklistExtra ?? (() => {})}
                      onRemoverDocumento={
                        props.onRemoverDocumentoChecklistExtra ?? (() => {})
                      }
                      salvando={props.checklistExtrasSaving}
                    />
                  )}

                  {/* f. Everyone ELSE's paperwork, then this person's files.
                         🔴 ONE PANEL PER PERSON, and the titular is not one of
                         them — the titular IS the card, and their checklist is
                         the section above. Every other party needs the same
                         items and the same uploads, which is the whole reason
                         a comprador is a `clientes` row.

                         Collapsible because a married buyer means one extra
                         panel, a fiador two, and their queries only run when
                         opened. */}
                  {compradores.length > 0 && (
                    <div className="mb-4" data-testid="compradores-section">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Compradores
                      </p>
                      {compradores.map((parte) => (
                        <PessoaDocumentosSection
                          key={parte.id}
                          nome={nomeDaParte(parte)}
                          papel={PAPEL_LABEL[parte.papel] ?? parte.papel}
                          testId={`comprador-${parte.id}`}
                          acao={
                            props.onRemoverComprador && (
                              <TooltipIconButton
                                label={`Remover ${nomeDaParte(parte)} deste atendimento`}
                                icon={Trash2}
                                testId={`comprador-remover-${parte.id}`}
                                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                                onClick={() => props.onRemoverComprador?.(parte.id)}
                              />
                            )
                          }
                        >
                          {() => props.renderDocumentosDePessoa?.(parte.cliente_id) ?? null}
                        </PessoaDocumentosSection>
                      ))}
                    </div>
                  )}

                  <AnexosSection
                    documentos={props.documentos}
                    loading={props.documentosLoading}
                    refreshing={props.documentosRefreshing}
                    uploading={props.uploadingDocumento}
                    onUpload={(file) =>
                      props.onUploadDocumento(
                        file,
                        props.tiposDocumento[0]?.tipo_documento ?? "outro",
                      )
                    }
                    onOpenDocumento={props.onOpenDocumento}
                    onDeleteDocumento={props.onDeleteDocumento}
                  />

                  {/* g. The user-created working checklists — last, and only
                         when there are any. */}
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

              {subpage === "roteiros" && (
                <RoteirosSection
                  roteiros={props.roteiros ?? []}
                  loading={props.roteirosLoading}
                  refreshing={props.roteirosRefreshing}
                  error={props.roteirosError}
                  onCriar={props.onCriarRoteiro}
                  onRemover={props.onRemoverRoteiro}
                  onGerarPdf={props.onGerarRoteiroPdf}
                  onPatchVisita={props.onPatchVisita}
                  pdfPendingId={props.roteiroPdfPendingId}
                />
              )}

              {subpage === "financiamento" && (
                <div data-testid="card-subpage-financiamento">
                  {props.renderFinanciamento?.() ?? (
                    <p className="text-sm text-muted-foreground">
                      Financiamento indisponível.
                    </p>
                  )}
                </div>
              )}

              {subpage === "negociacao" && (
                <div data-testid="card-subpage-negociacao">
                  {props.renderNegociacao?.() ?? (
                    <p className="text-sm text-muted-foreground">
                      Negociação indisponível.
                    </p>
                  )}
                </div>
              )}

              {/* 🔴 The Dados do cliente tab is no longer read-only. It showed
                  what the record holds and offered nowhere to change it, so
                  correcting a mistyped email meant leaving the card. The
                  editor is `DadosPessoaisForm` — the SAME form each party's
                  panel uses, writing through the SAME `onSaveDadosPessoais`
                  path the inline rows use. A second editor for one set of
                  columns would be two ways to write the same value, and one
                  of them would be wrong first. */}
              {subpage === "cliente" && props.onSaveDadosPessoais && (
                <DadosPessoaisForm
                  valores={props.dadosPessoais ?? {}}
                  onSave={props.onSaveDadosPessoais}
                  saving={props.dadosPessoaisSaving}
                />
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

/**
 * How a party's role reads on screen. Keys mirror
 * `compradores_service.PAPEIS`; an unmapped value falls through to the raw
 * string rather than rendering blank, so a role added on the server shows up
 * as itself until someone gives it a label.
 */
const PAPEL_LABEL: Record<string, string> = {
  comprador: "Comprador",
  conjuge: "Cônjuge",
  fiador: "Fiador",
  procurador: "Procurador",
  outro: "Outro",
};

/**
 * The best name we hold for a party.
 *
 * Same precedence the checklist uses — the explicit `nome_completo` first,
 * then whatever the channel supplied. The fallback is a visible placeholder
 * rather than an empty string: a nameless collapsed row is unclickable in
 * practice because there is nothing to read on it.
 */
function nomeDaParte(parte: Comprador): string {
  return (
    parte.cliente?.nome_completo?.trim() ||
    parte.cliente?.nome?.trim() ||
    "Sem nome"
  );
}

/**
 * The three fields an operator reads before doing anything else, as one-line
 * rows at the top of Geral.
 *
 * They also appear as editable rows in the mandatory checklist below, and that
 * is not a duplicate: there they answer "is this still owed?", here they
 * answer "what is it?". Read-only on purpose — the checklist row is the ONE
 * place a value is edited, so the two can never disagree about how a write
 * happens.
 */
/**
 * What the ORIGIN records know about how to reach this person.
 *
 * 🔴 WHY THIS FALLBACK EXISTS (found by live-testing prod, 2026-08-27).
 * --------------------------------------------------------------------
 * `dadosPessoais` comes off the document checklist's `valores`, which reads
 * ONLY `clientes` columns — deliberately, and `documento_checklist_service`
 * argues that at length: a tick must mean "the client RECORD holds this".
 *
 * But most cards arrive from a campaign, and for those the contact lives on
 * the `leads` row while `clientes.celular` / `chave_canonica` stay null. On a
 * real prod card the summary therefore rendered "CELULAR —" while the funil
 * card DIRECTLY BEHIND IT displayed that person's phone number. The data was
 * there; this panel just wasn't looking where it lived.
 *
 * That is a lying readout of the same family as `check_lying_loading_state`:
 * rendering "we don't have this" over something we demonstrably have.
 *
 * Reuses `contatoValue` — the canonical reader that already discriminates
 * email-vs-phone off `contato_tipo` and applies `formatPhone` — rather than
 * re-deriving the rule here. Most recent atendimento wins; older ones are
 * likelier to carry a stale number.
 */
function contatoDeOrigem(atendimentos?: CardAtendimento[]): DadosPessoais {
  const origem: DadosPessoais = {};
  // Oldest → newest, so the newest non-empty value ends up winning.
  const ordenados = [...(atendimentos ?? [])].sort((a, b) =>
    (a.created_at ?? "").localeCompare(b.created_at ?? ""),
  );
  for (const at of ordenados) {
    // 🔴 BOTH origin shapes, not just `lead`. A card is spawned from a portal
    // lead OR from a Meta campaign, never both — and the two projections carry
    // contact differently: `leads` has ONE `contato` discriminated by
    // `contato_tipo`, while `meta_ads_leads` has separate `phone` and `email`
    // columns. Reading only `lead` missed every campaign-sourced card, which
    // on this board is most of them; caught by live-testing a real card whose
    // Dados tab showed a phone AND an email that Geral rendered as "—".
    const lead = at.lead;
    if (lead) {
      const valor = contatoValue(lead);
      if (valor) {
        if (lead.contato_tipo === "email") origem.email = valor;
        else origem.celular = valor;
      }
      if (lead.cliente_nome?.trim()) origem.nome_completo = lead.cliente_nome.trim();
    }

    const campanha = at.campanha;
    if (campanha) {
      // `phone` is canonical E.164 since migration 037, but still rendered
      // through the same seam so the card never shows a differently-formatted
      // number than the leads table does.
      const telefone = campanha.phone
        ? contatoValue({ contato: campanha.phone, contato_tipo: "telefone" })
        : null;
      if (telefone) origem.celular = telefone;
      if (campanha.email?.trim()) origem.email = campanha.email.trim().toLowerCase();
      if (campanha.full_name?.trim()) origem.nome_completo = campanha.full_name.trim();
    }
  }
  return origem;
}

function ContatoResumo({
  dados,
  origem,
}: {
  dados?: DadosPessoais;
  /** Contact the ORIGIN records carry, used only where the client record is
   *  blank. See `contatoDeOrigem`. */
  origem?: DadosPessoais;
}) {
  const linhas: {
    icon: typeof UserIcon;
    rotulo: string;
    valor?: string | null;
    /** True when the value came from the origin record, not the client one. */
    herdado: boolean;
  }[] = (
    [
      ["Nome", UserIcon, dados?.nome_completo, origem?.nome_completo],
      ["Celular", Phone, dados?.celular, origem?.celular],
      ["Email", Mail, dados?.email, origem?.email],
    ] as const
  ).map(([rotulo, icon, proprio, herdado]) => ({
    icon,
    rotulo,
    // Precedence is explicit-first, mirroring the backend's `campos` order: an
    // operator-typed value outranks whatever the channel supplied.
    valor: proprio || herdado,
    herdado: !proprio && Boolean(herdado),
  }));

  return (
    <dl className="mb-4 space-y-1" data-testid="contato-resumo">
      {linhas.map(({ icon: Icon, rotulo, valor, herdado }) => (
        <div
          key={rotulo}
          className="flex items-center gap-2 text-sm"
          data-testid={`contato-${rotulo.toLowerCase()}`}
        >
          <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <dt className="w-16 shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
            {rotulo}
          </dt>
          {/* An absent value says so rather than rendering an empty cell — a
              blank beside a label reads as a rendering bug, not as missing
              data. */}
          <dd className={cn("min-w-0 truncate", !valor && "text-muted-foreground")}>
            {valor || "—"}
          </dd>
          {/* 🔴 An inherited value is LABELLED, not silently promoted. The
              checklist beneath still reads this item as pending, because the
              client record genuinely does not hold it yet — and without this
              tag those two would look like they contradict each other. With
              it, they read as what they are: "we know it from the campaign,
              nobody has put it on the record". */}
          {herdado && (
            <span
              className="shrink-0 rounded bg-muted px-1 text-[10px] uppercase tracking-wide text-muted-foreground"
              title="Veio do cadastro de origem (campanha/portal); ainda não está no registro do cliente"
              data-testid={`contato-${rotulo.toLowerCase()}-herdado`}
            >
              origem
            </span>
          )}
        </div>
      ))}
    </dl>
  );
}

/**
 * One person's collapsible block of checklist + documents.
 *
 * 🔴 The children are rendered ONLY while open, and that is load-bearing
 * rather than cosmetic: a party's panel runs its own queries against their
 * `cliente_id`, so mounting three collapsed panels would fire three checklist
 * fetches and three document fetches for panels nobody is looking at. Opening
 * is what asks for the data.
 */
function PessoaDocumentosSection({
  nome,
  papel,
  defaultOpen = false,
  testId,
  acao,
  children,
}: {
  nome: string;
  papel: string;
  defaultOpen?: boolean;
  testId: string;
  /** Rendered in the header, beside the role badge — today the detach button.
   *  Outside the toggle so clicking it does not also expand the panel. */
  acao?: ReactNode;
  /**
   * A FUNCTION, not a node. JSX children are evaluated by the caller before
   * this component ever runs, so `{open && children}` would still have built
   * every collapsed party's subtree. Taking a thunk means a closed section
   * costs literally nothing — which is the point, since each party's panel
   * opens its own queries.
   */
  children: () => ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className="mb-2 rounded-lg border"
      data-testid={`pessoa-documentos-${testId}`}
    >
      <div className="flex items-center gap-2 pr-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/50"
          data-testid={`pessoa-documentos-toggle-${testId}`}
        >
          {open ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate text-sm font-semibold">{nome}</span>
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {papel}
          </span>
        </button>
        {acao}
      </div>
      {open && (
        <div className="border-t px-3 pb-3 pt-3" data-testid={`pessoa-documentos-corpo-${testId}`}>
          {children()}
        </div>
      )}
    </div>
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
          // Icon-only, but NOT label-less: `aria-label` + the hover caption
          // carry the word "Editar", so trading the visible text for space
          // does not trade away what the button does.
          <TooltipIconButton
            label="Editar descrição"
            icon={Pencil}
            testId="descricao-editar-btn"
            className="h-7 w-7"
            onClick={() => {
              setDraft(corpo);
              setEditing(true);
            }}
          />
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
          <div className="flex gap-1">
            <TooltipIconButton
              label="Salvar descrição"
              icon={Check}
              testId="descricao-salvar-btn"
              variant="default"
              className="h-8 w-8"
              disabled={saving}
              onClick={() => {
                onSave(draft);
                setEditing(false);
              }}
            />
            <TooltipIconButton
              label="Cancelar"
              icon={X}
              testId="descricao-cancelar-btn"
              className="h-8 w-8"
              onClick={() => setEditing(false)}
            />
          </div>
        </div>
      ) : corpo ? (
        <>
          <p className="whitespace-pre-wrap break-words text-sm">{shown}</p>
          {isLong && (
            <TooltipIconButton
              label={expanded ? "Mostrar menos" : "Mostrar mais"}
              icon={expanded ? ChevronUp : ChevronDown}
              testId="descricao-mostrar-mais"
              variant="outline"
              className="mt-2 h-7 w-7"
              onClick={() => setExpanded((v) => !v)}
            />
          )}
        </>
      ) : (
        <p className="text-sm italic text-muted-foreground">Sem descrição ainda.</p>
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
        <TooltipIconButton
          label={`Excluir checklist ${checklist.titulo}`}
          icon={Trash2}
          testId={`checklist-excluir-${checklist.id}`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={onRemove}
        />
      </div>
      <div className="mb-2 flex items-center gap-2">
        <span className="w-9 text-xs text-muted-foreground">{percent}%</span>
        <Progress value={percent} className="h-2 flex-1" />
      </div>
      <ul className="space-y-1">
        {checklist.itens.map((item) => (
          <li key={item.id} className="group flex items-center gap-2">
            <TokenCheckbox
              checked={item.concluido}
              onCheckedChange={(c) => onToggleItem(item.id, c)}
              label={item.texto}
              testId={`checklist-item-checkbox-${item.id}`}
            />
            <span className={cn("flex-1 text-sm", item.concluido && "text-muted-foreground line-through")}>
              {item.texto}
            </span>
            <button
              type="button"
              onClick={() => onRemoveItem(item.id)}
              aria-label={`Remover ${item.texto}`}
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
          aria-label={`Adicionar um item em ${checklist.titulo}`}
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
        <TooltipIconButton
          label="Adicionar item"
          icon={Plus}
          testId={`checklist-adicionar-item-${checklist.id}`}
          variant="outline"
          className="h-8 w-8"
          onClick={() => {
            if (!novoItem.trim()) return;
            onAddItem(novoItem.trim());
            setNovoItem("");
          }}
        />
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

/** The two READ-ONLY record subpages. `geral`, `agendamentos` and `roteiros`
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
                <TooltipIconButton
                  label="Remover agendamento"
                  icon={Trash2}
                  testId={`agendamento-remover-${a.id}`}
                  className="h-7 w-7"
                  onClick={() => onRemove(a.id)}
                />
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
 * 🔴 The comment composer's post action KEPT ITS WORDS.
 *
 * The brief removed the text from every button in the card and put it on
 * hover — with two exceptions, and this is one. The composer's button appears
 * only once something has been typed, and at that moment it is the whole
 * point of the box below it. A bare glyph beside a filled textarea does not
 * say whether it posts, saves a draft or clears — and this is the one control
 * whose misfire is public: a half-written note lands on the client's activity
 * feed for the whole team to read.
 */
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
