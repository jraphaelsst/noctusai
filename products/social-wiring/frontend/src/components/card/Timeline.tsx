/**
 * Timeline — the unified "Comentários e atividade" thread (D9: "everything,
 * one thread"), screenshot 03. Renders the `TimelineEntry` discriminated
 * union newest-first. PROJECT.md §3/§4.
 *
 * Presentational only (S3): props in (`entries`, loading flags, pagination
 * callback), callbacks out. An entry whose `kind` this build does not
 * recognise renders a graceful generic fallback — never crashes, never
 * silently drops it (§4) — Phase 2b's conversation kinds land on this slot
 * without a rewrite.
 */
import { FileText, MessageSquare, MoveRight, Paperclip, SquareCheck, Zap } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { KNOWN_TIMELINE_KINDS, type TimelineEntry, type TimelineUnknownEntry } from "@/types/cardHub";

export interface TimelineProps {
  entries: TimelineEntry[];
  loading: boolean;
  error?: string | null;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  testId?: string;
}

function initials(nome: string): string {
  const parts = nome.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

function EntryIcon({ kind }: { kind: string }) {
  switch (kind) {
    case "nota":
      return <MessageSquare className="h-4 w-4" />;
    case "touch":
      return <Zap className="h-4 w-4" />;
    case "movimento":
      return <MoveRight className="h-4 w-4" />;
    case "documento":
      return <Paperclip className="h-4 w-4" />;
    case "checklist":
      return <SquareCheck className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
}

/**
 * `TimelineUnknownEntry.kind` is a bare `string` (by design — it has to
 * accept whatever Phase 2b's new kinds are), which makes it structurally
 * compatible with EVERY known literal `kind` too — so a plain
 * `switch (entry.kind)` can never fully rule it out of a `case "nota":` etc.
 * branch, and TS widens every field access there to `unknown` (the
 * fallback's index signature). An explicit type predicate over the whole
 * `entry` (not just `entry.kind`) is what TS's narrowing actually needs.
 */
function isKnownEntry(entry: TimelineEntry): entry is Exclude<TimelineEntry, TimelineUnknownEntry> {
  return (KNOWN_TIMELINE_KINDS as readonly string[]).includes(entry.kind);
}

/**
 * "Novo contato via Meta Ads" — and the name only when it differs from the
 * label, so a row carries information rather than restating the card.
 */
function touchSummary(origem: string | null, nome: string | null): string {
  const via = (origem ?? "").trim();
  const quem = (nome ?? "").trim();
  if (via && quem && quem.toLowerCase() !== via.toLowerCase()) {
    return `Novo contato via ${via} — ${quem}`;
  }
  if (via) return `Novo contato via ${via}`;
  if (quem) return `Novo contato — ${quem}`;
  return "Novo contato";
}

function entrySummary(entry: TimelineEntry): string {
  if (!isKnownEntry(entry)) {
    // Unknown kind (Phase 2b conversation kinds, or anything future) —
    // render a best-effort generic line rather than crashing or dropping
    // the entry silently.
    return `Evento (${entry.kind})`;
  }
  switch (entry.kind) {
    case "nota":
      return entry.deleted_at ? "Nota removida" : entry.corpo;
    case "touch":
      // 🔴 A VERB, NOT JUST A NAME.
      //
      // This returned `entry.resumo` — the lead's name — so the timeline read
      // as the same name repeated down the page with a date under each one and
      // no indication of what had happened. Four identical-looking rows for
      // four separate contacts.
      //
      // `origem_rotulo` is where the contact came in from (Meta Ads, OLX, a
      // portal). The name is kept alongside it only when it adds something:
      // repeating the card's own title on every row is what made the list
      // unreadable in the first place.
      return touchSummary(entry.origem_rotulo, entry.resumo);
    case "movimento":
      return entry.de_etapa
        ? `Moveu de "${entry.de_etapa}" para "${entry.para_etapa}"`
        : `Entrou em "${entry.para_etapa}"`;
    case "documento":
      return `Anexou ${entry.nome_original}`;
    case "checklist":
      return `${entry.concluido ? "Concluiu" : "Reabriu"} "${entry.item_texto}" em ${entry.titulo}`;
    case "sistema":
      return entry.detalhe ? `${entry.evento} — ${entry.detalhe}` : entry.evento;
  }
}

function TimelineEntryRow({ entry }: { entry: TimelineEntry }) {
  const isKnown = KNOWN_TIMELINE_KINDS.includes(entry.kind as never);
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
          <EntryIcon kind={entry.kind} />
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="break-words text-sm">
          {entry.ator && <span className="font-semibold">{entry.ator.nome} </span>}
          {entrySummary(entry)}
          {!isKnown && (
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
}: TimelineProps) {
  const isEmpty = !loading && !error && entries.length === 0;

  return (
    <div data-testid={testId} className="space-y-4">
      {error ? (
        <p className="text-sm text-destructive" data-testid="timeline-error">
          Não foi possível carregar o histórico.
        </p>
      ) : loading ? (
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
            <TimelineEntryRow key={entry.id} entry={entry} />
          ))}
        </ul>
      )}

      {hasMore && !loading && (
        <div className="pt-2 text-center">
          <Button variant="ghost" size="sm" disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}
