/**
 * ClienteCardDialog — SW's lead card, a THIN ADAPTER over the seed card hub.
 * PROJECT.md §4 · `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * §1/§2 (Slice F).
 *
 * 🔴 THE CHROME IS THE SEED'S. The 3-pane dialog (rail · subpage · activity),
 * its four states, the hover rail, Geral's generic spine (etiquetas chips,
 * descrição, anexos, working checklists), the quick-action row, the comment
 * composer and the timeline all live in `@noctusai/lib/components`
 * (`CardHubDialog`, `GeralSubpage`, `GeralActions`, …) — MOVED there from this
 * file, not rewritten, so desktop markup, classes and data-testids are
 * unchanged and `ClienteCardDialog.test.tsx` passes untouched.
 *
 * What stays HERE is only what is SW's:
 *   - the subpage REGISTRY (`cardSubpages.ts`) paired with each entry's
 *     `render` — Dados do cliente, Vendedor, Agendamentos, Roteiros,
 *     Financiamento/Escritura, Negociação, Contratos, Campanha e imóvel;
 *   - Geral's SW slots: the contact line after the tags, the Dados
 *     obrigatórios fold after the descrição, each party's paperwork before the
 *     anexos;
 *   - the Agendar popover, mounted after Etiquetas through `afterEtiquetas`
 *     and sharing ONE controlled "which popover is open" state with the
 *     Agendamentos tab's own trigger;
 *   - the header actions (Adicionar Comprador + whatever board opened the card);
 *   - SW's timeline kind registry (`SW_TIMELINE_RENDERERS`, incl. `touch`).
 *
 * The PROPS are unchanged (the adapter contract): the smart wrapper
 * (`@/components/ClienteDetailModal.tsx`) owns `useCardHub` and feeds this
 * component; presentational only (S3, §0) — props in, callbacks out.
 *
 * 🔴 GERAL ABSORBED THE DOCUMENTOS TAB (2026-08 remodel). Collecting a
 * document is not a separate errand from working the card — it IS the work.
 * Geral reads top to bottom as the job: who this is (etiquetas, the contact
 * line), what was said (descrição), what is still owed (the mandatory rows,
 * then the operator's own extras), whose paperwork it is (each party's panel,
 * then the anexos), and finally the working checklists.
 *
 * 🔴 EVERY ACTION IS AN ICON WITH ITS CAPTION ON HOVER — and the SAME string
 * as its `aria-label` (`TooltipIconButton` cannot be built without a label).
 */
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { Archive, Bell, Loader2, Mail, Phone, Plus, Trash2, User as UserIcon, UserPlus } from "lucide-react";

import {
  CardHubDialog,
  CollapsibleSection,
  DetailSections,
  GeralActions,
  GeralSubpage,
  TooltipIconButton,
  ChecklistExtrasSection,
} from "@noctusai/lib/components";
import type {
  CardHubRenderCtx,
  CardSubpage,
  DetailSection,
  GeralPopoverKey,
  TimelineEntry as CardHubTimelineEntry,
} from "@noctusai/lib/components";
import {
  campanhaCardSubpages,
  contatoValue,
  leadCardSubpages,
} from "@/pages/leads/leadDetailSections";
import type { CardSubpageSections } from "@/pages/leads/leadDetailSections";
import { Button } from "@/components/ui/button";
import {
  DadosPessoaisForm,
  type DadosPessoais,
} from "@/components/card/DadosPessoaisForm";
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
  VisitaPropostaBody,
} from "@/types/cardHub";
// A VALUE, not a type — the two role vocabularies mirror
// `compradores_service.PAPEIS_POR_LADO`, and the select offers exactly what
// the API will accept. Re-listing them here would be the second copy that
// drifts.
import { PAPEIS_POR_LADO } from "@/types/cardHub";

import { AgendamentoPopover } from "./popovers/AgendamentoPopover";
import { RoteirosSection } from "./RoteirosSection";
import { CARD_SUBPAGES, type CardSubpageKey } from "./cardSubpages";
import type { GeracaoDestino } from "./GeradorContratoSection";
import { rolarAteAlvo } from "@/hooks/useRolarAteAlvo";
import { SW_TIMELINE_RENDERERS } from "./Timeline";
import {
  DocumentoChecklistSection,
  progressoChecklist,
} from "./DocumentoChecklistSection";
import { CasadoToggle } from "./CasadoToggle";
import { CertidaoCasamentoSlot, TIPO_CERTIDAO_CASAMENTO } from "./CertidaoCasamentoSlot";
import { estadoCivilExigeConjuge, temArquivoCin } from "@/types/qualificacaoCompletude";

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
   * Archive THIS FUNIL CARD (`atendimentos.arquivado=true`) — the cliente
   * itself stays active; only the pipeline row hides. Absent ⇒ the icon
   * hides, same convention as every other optional action below: the card
   * was opened WITHOUT an atendimento in context (e.g. from the Clientes
   * board), so there is nothing here to archive. The confirm dialog is a
   * SIBLING of this one (owner: `ClienteDetailModal`) — nesting a Dialog
   * inside this one's content fights the outer focus trap, the same
   * reason every other confirm/create dialog on this card lives there.
   */
  onArquivarAtendimento?: () => void;
  /** Disables the archive icon while the mutation is in flight. */
  arquivandoAtendimento?: boolean;
  /**
   * Hard-delete the CLIENTE (irreversible) — admin/owner only. Absent ⇒
   * the icon hides: the container only ever passes this when the caller
   * IS an admin (a UI convenience; the route re-checks server-side
   * regardless — see `clientes_router.excluir_cliente_route`). Same
   * sibling-confirm-dialog reasoning as `onArquivarAtendimento` above.
   */
  onExcluirCliente?: () => void;
  /** Disables the delete icon while the mutation is in flight. */
  excluindoCliente?: boolean;

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
   * Correct a buyer-side party's role, from the badge that already showed it.
   *
   * 🔴 The add-dialog deliberately does NOT ask for a role (it asks the two
   * `stage_gate.CAMPOS_OBRIGATORIOS` fields and nothing else), so the side
   * default used to be permanent. Until this existed, no party could ever be
   * marked `conjuge` — and a sale by a married owner needs the spouse's
   * consent (CC art. 1.647), which a contract cannot ask for if no row says
   * who the spouse is.
   *
   * Absent ⇒ the badge stays a read-only badge. Mirrors `onRemoverComprador`'s
   * shape: the PARTE id, never the person's.
   */
  onAlterarPapelComprador?: (parteId: string, papel: string) => void;
  /**
   * The Cônjuge tab's own empty-state action — creates the buyer-side party
   * with `papel: "conjuge"` directly, rather than routing through the
   * generic `onAdicionarComprador` and asking the operator to set the role
   * afterwards from the badge. Absent ⇒ the empty state shows no button, the
   * same shape as every other optional add-handler here.
   */
  onAdicionarConjuge?: () => void;

  // ─── Vendedores — the other side of the table (migration 098) ──────────
  /**
   * Who is SELLING. Structurally identical to `compradores` — same person
   * model, same checklist, same uploads — and deliberately a separate prop
   * rather than one list filtered by `lado`: the two render on different
   * subpages, and a single list would make every consumer filter it correctly
   * at each site.
   *
   * Unlike Compradores, an empty list here is NOT the ordinary case and the
   * panel does NOT hide itself. A deal with no seller recorded is a gap worth
   * showing, because the contract cannot name a party nobody entered.
   */
  vendedores?: Comprador[];
  vendedoresLoading?: boolean;
  onAdicionarVendedor?: () => void;
  onRemoverVendedor?: (parteId: string) => void;
  /** Same control on the seller side, over `PAPEIS_POR_LADO.vendedor`. Two
   *  props rather than one for the same reason the two lists are two props:
   *  the sides render on different subpages and each owns its own copy. */
  onAlterarPapelVendedor?: (parteId: string, papel: string) => void;
  /**
   * The party whose role is being saved right now — that ONE select is
   * disabled, not every one of them. A single boolean would freeze the whole
   * card because both sides share one mutation.
   */
  papelSalvandoParteId?: string | null;
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
   * Renders one party's structured certidões (número, emissão, validade,
   * resultado) under their documents panel — same render-prop reasoning as
   * `renderDocumentosDePessoa`, but keyed by the atendimento PARTE id, because
   * a certidão is linked to the person's role in this deal, not to the person.
   */
  renderCertidoesDaParte?: (parteId: string, nome: string, documento?: string) => ReactNode;
  /**
   * Renders one party's contract qualification completeness (migration 110)
   * — same render-prop reasoning as `renderDocumentosDePessoa`, and keyed
   * the SAME way (by `cliente_id`, not the parte id): qualificação is a fact
   * about the PERSON, not their role in this deal, exactly like the
   * documents panel above it.
   */
  renderQualificacaoDaParte?: (clienteId: string, nome: string) => ReactNode;
  /**
   * The TITULAR's own qualificação completeness, mounted beside
   * `DadosPessoaisForm` on the "Dados do cliente" tab. A thunk, not
   * `(clienteId, nome) => ReactNode`: this component is never handed the
   * titular's raw id (only their `nome`, for the header), the same reason
   * `renderNegociacao`/`renderFinanciamento`/`renderContratos` below are
   * thunks — the container already knows its own id.
   */
  renderQualificacaoDoTitular?: () => ReactNode;
  /**
   * The TITULAR's own structured certidões (contract automation F6,
   * migration 116) — `renderCertidoesDaParte`'s titular sibling, keyed the
   * same way `renderQualificacaoDoTitular` is: this component is never
   * handed the titular's raw id, only their `nome`. The titular has no
   * `atendimento_partes` row to key a per-parte fetch off (migration 073's
   * header), which is exactly why migration 116 added the sibling
   * cliente-scoped routes this panel reaches instead.
   *
   * The single `documento` arg is the titular's own CPF/CNPJ, sourced from
   * `props.dadosPessoais?.cpf` (the SAME document-checklist value
   * `DadosPessoaisForm` already reads/edits on this tab) — never a second,
   * independently-fetched copy. `undefined` when not on file yet.
   */
  renderCertidoesDoTitular?: (documento?: string) => ReactNode;
  /**
   * The TITULAR's own admin-decide surface (owner directive, 2026-09-19) —
   * `ConflitosPendentesCard`, same thunk reasoning as
   * `renderQualificacaoDoTitular`/`renderCertidoesDoTitular` above (this
   * component never sees the titular's raw id).
   */
  renderConflitosPendentes?: () => ReactNode;

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
  /** The Contratos subpage — same render-prop reasoning as the two above.
   *  Handed `irPara`: the readiness list's card-scoped "Resolver" — switches
   *  THIS dialog's subpage (`destino.ancora`) and lands on `destino.alvo`.
   *  The dialog owns its subpage in local state, so only it can do this. */
  renderContratos?: (nav: { irPara: (destino: GeracaoDestino) => void }) => ReactNode;
  /** The Empresas subpage (P0c contract, `project-history/roadmaps/
   *  sw-drive-extraction-P0c-contract.md` §F) — same render-prop reasoning
   *  as `renderNegociacao`/`renderFinanciamento` above: `EmpresasSection`
   *  fetches its own data keyed by the titular's `clienteId`, which this
   *  component is never handed directly. */
  renderEmpresas?: () => ReactNode;

  /** Current values behind the typed checklist items — read by the inline row
   *  editors AND by the full form on the Dados do cliente tab. */
  dadosPessoais?: DadosPessoais;
  onSaveDadosPessoais?: (valores: DadosPessoais) => void;
  dadosPessoaisSaving?: boolean;
  /** The server's own message from the titular's last rejected save (the
   *  RG==CPF 400, migration 110) — see `DadosPessoaisFormProps.saveError`. */
  dadosPessoaisError?: string | null;
  /** Owner directive, 2026-09-19 — see `DadosPessoaisFormProps
   *  .pendenteConfirmacao`. The titular's last save's admin-confirmation
   *  fallout. */
  dadosPessoaisPendente?: string[];
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
  onAddVisita: (roteiroId: string, codigo: string) => void;
  onRemoveVisita: (roteiroId: string, visitaId: string) => void;
  /** Record / undo a proposta and its acceptance on one visita. Accepting is
   *  what names the imóvel of the deal (migration 104). */
  onPatchProposta: (
    roteiroId: string,
    visitaId: string,
    body: VisitaPropostaBody,
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
  onUploadDocumentoChecklist?: (
    item: DocumentoChecklistItem,
    file: File,
    tipoDocumento: string,
  ) => void;
  /** Discards that file. The ROW stays: the mandatory list is server-defined
   *  and there is no such thing as deleting "CPF" from it. */
  onRemoverDocumentoChecklist?: (
    documentoId: string,
    item: DocumentoChecklistItem,
  ) => void;
  /** Opens a checklist document (RG/CPF) inline in a new tab — same id space
   *  as Anexos' `onOpenDocumento`. */
  onVisualizarDocumentoChecklist?: (documentoId: string) => void;
  /** Downloads a checklist document under its original filename. */
  onBaixarDocumentoChecklist?: (documentoId: string, nomeArquivo: string) => void;
  /** Opens an EXTRAS row's file. Same `documentoId` space as the mandatory
   *  rows — an extra's upload goes through the same `documentos_service`, so
   *  the caller hands over the very same handler. */
  onVisualizarDocumentoChecklistExtra?: (documentoId: string) => void;
  /** Downloads an EXTRAS row's file under its original filename. */
  onBaixarDocumentoChecklistExtra?: (
    documentoId: string,
    nomeArquivo: string,
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
  /** Re-queues a stuck/never-run extraction (`POST .../extrair`). Optional
   *  so an older caller (or a test) that has not wired the mutation yet
   *  simply gets no retry affordance on Anexos. */
  onReextrairDocumento?: (documentoId: string) => void;
  reextraindoDocumentoId?: string | null;

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
  // ONE "which popover is open" state, shared by the seed quick-action row and
  // SW's Agendar popover — on Geral (after Etiquetas) and on the Agendamentos
  // tab alike — so opening one closes whichever other was open.
  const [activePopover, setActivePopover] = useState<GeralPopoverKey | null>(null);

  const record = useRecordSections(props.atendimentos);
  const compradores = props.compradores ?? [];
  const vendedores = props.vendedores ?? [];

  // 🔴 ONE predicate for every marriage-gated surface this card has — the
  // "Casado(a)" toggle and the certidão slot on "Dados do cliente", AND
  // (this slice) the Cônjuge rail entry. All three read this SAME boolean so
  // switching the toggle shows or hides every one of them together, never
  // just some — never re-derived per surface.
  const titularCasado = estadoCivilExigeConjuge(props.dadosPessoais?.estado_civil);
  // The buyer-side party whose role IS "cônjuge" — the titular's own spouse.
  // Always searched on `compradores`, never `vendedores`: the titular is a
  // buyer by construction (`compradores_service.adicionar`'s own comment on
  // `atendimentos.cliente_id`), so THIS card's marriage is always a
  // buyer-side fact.
  const conjugeParte = compradores.find((p) => p.papel === "conjuge");
  // 🔴 Not shown twice. Once the Cônjuge tab exists, the spouse's panel lives
  // there — a full-width dedicated tab, not a card buried in a general list
  // — so Geral drops that one row rather than rendering it in both places.
  // Gated on `titularCasado`, not on `conjugeParte` alone: an existing
  // conjuge-tagged party survives here undisturbed if the tab that would
  // otherwise hold it is gone (estado_civil cleared after the role was set),
  // so nobody ever silently disappears from the card.
  const compradoresGeral = titularCasado
    ? compradores.filter((p) => p.papel !== "conjuge")
    : compradores;

  const agendamentoPopover = (
    <AgendamentoPopover
      open={activePopover === "agendamento"}
      onOpenChange={(o) => setActivePopover(o ? "agendamento" : null)}
      onCreate={props.onCreateAgendamento}
      saving={props.agendamentoSaving}
    />
  );

  /**
   * One party's collapsible panel — the SAME block on both sides of the table.
   * Keyed by the PARTE id; the side picks the role vocabulary, the handlers
   * and the testid prefix.
   */
  function renderParte(
    parte: Comprador,
    lado: "comprador" | "vendedor",
    opts?: { defaultOpen?: boolean },
  ) {
    const onAlterarPapel =
      lado === "comprador" ? props.onAlterarPapelComprador : props.onAlterarPapelVendedor;
    const onRemover = lado === "comprador" ? props.onRemoverComprador : props.onRemoverVendedor;
    return (
      <PessoaDocumentosSection
        key={parte.id}
        nome={nomeDaParte(parte)}
        papel={parte.papel}
        papeisDisponiveis={PAPEIS_POR_LADO[lado]}
        onPapelChange={onAlterarPapel && ((papel) => onAlterarPapel(parte.id, papel))}
        papelSalvando={props.papelSalvandoParteId === parte.id}
        defaultOpen={opts?.defaultOpen}
        testId={`${lado}-${parte.id}`}
        acao={
          onRemover && (
            <TooltipIconButton
              label={`Remover ${nomeDaParte(parte)} deste atendimento`}
              icon={Trash2}
              testId={`${lado}-remover-${parte.id}`}
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={() => onRemover(parte.id)}
            />
          )
        }
      >
        {() => (
          <>
            {props.renderDocumentosDePessoa?.(parte.cliente_id) ?? null}
            {props.renderCertidoesDaParte?.(
              parte.id,
              nomeDaParte(parte),
              parte.cliente?.cpf ?? undefined,
            ) ?? null}
            {props.renderQualificacaoDaParte?.(parte.cliente_id, nomeDaParte(parte)) ?? null}
          </>
        )}
      </PessoaDocumentosSection>
    );
  }

  // ── GERAL ──────────────────────────────────────────────────────────────
  // The seed spine in the order the work happens; SW's blocks enter at the
  // named slots — never by copying the subpage.
  const renderGeral = () => (
    <GeralSubpage
      tags={props.selectedTags}
      descricao={{
        corpo: props.descricaoCorpo,
        onSave: props.onSaveDescricao,
        saving: props.descricaoSaving,
      }}
      anexos={{
        documentos: props.documentos,
        tipos: props.tiposDocumento,
        loading: props.documentosLoading,
        refreshing: props.documentosRefreshing,
        uploading: props.uploadingDocumento,
        // The operator's OWN pick from the section's own `<Select>` — the tipo
        // no longer travels as a caller-supplied default.
        onUpload: (file, tipoDocumento) => props.onUploadDocumento(file, tipoDocumento),
        onOpenDocumento: props.onOpenDocumento,
        onDeleteDocumento: props.onDeleteDocumento,
        onReextrairDocumento: props.onReextrairDocumento,
        reextraindoDocumentoId: props.reextraindoDocumentoId,
      }}
      checklists={{
        checklists: props.checklists,
        loading: props.checklistsLoading,
        onRemoveChecklist: props.onRemoveChecklist,
        onAddItem: props.onAddItem,
        onToggleItem: props.onToggleItem,
        onRemoveItem: props.onRemoveItem,
      }}
      slots={{
        // b. The contact line — what an operator reads BEFORE picking up the
        //    phone.
        afterTags: (
          <ContatoResumo dados={props.dadosPessoais} origem={contatoDeOrigem(props.atendimentos)} />
        ),
        // d. + e. The client's paperwork, folded away by default.
        //    🔴 ONE fold, TWO levels. The mandatory checklist and the
        //    operator's own rows are the tallest thing on this card and are
        //    read once — when the deal is being put together — so "Dados
        //    obrigatórios" collapses as a whole and "Outros dados" is its own
        //    collapsible NESTED inside it. The outer header keeps the progress
        //    count: a fold that hides how much is left is a fold nobody opens.
        afterDescricao: (
          <CollapsibleSection
            testId="dados-obrigatorios"
            titulo={
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Dados obrigatórios
              </span>
            }
            resumo={
              <span className="flex shrink-0 items-center gap-1.5">
                {props.documentoChecklistRefreshing && (
                  <Loader2
                    className="h-3 w-3 animate-spin text-muted-foreground"
                    data-testid="documento-checklist-refreshing"
                  />
                )}
                <span
                  className="text-xs text-muted-foreground"
                  data-testid="documento-checklist-progresso"
                >
                  {progressoChecklist(props.documentoChecklist ?? []).done}/
                  {progressoChecklist(props.documentoChecklist ?? []).total}
                </span>
              </span>
            }
          >
            {() => (
              <>
                <DocumentoChecklistSection
                  hideHeader
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
                  onVisualizarDocumento={props.onVisualizarDocumentoChecklist}
                  onBaixarDocumento={props.onBaixarDocumentoChecklist}
                />

                {props.onCriarChecklistExtra && (
                  <CollapsibleSection
                    testId="outros-dados"
                    titulo={
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Outros dados
                      </span>
                    }
                    resumo={
                      props.checklistExtrasRefreshing ? (
                        <Loader2
                          className="h-3 w-3 shrink-0 animate-spin text-muted-foreground"
                          data-testid="checklist-extras-refreshing"
                        />
                      ) : undefined
                    }
                  >
                    {() => (
                      <ChecklistExtrasSection
                        hideHeader
                        items={props.checklistExtras ?? []}
                        loading={props.checklistExtrasLoading}
                        refreshing={props.checklistExtrasRefreshing}
                        error={props.checklistExtrasError}
                        onCriar={props.onCriarChecklistExtra!}
                        criando={props.checklistExtrasSaving}
                        onRenomear={props.onRenomearChecklistExtra ?? (() => {})}
                        onSalvarTexto={props.onSalvarTextoChecklistExtra ?? (() => {})}
                        onRemover={props.onRemoverChecklistExtra ?? (() => {})}
                        onUploadDocumento={props.onUploadChecklistExtra ?? (() => {})}
                        onRemoverDocumento={props.onRemoverDocumentoChecklistExtra ?? (() => {})}
                        onVisualizarDocumento={props.onVisualizarDocumentoChecklistExtra}
                        onBaixarDocumento={props.onBaixarDocumentoChecklistExtra}
                        salvando={props.checklistExtrasSaving}
                      />
                    )}
                  </CollapsibleSection>
                )}
              </>
            )}
          </CollapsibleSection>
        ),
        // f. Everyone ELSE's paperwork, then this person's files (the anexos).
        //    🔴 ONE PANEL PER PERSON, and the titular is not one of them — the
        //    titular IS the card. Collapsible because each panel's queries only
        //    run when opened.
        beforeAnexos:
          compradoresGeral.length > 0 ? (
            <div className="mb-4" data-testid="compradores-section">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Compradores
              </p>
              {compradoresGeral.map((parte) => renderParte(parte, "comprador"))}
            </div>
          ) : undefined,
      }}
    />
  );

  // ── The SW subpage renders, keyed by the registry ─────────────────────────
  const renders: Record<CardSubpageKey, (ctx: CardHubRenderCtx<CardSubpageKey>) => ReactNode> = {
    geral: renderGeral,

    // 🔴 The Dados do cliente tab is no longer read-only: the editor is
    // `DadosPessoaisForm` — the SAME form each party's panel uses, writing
    // through the SAME `onSaveDadosPessoais` path the inline rows use.
    cliente: () => (
      <>
        {props.onSaveDadosPessoais && (
          <>
            {/* Visible only while married — see `CasadoToggle`'s docblock
                for why turning it off writes `estado_civil` directly
                rather than a second, component-local flag. */}
            {titularCasado && (
              <CasadoToggle
                testId="casado-toggle-titular"
                salvando={props.dadosPessoaisSaving}
                onDesmarcar={() => props.onSaveDadosPessoais!({ estado_civil: null })}
              />
            )}
            <DadosPessoaisForm
              valores={props.dadosPessoais ?? {}}
              onSave={props.onSaveDadosPessoais}
              saving={props.dadosPessoaisSaving}
              saveError={props.dadosPessoaisError}
              pendenteConfirmacao={props.dadosPessoaisPendente}
              temCin={temArquivoCin(props.documentoChecklist)}
            />
            {props.renderConflitosPendentes?.() ?? null}
            {/* Same gate, same reasoning as the per-party panel
                (`PessoaDocumentosPanel`) — reads the titular's OWN
                `documentos` list, the same one Geral's Anexos renders, so
                there is no second fetch and no second source of truth. */}
            {titularCasado && (
              <CertidaoCasamentoSlot
                testId="certidao-casamento-titular"
                documentos={props.documentos}
                uploading={props.uploadingDocumento}
                onUpload={(file) => props.onUploadDocumento(file, TIPO_CERTIDAO_CASAMENTO)}
                onVisualizar={props.onOpenDocumento}
                onRemover={props.onDeleteDocumento}
              />
            )}
            {props.renderCertidoesDoTitular?.(props.dadosPessoais?.cpf ?? undefined) ?? null}
            {props.renderQualificacaoDoTitular?.() ?? null}
          </>
        )}
        <RecordSubpage sections={record.cliente} subpage="cliente" />
      </>
    ),

    // 🔴 Conditional entry — see `cardSubpages.CARD_SUBPAGES`'s own docblock
    // on `"conjuge"` for why this key can still be present in `renders`
    // (the `Record<CardSubpageKey, …>` type demands it) while never being
    // reachable in the rail unless `titularCasado`.
    conjuge: () =>
      conjugeParte ? (
        <div data-testid="card-subpage-conjuge" className="space-y-4">
          {/* `defaultOpen` — unlike the same party's card under Geral's
              Compradores list, this tab has exactly ONE thing to show, so
              there is no fold worth making the operator open by hand. */}
          {renderParte(conjugeParte, "comprador", { defaultOpen: true })}
        </div>
      ) : (
        <div data-testid="card-subpage-conjuge-vazio" className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Nenhum cônjuge cadastrado neste atendimento.
          </p>
          {props.onAdicionarConjuge && (
            <Button
              size="sm"
              variant="outline"
              onClick={props.onAdicionarConjuge}
              data-testid="adicionar-conjuge-btn"
            >
              <Plus className="mr-1 h-4 w-4" />
              Adicionar cônjuge
            </Button>
          )}
        </div>
      ),

    vendedor: () => (
      <div data-testid="card-subpage-vendedor" className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Vendedor</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Quem está vendendo o imóvel. O primeiro é o
              proprietário; cônjuge e procurador entram aqui também.
            </p>
          </div>
          {props.onAdicionarVendedor && (
            <Button
              size="sm"
              variant="outline"
              onClick={props.onAdicionarVendedor}
              data-testid="adicionar-vendedor-btn"
            >
              <Plus className="mr-1 h-4 w-4" />
              Adicionar vendedor
            </Button>
          )}
        </div>

        {/* 🔴 Two signals, never `isLoading`. A skeleton shows only while
            there is genuinely nothing yet; a refetch over existing rows must
            not unmount them. → KB § PATTERNS/frontend/lying-loading-state.md */}
        {props.vendedoresLoading && vendedores.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="card-subpage-vendedor-loading">
            Carregando…
          </p>
        ) : vendedores.length === 0 ? (
          /* Deliberately NOT hidden when empty, unlike Compradores: a deal
             with no seller recorded is a gap, and a contract cannot name a
             party nobody entered. */
          <p className="text-sm text-muted-foreground" data-testid="card-subpage-vendedor-empty">
            Nenhum vendedor cadastrado neste atendimento.
          </p>
        ) : (
          vendedores.map((parte) => renderParte(parte, "vendedor"))
        )}
      </div>
    ),

    // P0c contract §F — a container, same render-prop reasoning as
    // `financiamento`/`negociacao`/`contratos` below: `EmpresasSection`
    // fetches its own data keyed by the titular's clienteId.
    empresas: () => (
      <div data-testid="card-subpage-empresas">
        {props.renderEmpresas?.() ?? (
          <p className="text-sm text-muted-foreground">Empresas indisponível.</p>
        )}
      </div>
    ),

    agendamentos: () => (
      <AgendamentosSection
        agendamentos={props.agendamentos ?? []}
        loading={props.agendamentosLoading}
        onRemove={props.onRemoveAgendamento}
        acao={agendamentoPopover}
      />
    ),

    roteiros: () => (
      <RoteirosSection
        roteiros={props.roteiros ?? []}
        loading={props.roteirosLoading}
        refreshing={props.roteirosRefreshing}
        error={props.roteirosError}
        onCriar={props.onCriarRoteiro}
        onRemover={props.onRemoverRoteiro}
        onGerarPdf={props.onGerarRoteiroPdf}
        onPatchVisita={props.onPatchVisita}
        onAddVisita={props.onAddVisita}
        onRemoveVisita={props.onRemoveVisita}
        onPatchProposta={props.onPatchProposta}
        pdfPendingId={props.roteiroPdfPendingId}
      />
    ),

    financiamento: () => (
      <div data-testid="card-subpage-financiamento">
        {props.renderFinanciamento?.() ?? (
          <p className="text-sm text-muted-foreground">Financiamento indisponível.</p>
        )}
      </div>
    ),

    negociacao: () => (
      <div data-testid="card-subpage-negociacao">
        {props.renderNegociacao?.() ?? (
          <p className="text-sm text-muted-foreground">Negociação indisponível.</p>
        )}
      </div>
    ),

    contratos: (ctx) => (
      <div data-testid="card-subpage-contratos">
        {props.renderContratos?.({
          irPara: (destino) => {
            const alvoSubpage = CARD_SUBPAGES.find((s) => s.key === destino.ancora);
            if (alvoSubpage) ctx.select(alvoSubpage.key);
            if (destino.alvo) rolarAteAlvo(destino.alvo);
          },
        }) ?? (
          <p className="text-sm text-muted-foreground">Contratos indisponível.</p>
        )}
      </div>
    ),

    campanha: () => <RecordSubpage sections={record.campanha} subpage="campanha" />,
  };

  // The rail disables (never drops) a record subpage with nothing to show.
  const isEmpty = (key: CardSubpageKey) =>
    (key === "cliente" && record.cliente.length === 0) ||
    (key === "campanha" && record.campanha.length === 0);

  // 🔴 HIDDEN, not disabled — `CardSidebarNav`'s `isEmpty` greys out a rail
  // entry but never drops it (nothing-to-show is itself information worth
  // showing). "Cônjuge" is the opposite kind of absence: an unmarried
  // titular has no such entry AT ALL, the same way this card never grows a
  // rail item for a relationship it does not have. Dropped from the ARRAY
  // `CardHubDialog` renders, not merely marked empty — the one place this
  // registry is conditional. If "Cônjuge" was the active subpage when it
  // drops out, `CardHubDialog` itself falls back to the first entry
  // (`geral`) the next time it re-renders — no extra state needed here.
  const subpagesVisiveis = titularCasado
    ? CARD_SUBPAGES
    : CARD_SUBPAGES.filter((def) => def.key !== "conjuge");

  const subpages: CardSubpage<CardSubpageKey>[] = subpagesVisiveis.map((def) => ({
    ...def,
    render: renders[def.key],
    isEmpty: isEmpty(def.key),
    // The action row belongs to Geral. A row of quick-actions floating above
    // an unrelated tab is just noise; each other tab carries its own trigger.
    toolbar:
      def.key === "geral" ? (
        <GeralActions
          etiquetas={{
            allTags: props.allTags,
            selectedTagIds: props.selectedTags.map((t) => t.id),
            onToggleTag: props.onToggleTag,
            onCreateTag: props.onCreateTag,
            onEditTag: props.onEditTag,
            colorBlindMode: props.colorBlindMode,
            onToggleColorBlindMode: props.onToggleColorBlindMode,
            saving: props.tagsSaving,
          }}
          membros={{
            allMembros: props.allMembros,
            selectedMembroIds: props.selectedMembros.map((m) => m.id),
            onToggleMembro: props.onToggleMembro,
            saving: props.membrosSaving,
          }}
          onCreateChecklist={props.onCreateChecklist}
          afterEtiquetas={agendamentoPopover}
          activePopover={activePopover}
          onActivePopoverChange={setActivePopover}
        />
      ) : undefined,
  }));

  return (
    <CardHubDialog<CardSubpageKey>
      open={open}
      onClose={onClose}
      isLoading={isLoading}
      error={error}
      notFound={notFound}
      nome={nome}
      testId="cliente-card-dialog"
      // Top-right: "Adicionar Comprador" is card-level ("this buyer is
      // married" is discovered while reading anything on the card), then
      // Arquivar/Excluir (both owner-request additions, both confirmed via
      // a SIBLING alert-dialog `ClienteDetailModal` owns — see this file's
      // own props docs), then whatever board opened the card (`acoes` —
      // its own buttons).
      headerActions={
        <>
          {props.onAdicionarComprador && (
            <TooltipIconButton
              label="Adicionar Comprador"
              icon={UserPlus}
              variant="outline"
              testId="adicionar-comprador-btn"
              onClick={props.onAdicionarComprador}
            />
          )}
          {props.onArquivarAtendimento && (
            <TooltipIconButton
              label="Arquivar no funil"
              icon={Archive}
              variant="outline"
              testId="arquivar-atendimento-btn"
              onClick={props.onArquivarAtendimento}
              disabled={props.arquivandoAtendimento}
            />
          )}
          {props.onExcluirCliente && (
            <TooltipIconButton
              label="Excluir cliente"
              icon={Trash2}
              variant="outline"
              testId="excluir-cliente-btn"
              onClick={props.onExcluirCliente}
              disabled={props.excluindoCliente}
            />
          )}
          {acoes}
        </>
      }
      subpages={subpages}
      // `geral` is the open-on-mount subpage: the card is opened to DO
      // something far more often than to read the record behind it.
      defaultSubpage="geral"
      // 🔴 Reported upward so the owner can fetch a tab's data WHEN IT IS
      // OPENED.
      onSubpageChange={props.onSubpageChange}
      activity={{
        composer: { onPost: props.onPostComentario, posting: props.postingComentario },
        timeline: {
          // SW's union adds `touch`; every SW entry is a seed entry (the
          // seed union's open `TimelineUnknownEntry` admits any kind).
          entries: props.timelineEntries as CardHubTimelineEntry[],
          loading: props.timelineLoading,
          error: props.timelineError,
          hasMore: props.timelineHasMore,
          loadingMore: props.timelineLoadingMore,
          onLoadMore: props.onTimelineLoadMore,
          renderers: SW_TIMELINE_RENDERERS,
        },
      }}
    />
  );
}

// ─── Sub-sections ───────────────────────────────────────────────────────────

/**
 * How a party's role reads on screen. Keys mirror
 * `compradores_service.PAPEIS_POR_LADO` — EVERY value of BOTH tuples has an
 * entry, which `ClienteCardDialog.test.tsx` pins against `PAPEIS_POR_LADO`
 * itself rather than against a second hand-written list.
 *
 * An unmapped value falls through to the raw string rather than rendering
 * blank (`rotuloDePapel`), so a role added on the server shows up as itself
 * until someone gives it a label. That fallback matters more now that the
 * badge is a `<select>`: a blank option is indistinguishable from "no role".
 */
const PAPEL_LABEL: Record<string, string> = {
  comprador: "Comprador",
  conjuge: "Cônjuge",
  fiador: "Fiador",
  procurador: "Procurador",
  outro: "Outro",
  // Seller-side roles (migration 098). One flat map rather than one per side:
  // `conjuge` and `procurador` render identically on both, and splitting the
  // map would duplicate them so that a label fix could land on one side only.
  proprietario: "Proprietário",
  inventariante: "Inventariante",
  // Contract-automation F6: a PREVIOUS owner, not today's seller — see
  // `PAPEIS_POR_LADO.vendedor`'s own docblock (`@/types/cardHub`).
  antigo_proprietario: "Antigo proprietário",
};

/** The one role whose label alone does not say WHY it exists on the card —
 *  every other role signs the contract; this one exists purely so its
 *  certidões can be attached to the deal's due diligence. Read by
 *  `PapelSelect` as a per-option hint (native `title` tooltip). */
const PAPEL_ANTIGO_PROPRIETARIO_HINT =
  "Não assina o contrato — usado apenas para anexar as certidões do antigo proprietário.";

/** The ONE place a role becomes words. Exported for the test that pins every
 *  `PAPEIS_POR_LADO` value against it. */
export function rotuloDePapel(papel: string): string {
  return PAPEL_LABEL[papel] ?? papel;
}

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
 * The fold itself is `CollapsibleSection` — this composes the header ONE party
 * needs (their name, then their role as a badge) and hands the rest over. The
 * chrome moved out when the card grew a second thing worth folding (the
 * Dados obrigatórios / Outros dados pair above): two hand-rolled chevron
 * headers would have been two places for the keyboard semantics to drift.
 *
 * 🔴 The children stay a THUNK, and that is load-bearing rather than
 * cosmetic: a party's panel runs its own queries against their `cliente_id`,
 * so mounting three collapsed panels would fire three checklist fetches and
 * three document fetches for panels nobody is looking at. Opening is what asks
 * for the data. `CollapsibleSection` preserves that contract — see its
 * docblock before changing either.
 */
function PessoaDocumentosSection({
  nome,
  papel,
  papeisDisponiveis,
  onPapelChange,
  papelSalvando = false,
  defaultOpen = false,
  testId,
  acao,
  children,
}: {
  nome: string;
  /** 🔴 The RAW value (`conjuge`), not a label. Labelling happens here so the
   *  fallback for an unmapped role lives in ONE place, and so the select's
   *  option values are the vocabulary the API validates. */
  papel: string;
  /** The roles this party's SIDE offers — `PAPEIS_POR_LADO[lado]`. Absent (or
   *  without `onPapelChange`) leaves the badge read-only. */
  papeisDisponiveis?: readonly string[];
  onPapelChange?: (papel: string) => void;
  papelSalvando?: boolean;
  defaultOpen?: boolean;
  testId: string;
  /** Rendered in the header, beside the role badge — today the detach button.
   *  Outside the toggle so clicking it does not also expand the panel. */
  acao?: ReactNode;
  /** A FUNCTION, not a node — see the docblock above. */
  children: () => ReactNode;
}) {
  const editavel = !!onPapelChange && !!papeisDisponiveis?.length;

  return (
    <CollapsibleSection
      testId={`pessoa-documentos-${testId}`}
      defaultOpen={defaultOpen}
      acao={
        <>
          {editavel ? (
            <PapelSelect
              papel={papel}
              opcoes={papeisDisponiveis!}
              onChange={onPapelChange!}
              salvando={papelSalvando}
              testId={testId}
              nome={nome}
            />
          ) : (
            <span
              className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
              data-testid={`papel-badge-${testId}`}
            >
              {rotuloDePapel(papel)}
            </span>
          )}
          {acao}
        </>
      }
      titulo={
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold">{nome}</span>
        </span>
      }
    >
      {children}
    </CollapsibleSection>
  );
}

/**
 * The role badge, which IS the control.
 *
 * 🔴 NOTHING NEW APPEARS ON SCREEN. `papel` was API-reachable and
 * UI-unreachable: `AdicionarCompradorDialog` asks for the two
 * `stage_gate.CAMPOS_OBRIGATORIOS` fields and never sent a role, so the side's
 * default was permanent — every buyer a `comprador`, every seller a
 * `proprietario`, and no `conjuge` for the spouse whose signature a sale by a
 * married owner legally requires (CC art. 1.647). Rather than grow the one
 * frictionless flow with a dropdown asked at the moment the operator knows
 * LEAST about the person, the label already on screen became the thing you
 * click. The common case still costs zero clicks: the side default is right
 * until it isn't, and you touch this only for the exceptions — which is
 * exactly when you know.
 *
 * 🔴 IT LIVES IN `acao`, NOT IN `titulo`. `CollapsibleSection` renders `titulo`
 * INSIDE the fold's `<button>`; a control there would both fold the panel on
 * every click and nest interactive content inside a button. `acao` is the slot
 * kept outside the toggle for exactly this — see that component's docblock.
 *
 * A native `<select>` rather than the Radix `Select` `ChecklistItemRow` uses:
 * five options with no search, no grouping and no custom rendering, inside a
 * Dialog that already portals — and `AgendamentoPopover` set that precedent.
 * The plain element is also the one a test can actually change.
 */
function PapelSelect({
  papel,
  opcoes,
  onChange,
  salvando,
  testId,
  nome,
}: {
  papel: string;
  opcoes: readonly string[];
  onChange: (papel: string) => void;
  salvando: boolean;
  testId: string;
  nome: string;
}) {
  // A role the server sent that this side's list does not offer still has to
  // be SHOWN — a select whose value matches no option renders blank, which
  // would read as "this person has no role" rather than "an unexpected one".
  const valores = opcoes.includes(papel) ? opcoes : [papel, ...opcoes];

  return (
    <select
      value={papel}
      disabled={salvando}
      aria-label={`Papel de ${nome}`}
      onChange={(e) => {
        if (e.target.value !== papel) onChange(e.target.value);
      }}
      className="h-6 shrink-0 rounded bg-muted px-1 text-[10px] uppercase tracking-wide text-muted-foreground disabled:opacity-50"
      data-testid={`papel-select-${testId}`}
    >
      {valores.map((p) => (
        <option
          key={p}
          value={p}
          title={p === "antigo_proprietario" ? PAPEL_ANTIGO_PROPRIETARIO_HINT : undefined}
        >
          {rotuloDePapel(p)}
        </option>
      ))}
    </select>
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
