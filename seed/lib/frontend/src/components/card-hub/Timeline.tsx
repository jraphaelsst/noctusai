/**
 * Timeline — the unified "Comentários e atividade" thread (one thread,
 * everything). Renders `TimelineEntry` rows newest-first.
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/Timeline.tsx`
 * into the seed card hub (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C). Markup, classes and data-testids are SW's.
 *
 * 🔴 KIND-RENDERER REGISTRY, NOT A SWITCH
 * ---------------------------------------
 * SW's copy was a closed `switch (entry.kind)` over SW's own kinds. The seed
 * cannot know a product's kinds, so each kind is a REGISTERED renderer
 * (`{ icon, summary }`): the seed ships the kinds its backend gatherers
 * produce (`DEFAULT_TIMELINE_RENDERERS` — nota, documento, checklist) plus
 * opt-in generic ones (`GENERIC_TIMELINE_RENDERERS` — movimento, sistema); a
 * product merges its own over them (SW: `touch`).
 *
 * 🔴 AN UNREGISTERED KIND STILL RENDERS. It gets the generic fallback line
 * ("Evento (<kind>)" plus a `(<kind>)` tag) — never a crash, never a silently
 * dropped row. That is how a backend can ship a new kind before any frontend
 * learns it.
 *
 * Loading follows `KB § PATTERNS/frontend/lying-loading-state.md`: the
 * skeleton shows only while there are NO entries yet (`loading && !entries`),
 * so a refetch over existing rows never blanks them.
 *
 * Presentational only: props in, callbacks out.
 */
import type { LucideIcon } from "lucide-react";
import { FileText, MessageSquare, MoveRight, Paperclip, SquareCheck } from "lucide-react";

import { Avatar, AvatarFallback } from "../../design-system/ui/avatar";
import { CardHubButton as Button } from "../../design-system/ui/card-hub-button";
import { formatDate } from "../../utils";
import type {
  TimelineChecklistEntry,
  TimelineDocumentoEntry,
  TimelineEntry,
  TimelineMovimentoEntry,
  TimelineNotaEntry,
  TimelineSistemaEntry,
} from "./types";

/** How ONE timeline kind renders: its glyph (shown when the entry has no
 *  actor) and its one-line summary. */
export interface TimelineKindRenderer {
  icon: LucideIcon;
  // The entry is typed loosely on purpose: the registry is keyed by a runtime
  // string, so each renderer narrows to its own entry shape itself.
  summary: (entry: any) => string;
}

export type TimelineRenderers = Readonly<Record<string, TimelineKindRenderer>>;

/** The kinds the seed backend gatherers produce. */
export const DEFAULT_TIMELINE_RENDERERS: TimelineRenderers = {
  nota: {
    icon: MessageSquare,
    summary: (entry: TimelineNotaEntry) => (entry.deleted_at ? "Nota removida" : entry.corpo),
  },
  documento: {
    icon: Paperclip,
    summary: (entry: TimelineDocumentoEntry) => `Anexou ${entry.nome_original}`,
  },
  checklist: {
    icon: SquareCheck,
    summary: (entry: TimelineChecklistEntry) =>
      `${entry.concluido ? "Concluiu" : "Reabriu"} "${entry.item_texto}" em ${entry.titulo}`,
  },
};

/** Generic kinds a product opts into by merging them into `renderers`. */
export const GENERIC_TIMELINE_RENDERERS: TimelineRenderers = {
  movimento: {
    icon: MoveRight,
    summary: (entry: TimelineMovimentoEntry) =>
      entry.de_etapa
        ? `Moveu de "${entry.de_etapa}" para "${entry.para_etapa}"`
        : `Entrou em "${entry.para_etapa}"`,
  },
  sistema: {
    icon: FileText,
    summary: (entry: TimelineSistemaEntry) =>
      entry.detalhe ? `${entry.evento} — ${entry.detalhe}` : entry.evento,
  },
};

export interface TimelineProps {
  entries: TimelineEntry[];
  loading: boolean;
  error?: string | null;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  testId?: string;
  /**
   * The kind registry. Defaults to `DEFAULT_TIMELINE_RENDERERS`; a product
   * passes `{ ...DEFAULT_TIMELINE_RENDERERS, ...GENERIC_TIMELINE_RENDERERS,
   * ...own }`. A kind absent from it renders through the unknown-kind
   * fallback.
   */
  renderers?: TimelineRenderers;
}

function initials(nome: string): string {
  const parts = nome.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

function TimelineEntryRow({
  entry,
  renderers,
}: {
  entry: TimelineEntry;
  renderers: TimelineRenderers;
}) {
  const renderer = Object.prototype.hasOwnProperty.call(renderers, entry.kind)
    ? renderers[entry.kind]
    : undefined;
  const Icon = renderer?.icon ?? FileText;
  return (
    <li className="flex gap-3" data-testid="timeline-entry" data-kind={entry.kind}>
      {entry.ator ? (
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarFallback className="bg-red-600 text-xs text-white">
            {initials(entry.ator.nome)}
          </AvatarFallback>
        </Avatar>
      ) : (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Icon className="h-4 w-4" />
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="break-words text-sm">
          {entry.ator && <span className="font-semibold">{entry.ator.nome} </span>}
          {/* Unknown kind — a best-effort generic line rather than a crash
              or a silently dropped entry. */}
          {renderer ? renderer.summary(entry) : `Evento (${entry.kind})`}
          {!renderer && (
            <span className="ml-1 text-xs text-muted-foreground" data-testid="timeline-entry-unknown-kind">
              ({entry.kind})
            </span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">{formatDate(entry.ocorrido_em, true)}</p>
      </div>
    </li>
  );
}

export function Timeline({
  entries,
  loading,
  error,
  hasMore,
  loadingMore,
  onLoadMore,
  testId = "timeline",
  renderers = DEFAULT_TIMELINE_RENDERERS,
}: TimelineProps) {
  // Two signals, never one: the skeleton only while there is nothing to show.
  const showSkeleton = loading && entries.length === 0;
  const isEmpty = !showSkeleton && !error && entries.length === 0;

  return (
    <div data-testid={testId} className="space-y-4">
      {error ? (
        <p className="text-sm text-destructive" data-testid="timeline-error">
          Não foi possível carregar o histórico.
        </p>
      ) : showSkeleton ? (
        <div className="space-y-3" data-testid="timeline-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isEmpty ? (
        <p className="text-sm text-muted-foreground" data-testid="timeline-empty">
          Nenhuma atividade ainda.
        </p>
      ) : (
        <ul className="space-y-4">
          {entries.map((entry) => (
            <TimelineEntryRow key={entry.id} entry={entry} renderers={renderers} />
          ))}
        </ul>
      )}

      {hasMore && !showSkeleton && (
        <div className="pt-2 text-center">
          <Button
            variant="ghost"
            size="sm"
            className="max-sm:min-h-10"
            disabled={loadingMore}
            onClick={onLoadMore}
          >
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}
