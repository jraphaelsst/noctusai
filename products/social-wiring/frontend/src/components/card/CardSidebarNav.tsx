/**
 * CardSidebarNav — the card's left-rail subpage navigation, as a HOVER RAIL.
 *
 * The card grew past one scrollable column: the working surface (etiquetas,
 * descrição, dados obrigatórios, anexos, checklists) and the READ-ONLY record
 * data (who the person is, which campaign and property produced them) were
 * stacked on top of each other, so reaching the work meant scrolling past the
 * data and vice-versa. They are different jobs at different moments, which is
 * what a subpage is for.
 *
 * 🔴 ICON-ONLY, EXPANDING ON HOVER — AS AN OVERLAY
 * ------------------------------------------------
 * The rail rests at icon width and reveals its labels on hover, matching the
 * main app sidebar so the card does not teach a second navigation idiom.
 *
 * The expansion FLOATS. The grid column keeps the COLLAPSED width and the nav
 * itself is absolutely positioned inside it, so opening the rail draws over
 * the middle pane instead of squeezing it: "it's positioned on top of the
 * screen, instead of changing the screen size". A width transition on a grid
 * COLUMN would reflow — and reflowing the pane under the pointer moves the
 * thing the user was reading, on every accidental hover.
 *
 * 🔴 `focus-within` EXPANDS IT TOO. A hover-only rail is unreachable by
 * keyboard: tabbing into it would move focus onto buttons whose labels are
 * clipped to zero width. The two triggers are declared together so the
 * keyboard path cannot be forgotten later.
 *
 * NOT `hidden md:flex`: below `md` the dialog collapses to a single column, so
 * hiding the rail would leave the cliente/campanha subpages unreachable on a
 * phone rather than merely restyled. There it stays a horizontal strip with
 * its labels always visible — there is no hover on a phone, so a rail that
 * only opens on hover would be a row of unlabelled glyphs.
 *
 * Presentational only, same contract as the rest of `card/**` (PROJECT.md §0):
 * the active key and the setter come in as props, so the dialog owns the state
 * and this file owns only how it looks.
 *
 * NOT the seed `Tabs` primitive: this is a persistent left rail beside content
 * that keeps its own scroll position, not a horizontal strip above a single
 * panel. Checked before building (`noc-organ-consume-check`); if a second
 * product needs a rail like this, THIS is the extraction target.
 */
import type { LucideIcon } from "lucide-react";
import {
  CalendarClock,
  ClipboardList,
  Handshake,
  Landmark,
  Megaphone,
  Route,
  User,
} from "lucide-react";

import { cn } from "@/lib/utils";

/** Which subpage the card is showing. `geral` is the default on open. */
export type CardSubpageKey =
  | "geral"
  | "cliente"
  | "agendamentos"
  | "roteiros"
  | "financiamento"
  | "negociacao"
  | "campanha";

interface SubpageDef {
  key: CardSubpageKey;
  label: string;
  icon: LucideIcon;
}

/** The collapsed rail's width, and the width the grid column reserves. The two
 *  MUST agree: the column is what stops the expansion from reflowing. */
export const RAIL_LARGURA_FECHADA = "3.25rem";

/**
 * Order is the reading order of the card: what you DO with this person, then
 * who they are, then what is booked with them, then how the deal closes, then
 * where they came from.
 *
 * `roteiros` sits IMMEDIATELY under `agendamentos` because that is the funnel
 * order the user named — qualificação leads to a VISIT, and a roteiro is the
 * planned visit. It is also the tab you reach for right after failing to find
 * "Visita" in the Agendar button, which no longer offers it (migration 082).
 *
 * 🔴 `documentos` IS GONE, and its absence is the point. Everything it held —
 * the required-data checklist, each party's panel, the anexos — moved onto
 * Geral, because collecting a document is not a separate errand from working
 * the card: it is the work. A tab for it meant the operator read "RG pendente"
 * on one screen and supplied it on another. `financiamento` inherits the slot
 * it used to sit above, and keeps it: it is another pile of paperwork to
 * collect, just one belonging to the bank rather than to the person.
 */
export const CARD_SUBPAGES: readonly SubpageDef[] = [
  { key: "geral", label: "Geral", icon: ClipboardList },
  { key: "cliente", label: "Dados do cliente", icon: User },
  { key: "agendamentos", label: "Agendamentos", icon: CalendarClock },
  { key: "roteiros", label: "Roteiros", icon: Route },
  { key: "financiamento", label: "Financiamento/Escritura", icon: Landmark },
  { key: "negociacao", label: "Negociação", icon: Handshake },
  { key: "campanha", label: "Campanha e imóvel", icon: Megaphone },
] as const;

export interface CardSidebarNavProps {
  active: CardSubpageKey;
  onSelect: (key: CardSubpageKey) => void;
  /**
   * Keys with nothing to show. Rendered disabled rather than dropped: a rail
   * whose items come and go per record teaches the user nothing about where a
   * thing lives, and "this card has no campaign" is itself information.
   *
   * Only the two RECORD subpages can be empty. `agendamentos` and `roteiros`
   * are always reachable even with nothing in them — you go there to ADD, and
   * a disabled tab would be a dead end on an empty card.
   */
  emptyKeys?: readonly CardSubpageKey[];
}

export function CardSidebarNav({ active, onSelect, emptyKeys = [] }: CardSidebarNavProps) {
  return (
    // The RESERVED column. It keeps the collapsed width no matter how wide the
    // nav inside it grows, which is what makes the expansion an overlay rather
    // than a reflow. On narrow screens it reserves nothing and the strip flows
    // normally.
    <div
      className="relative md:w-[3.25rem] md:shrink-0"
      data-testid="card-sidebar-rail"
    >
      <nav
        aria-label="Seções do cartão"
        className={cn(
          "group flex gap-1 overflow-x-auto border-b bg-muted/30 p-2",
          "md:absolute md:inset-y-0 md:left-0 md:z-30 md:w-[3.25rem] md:flex-col",
          "md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-2",
          "md:transition-[width,background-color,box-shadow] md:duration-200",
          // The two expansion triggers, declared together on purpose.
          "md:hover:w-56 md:focus-within:w-56",
          "md:hover:bg-muted md:focus-within:bg-muted",
          "md:hover:shadow-xl md:focus-within:shadow-xl",
        )}
        data-testid="card-sidebar-nav"
      >
        {CARD_SUBPAGES.map(({ key, label, icon: Icon }) => {
          const isActive = key === active;
          const isEmpty = emptyKeys.includes(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelect(key)}
              disabled={isEmpty}
              aria-current={isActive ? "page" : undefined}
              // 🔴 The accessible name, always — the visible label is clipped
              // to nothing while the rail rests, and a rail of unnamed glyphs
              // is unusable with a screen reader.
              aria-label={label}
              title={label}
              data-testid={`card-subpage-tab-${key}`}
              data-active={isActive ? "true" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                "md:w-full md:justify-start md:overflow-hidden md:px-2",
                isActive
                  ? "bg-background font-medium text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                isEmpty && "cursor-not-allowed opacity-40 hover:bg-transparent",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {/* Present in the DOM at every width — only its BOX collapses.
                  Rendering it conditionally would have removed the label from
                  the accessibility tree as well as from the screen, and would
                  have made the reveal a mount rather than a transition.

                  🔴 Wraps, never truncates, once revealed. At 184px
                  "Financiamento/Escritura" and "Campanha e imóvel" both
                  rendered as "Financiamento/…" and "Campanha e im…" — a nav
                  whose own labels do not fit is a nav you have to click to
                  read. */}
              <span
                aria-hidden="true"
                data-testid={`card-subpage-label-${key}`}
                className={cn(
                  "leading-tight",
                  "md:w-0 md:overflow-hidden md:whitespace-nowrap md:opacity-0",
                  "md:transition-[width,opacity] md:duration-200",
                  "md:group-hover:w-auto md:group-hover:whitespace-normal md:group-hover:opacity-100",
                  "md:group-focus-within:w-auto md:group-focus-within:whitespace-normal md:group-focus-within:opacity-100",
                )}
              >
                {label}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
