/**
 * Timeline — SW's "Comentários e atividade" thread, a thin adapter over the
 * seed `Timeline` (`@noctusai/lib/components`, wave-a Slice C/F —
 * `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`).
 *
 * The seed renders any kind through a RENDERER REGISTRY and keeps the
 * unknown-kind fallback (an unregistered kind renders `Evento (<kind>)`, never
 * crashes, never drops). What stays SW is the registry: the seed's own kinds
 * (`nota`, `documento`, `checklist`), the generic `movimento` + `sistema`, and
 * SW's `touch` — the one kind only SW's backend gathers.
 *
 * 🔴 `visita` is deliberately NOT registered. SW's `KNOWN_TIMELINE_KINDS`
 * never listed it, so a `visita` entry (roteiro created / visita outcome,
 * migration 082) has always rendered through the unknown-kind fallback. The
 * swap onto the seed is a zero-behaviour-change move; giving `visita` a real
 * summary is a product decision for its own slice, not a side effect of this
 * one. `SW_TIMELINE_RENDERERS` is therefore exactly SW's pre-swap known set.
 */
import { Zap } from "lucide-react";
import {
  DEFAULT_TIMELINE_RENDERERS,
  GENERIC_TIMELINE_RENDERERS,
  Timeline as CardHubTimeline,
} from "@noctusai/lib/components";
import type {
  TimelineProps as CardHubTimelineProps,
  TimelineRenderers,
  TimelineEntry as CardHubTimelineEntry,
} from "@noctusai/lib/components";

import type { TimelineEntry, TimelineTouchEntry } from "@/types/cardHub";
import { dataOnlyFromPossibleUtcMidnight } from "@/lib/utils";

/**
 * "Novo contato via Meta Ads" — and the name only when it differs from the
 * label, so a row carries information rather than restating the card.
 *
 * 🔴 A VERB, NOT JUST A NAME. This used to be the lead's name alone, so the
 * timeline read as the same name repeated down the page with no indication of
 * what had happened. `origem_rotulo` is where the contact came in from.
 */
function touchSummary(entry: TimelineTouchEntry): string {
  const via = (entry.origem_rotulo ?? "").trim();
  const quem = (entry.resumo ?? "").trim();
  if (via && quem && quem.toLowerCase() !== via.toLowerCase()) {
    return `Novo contato via ${via} — ${quem}`;
  }
  if (via) return `Novo contato via ${via}`;
  if (quem) return `Novo contato — ${quem}`;
  return "Novo contato";
}

/** SW's kind registry — the seed kinds, the generic ones, plus `touch`. */
export const SW_TIMELINE_RENDERERS: TimelineRenderers = {
  ...DEFAULT_TIMELINE_RENDERERS,
  ...GENERIC_TIMELINE_RENDERERS,
  touch: { icon: Zap, summary: touchSummary },
};

export interface TimelineProps extends Omit<CardHubTimelineProps, "entries" | "renderers"> {
  entries: TimelineEntry[];
}

/**
 * Bug 4 — `touch` is the one kind whose `ocorrido_em` traces back to a DATE
 * column (`data_entrada`). See `dataOnlyFromPossibleUtcMidnight`'s docblock
 * (`@/lib/utils`) for why a UTC-midnight timestamp there renders 3h into the
 * wrong calendar day, and why the rewrite is scoped to this one kind.
 */
function semDeslocamentoDeFuso(entries: TimelineEntry[]): TimelineEntry[] {
  return entries.map((entry) =>
    entry.kind === "touch"
      ? { ...entry, ocorrido_em: dataOnlyFromPossibleUtcMidnight(entry.ocorrido_em) }
      : entry,
  );
}

export function Timeline({ entries, ...props }: TimelineProps) {
  return (
    <CardHubTimeline
      {...props}
      // SW's union adds `touch`; structurally every SW entry is a seed entry
      // (the seed union's open `TimelineUnknownEntry` member admits any kind).
      entries={semDeslocamentoDeFuso(entries) as CardHubTimelineEntry[]}
      renderers={SW_TIMELINE_RENDERERS}
    />
  );
}
