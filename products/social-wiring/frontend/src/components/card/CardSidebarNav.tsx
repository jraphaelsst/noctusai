/**
 * CardSidebarNav — the card's left-rail subpage navigation.
 *
 * The card grew past one scrollable column: the working surface (etiquetas,
 * descrição, agendamentos, checklists, anexos) and the READ-ONLY record data
 * (who the person is, which campaign and property produced them) were stacked
 * on top of each other, so reaching the work meant scrolling past the data and
 * vice-versa. They are different jobs at different moments, which is what a
 * subpage is for.
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
import { ClipboardList, Megaphone, User } from "lucide-react";

import { cn } from "@/lib/utils";

/** Which subpage the card is showing. `atividade` is the default on open. */
export type CardSubpageKey = "atividade" | "cliente" | "campanha";

interface SubpageDef {
  key: CardSubpageKey;
  label: string;
  icon: LucideIcon;
}

/**
 * Order is the reading order of the card: what you DO with this person first,
 * then who they are, then where they came from.
 */
export const CARD_SUBPAGES: readonly SubpageDef[] = [
  { key: "atividade", label: "Atividade", icon: ClipboardList },
  { key: "cliente", label: "Dados do cliente", icon: User },
  { key: "campanha", label: "Campanha e imóvel", icon: Megaphone },
] as const;

export interface CardSidebarNavProps {
  active: CardSubpageKey;
  onSelect: (key: CardSubpageKey) => void;
  /**
   * Keys with nothing to show. Rendered disabled rather than dropped: a rail
   * whose items come and go per record teaches the user nothing about where a
   * thing lives, and "this card has no campaign" is itself information.
   */
  emptyKeys?: readonly CardSubpageKey[];
}

export function CardSidebarNav({ active, onSelect, emptyKeys = [] }: CardSidebarNavProps) {
  return (
    <nav
      aria-label="Seções do cartão"
      // Vertical rail on md+, a horizontal strip on narrow screens. NOT
      // `hidden md:flex`: the dialog collapses to one column there, so hiding
      // the rail would leave the cliente/campanha subpages unreachable on a
      // phone rather than merely restyled.
      className={cn(
        "flex shrink-0 gap-1 overflow-x-auto border-b bg-muted/30 p-2",
        "md:flex-col md:overflow-x-visible md:border-b-0 md:border-r md:p-3",
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
            data-testid={`card-subpage-tab-${key}`}
            data-active={isActive ? "true" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
              isActive
                ? "bg-background font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
              isEmpty && "cursor-not-allowed opacity-40 hover:bg-transparent",
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
