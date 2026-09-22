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
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/CardSidebarNav.tsx` into the
 * seed card hub (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C) — a MOVE, not a rewrite: markup, classes and data-testids are SW's,
 * so SW's own suites pass unchanged once it consumes this copy (Slice F).
 */
import type { LucideIcon } from "lucide-react";

import { cn } from "../../utils";

/** One rail entry. The seed ships no fixed list — the card's subpages are a
 *  REGISTRY the product declares (see `CardSubpage` in `CardHubDialog`). */
export interface CardSidebarNavItem<K extends string = string> {
  key: K;
  label: string;
  icon: LucideIcon;
}

/** The collapsed rail's width, and the width the grid column reserves. The two
 *  MUST agree: the column is what stops the expansion from reflowing. */
export const RAIL_LARGURA_FECHADA = "3.25rem";

export interface CardSidebarNavProps<K extends string = string> {
  /** The registry, in reading order. Order is the product's decision. */
  items: readonly CardSidebarNavItem<K>[];
  active: K;
  onSelect: (key: K) => void;
  /**
   * Keys with nothing to show. Rendered disabled rather than dropped: a rail
   * whose items come and go per record teaches the user nothing about where a
   * thing lives, and "this card has no campaign" is itself information.
   */
  emptyKeys?: readonly K[];
}

export function CardSidebarNav<K extends string>({
  items,
  active,
  onSelect,
  emptyKeys = [],
}: CardSidebarNavProps<K>) {
  return (
    // The RESERVED column. It keeps the collapsed width no matter how wide the
    // nav inside it grows, which is what makes the expansion an overlay rather
    // than a reflow. On narrow screens it reserves nothing and the strip flows
    // normally.
    //
    // Mobile-first (R0, `max-sm:` only — desktop classes are SW's): below `sm`
    // the dialog is a full-screen sheet that scrolls as a whole, so the strip
    // STICKS to its top — the subpage tabs stay reachable from anywhere in a
    // long Geral.
    <div
      className="relative md:w-[3.25rem] md:shrink-0 max-sm:sticky max-sm:top-0 max-sm:z-20 max-sm:bg-background"
      data-testid="card-sidebar-rail"
    >
      <nav
        aria-label="Seções do cartão"
        className={cn(
          "group flex gap-1 overflow-x-auto border-b bg-muted/30 p-2",
          // Below `sm`: a horizontally scrollable tab strip; the right padding
          // clears the sheet's close button (absolute, top-right).
          "max-sm:snap-x max-sm:pr-12",
          "md:absolute md:inset-y-0 md:left-0 md:z-30 md:w-[3.25rem] md:flex-col",
          "md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-2",
          "md:transition-[width,background-color,box-shadow] md:duration-200",
          // The two expansion triggers, declared together on purpose.
          // 🔴 `has-[:focus-visible]`, NOT `focus-within` (fixed 2026-08-27,
          // caught live in prod). `focus-within` is true after a MOUSE click
          // too, so clicking a rail item left focus on it and pinned the rail
          // open across the pane the click had just navigated to — it only
          // closed once you clicked something else. `:focus-visible` is set by
          // the browser for keyboard/AT focus and NOT for a mouse click, which
          // is exactly the distinction this needs: the keyboard path keeps its
          // expansion, the pointer path stops sticking.
          "md:hover:w-56 md:has-[:focus-visible]:w-56",
          "md:hover:bg-muted md:has-[:focus-visible]:bg-muted",
          "md:hover:shadow-xl md:has-[:focus-visible]:shadow-xl",
        )}
        data-testid="card-sidebar-nav"
      >
        {items.map(({ key, label, icon: Icon }) => {
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
                // Tabs in a scroll strip never shrink or wrap, and meet the
                // 40px touch floor.
                "max-sm:min-h-10 max-sm:shrink-0 max-sm:snap-start max-sm:whitespace-nowrap",
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
                  // Same `:focus-visible` switch as the rail width above — the
                  // label must reveal on exactly the states the rail expands
                  // on, or a keyboard user gets a wide rail full of clipped
                  // labels.
                  "md:group-has-[:focus-visible]:w-auto md:group-has-[:focus-visible]:whitespace-normal md:group-has-[:focus-visible]:opacity-100",
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
